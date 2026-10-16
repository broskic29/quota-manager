import threading
import datetime as dt
import logging
import time

import quota_manager.sql_management as sqlm
import quota_manager.quota_management as qm

from quota_manager.sqlite_helper_functions import UTC_OFFSET

USAGE_UPDATE_INTERVAL = 1
ONE_DAY = 1
ONE_MONTH = 1
DAILY_RESET_STARTUP_GRACE_SECONDS = 300

DAILY_RESET_COMPLETED = "completed"
DAILY_RESET_NOT_DUE = "not_due"
DAILY_RESET_DEFERRED_CLOCK = "deferred_clock"
DAILY_RESET_BUSY = "busy"
DAILY_RESET_FAILED = "failed"

MONTHLY_RESET_COMPLETED = "completed"
MONTHLY_RESET_NOT_DUE = "not_due"
MONTHLY_RESET_DEFERRED_CLOCK = "deferred_clock"
MONTHLY_RESET_BUSY = "busy"
MONTHLY_RESET_FAILED = "failed"
MONTHLY_RESET_BASELINED = "baseline_initialized"

USAGE_TRACKER_STARTED_AT = time.monotonic()
_LAST_DAILY_RESET_RESULT = None
_LAST_MONTHLY_RESET_RESULT = None

log = logging.getLogger(__name__)


def daily_delay_calc(now, tz):
    zero_hour = dt.datetime(now.year, now.month, now.day, tzinfo=tz)

    next_daily = zero_hour + dt.timedelta(days=ONE_DAY)

    log.info(f"Next daily wipe set for {next_daily}.")

    daily_delay = next_daily - now

    return daily_delay


def monthly_delay_calc(now, tz):
    zero_hour = dt.datetime(now.year, now.month, now.day, tzinfo=tz)

    next_monthly = zero_hour + dt.timedelta(days=(32 - now.day))
    next_monthly = next_monthly.replace(day=qm.ACCOUNT_BILLING_DAY)

    log.info(f"Next monthly wipe set for {next_monthly}.")

    monthly_delay = next_monthly - now

    return monthly_delay


def event_scheduler(stop_event: threading.Event):
    while not stop_event.is_set():

        tz = dt.timezone(dt.timedelta(hours=UTC_OFFSET))
        now = dt.datetime.now(tz)

        daily_delay = daily_delay_calc(now, tz)
        monthly_delay = monthly_delay_calc(now, tz)

        next_delay = min(daily_delay, monthly_delay)

        if stop_event.wait(next_delay.total_seconds()):
            break

        # After waking up, determine which tasks to run
        now = dt.datetime.now(tz)

        reconcile_daily_reset(now)
        reconcile_monthly_reset(now)


def clock_gate_decision(now, system_state, startup_elapsed_seconds):
    """Return whether persisted time makes the local wall clock trustworthy."""
    stored_date_text = system_state.get("system_date") if system_state else None
    try:
        stored_date = dt.date.fromisoformat(stored_date_text)
    except (TypeError, ValueError) as e:
        raise ValueError(
            f"Invalid persisted system date: {stored_date_text!r}"
        ) from e

    current_date = now.date()
    if current_date < stored_date:
        return stored_date_text, "clock_behind", DAILY_RESET_DEFERRED_CLOCK
    if (
        current_date > stored_date
        and startup_elapsed_seconds < DAILY_RESET_STARTUP_GRACE_SECONDS
    ):
        return stored_date_text, "startup_grace", DAILY_RESET_DEFERRED_CLOCK

    return stored_date_text, "clock_ready", None


def _daily_reset_decision(now, system_state, startup_elapsed_seconds):
    stored_date_text, decision, outcome = clock_gate_decision(
        now, system_state, startup_elapsed_seconds
    )
    if outcome is not None:
        return stored_date_text, decision, outcome

    if now.date().isoformat() == stored_date_text:
        return stored_date_text, "same_date", DAILY_RESET_NOT_DUE

    return stored_date_text, "forward_date", None


def _log_daily_reset_result(stored_date, current_date, decision, outcome, level=None):
    global _LAST_DAILY_RESET_RESULT
    result = (stored_date, current_date, decision, outcome)
    log_method = level or log.info
    if result == _LAST_DAILY_RESET_RESULT:
        log_method = log.debug
    else:
        _LAST_DAILY_RESET_RESULT = result

    log_method(
        "Daily reset reconciliation: stored_date=%s observed_date=%s "
        "decision=%s outcome=%s",
        stored_date,
        current_date,
        decision,
        outcome,
    )


def _perform_daily_reset(now, stored_date, db_path=None):
    qm.checkpoint_all_logged_in_users(db_path=db_path)
    log.info("Active user usage checkpoint complete before daily reset.")

    qm.log_out_all_users()
    log.info("All users logged out.")

    qm.nftm_flush_set_ghosts()
    log.info("Nftm set ghosts flushed.")

    qm.wipe_ip_neigh_db()
    log.info("IP neigh db wiped.")

    qm.reset_throttling_and_packet_dropping_all_users(db_path=db_path)
    log.info("Throttling and packet dropping reset for all users.")

    group_quotas_dict = qm.calculate_hypothetical_group_quotas_for_today(
        now=now, reset_day=qm.ACCOUNT_BILLING_DAY
    )
    qm.apply_new_quotas(group_quotas_dict)
    log.info("New daily quotas applied.")

    qm.update_daily_byte_budget(now)
    log.info("Quota byte budget updated.")

    return sqlm.usage_daily_wipe_and_advance_date(
        now.date().isoformat(), stored_date, db_path=db_path
    )


def reconcile_daily_reset(now, *, startup_elapsed_seconds=None, db_path=None):
    """Reconcile one due daily reset and return an explicit outcome string."""
    current_date = now.date().isoformat()
    if startup_elapsed_seconds is None:
        startup_elapsed_seconds = max(
            0.0, time.monotonic() - USAGE_TRACKER_STARTED_AT
        )

    try:
        system_state = sqlm.fetch_system_state(db_path)
        if system_state is None:
            raise RuntimeError("System state does not exist.")
        stored_date, decision, outcome = _daily_reset_decision(
            now, system_state, startup_elapsed_seconds
        )
    except Exception as e:
        log.error(
            "Daily reset reconciliation failed before lock acquisition: %s", e
        )
        _log_daily_reset_result(
            None, current_date, "state_error", DAILY_RESET_FAILED, log.error
        )
        return DAILY_RESET_FAILED

    if outcome is not None:
        level = log.warning if outcome == DAILY_RESET_DEFERRED_CLOCK else log.info
        _log_daily_reset_result(
            stored_date, current_date, decision, outcome, level
        )
        return outcome

    if not qm.RESET_LOCK.acquire(blocking=False):
        _log_daily_reset_result(
            stored_date, current_date, "reset_lock_busy", DAILY_RESET_BUSY
        )
        return DAILY_RESET_BUSY

    quota_lock_acquired = False
    try:
        quota_lock_acquired = qm.QUOTA_LOCK.acquire(blocking=False)
        if not quota_lock_acquired:
            _log_daily_reset_result(
                stored_date, current_date, "quota_lock_busy", DAILY_RESET_BUSY
            )
            return DAILY_RESET_BUSY

        try:
            system_state = sqlm.fetch_system_state(db_path)
            if system_state is None:
                raise RuntimeError("System state does not exist.")
            stored_date, decision, outcome = _daily_reset_decision(
                now, system_state, startup_elapsed_seconds
            )
        except Exception as e:
            log.error("Daily reset reconciliation recheck failed: %s", e)
            _log_daily_reset_result(
                None, current_date, "state_recheck_error", DAILY_RESET_FAILED, log.error
            )
            return DAILY_RESET_FAILED

        if outcome is not None:
            level = log.warning if outcome == DAILY_RESET_DEFERRED_CLOCK else log.info
            _log_daily_reset_result(
                stored_date, current_date, f"recheck_{decision}", outcome, level
            )
            return outcome

        try:
            reset_committed = _perform_daily_reset(
                now, stored_date, db_path=db_path
            )
        except Exception as e:
            log.error("Daily reset reconciliation failed: %s", e)
            _log_daily_reset_result(
                stored_date, current_date, "reset_error", DAILY_RESET_FAILED, log.error
            )
            return DAILY_RESET_FAILED

        if not reset_committed:
            latest_state = sqlm.fetch_system_state(db_path)
            latest_date = latest_state.get("system_date") if latest_state else None
            if latest_date == current_date:
                _log_daily_reset_result(
                    latest_date,
                    current_date,
                    "already_committed",
                    DAILY_RESET_NOT_DUE,
                )
                return DAILY_RESET_NOT_DUE

            _log_daily_reset_result(
                latest_date,
                current_date,
                "marker_changed",
                DAILY_RESET_FAILED,
                log.error,
            )
            return DAILY_RESET_FAILED

        _log_daily_reset_result(
            stored_date, current_date, "forward_date", DAILY_RESET_COMPLETED
        )
        return DAILY_RESET_COMPLETED
    finally:
        if quota_lock_acquired:
            qm.QUOTA_LOCK.release()
        qm.RESET_LOCK.release()


def daily_events(now):
    """Compatibility entry point; all daily resets use the coordinator."""
    return reconcile_daily_reset(now)


def most_recent_billing_boundary(now):
    """Return the most recent configured billing-day boundary."""
    current_date = now.date()
    if current_date.day >= qm.ACCOUNT_BILLING_DAY:
        return current_date.replace(day=qm.ACCOUNT_BILLING_DAY)

    previous_month = current_date.replace(day=1) - dt.timedelta(days=1)
    return previous_month.replace(day=qm.ACCOUNT_BILLING_DAY)


def monthly_reset_decision(now, system_state, startup_elapsed_seconds):
    _, clock_decision, clock_outcome = clock_gate_decision(
        now, system_state, startup_elapsed_seconds
    )
    current_boundary = most_recent_billing_boundary(now)
    current_boundary_text = current_boundary.isoformat()
    stored_boundary_text = (
        system_state.get("last_monthly_reset_date") if system_state else None
    )

    if clock_outcome is not None:
        return (
            stored_boundary_text,
            current_boundary_text,
            clock_decision,
            MONTHLY_RESET_DEFERRED_CLOCK,
        )

    if stored_boundary_text is None:
        return None, current_boundary_text, "missing_marker", None

    try:
        stored_boundary = dt.date.fromisoformat(stored_boundary_text)
    except (TypeError, ValueError) as e:
        raise ValueError(
            f"Invalid persisted monthly reset boundary: {stored_boundary_text!r}"
        ) from e

    if current_boundary < stored_boundary:
        return (
            stored_boundary_text,
            current_boundary_text,
            "clock_behind_boundary",
            MONTHLY_RESET_DEFERRED_CLOCK,
        )
    if current_boundary == stored_boundary:
        return (
            stored_boundary_text,
            current_boundary_text,
            "same_boundary",
            MONTHLY_RESET_NOT_DUE,
        )

    return stored_boundary_text, current_boundary_text, "older_boundary", None


def _log_monthly_reset_result(
    stored_boundary, current_boundary, decision, outcome, level=None
):
    global _LAST_MONTHLY_RESET_RESULT
    result = (stored_boundary, current_boundary, decision, outcome)
    log_method = level or log.info
    if result == _LAST_MONTHLY_RESET_RESULT:
        log_method = log.debug
    else:
        _LAST_MONTHLY_RESET_RESULT = result

    log_method(
        "Monthly reset reconciliation: stored_boundary=%s "
        "current_boundary=%s decision=%s outcome=%s",
        stored_boundary,
        current_boundary,
        decision,
        outcome,
    )


def _perform_monthly_reset(current_boundary, stored_boundary, db_path=None):
    qm.checkpoint_monthly_usage(db_path=db_path)
    log.info("User and system usage checkpoint complete before monthly reset.")
    return sqlm.usage_monthly_wipe_and_advance_marker(
        current_boundary, stored_boundary, db_path=db_path
    )


def reconcile_monthly_reset(now, *, startup_elapsed_seconds=None, db_path=None):
    """Reconcile one due billing-period reset and return its outcome."""
    if startup_elapsed_seconds is None:
        startup_elapsed_seconds = max(
            0.0, time.monotonic() - USAGE_TRACKER_STARTED_AT
        )

    try:
        system_state = sqlm.fetch_system_state(db_path)
        if system_state is None:
            raise RuntimeError("System state does not exist.")
        stored_boundary, current_boundary, decision, outcome = (
            monthly_reset_decision(
                now, system_state, startup_elapsed_seconds
            )
        )
    except Exception as e:
        log.error(
            "Monthly reset reconciliation failed before lock acquisition: %s", e
        )
        _log_monthly_reset_result(
            None, None, "state_error", MONTHLY_RESET_FAILED, log.error
        )
        return MONTHLY_RESET_FAILED

    if outcome is not None:
        level = (
            log.warning
            if outcome == MONTHLY_RESET_DEFERRED_CLOCK
            else log.info
        )
        _log_monthly_reset_result(
            stored_boundary, current_boundary, decision, outcome, level
        )
        return outcome

    if not qm.RESET_LOCK.acquire(blocking=False):
        _log_monthly_reset_result(
            stored_boundary,
            current_boundary,
            "reset_lock_busy",
            MONTHLY_RESET_BUSY,
        )
        return MONTHLY_RESET_BUSY

    quota_lock_acquired = False
    try:
        quota_lock_acquired = qm.QUOTA_LOCK.acquire(blocking=False)
        if not quota_lock_acquired:
            _log_monthly_reset_result(
                stored_boundary,
                current_boundary,
                "quota_lock_busy",
                MONTHLY_RESET_BUSY,
            )
            return MONTHLY_RESET_BUSY

        try:
            system_state = sqlm.fetch_system_state(db_path)
            if system_state is None:
                raise RuntimeError("System state does not exist.")
            stored_boundary, current_boundary, decision, outcome = (
                monthly_reset_decision(
                    now, system_state, startup_elapsed_seconds
                )
            )
        except Exception as e:
            log.error("Monthly reset reconciliation recheck failed: %s", e)
            _log_monthly_reset_result(
                None,
                None,
                "state_recheck_error",
                MONTHLY_RESET_FAILED,
                log.error,
            )
            return MONTHLY_RESET_FAILED

        if outcome is not None:
            level = (
                log.warning
                if outcome == MONTHLY_RESET_DEFERRED_CLOCK
                else log.info
            )
            _log_monthly_reset_result(
                stored_boundary,
                current_boundary,
                f"recheck_{decision}",
                outcome,
                level,
            )
            return outcome

        if stored_boundary is None:
            try:
                initialized = sqlm.initialize_monthly_reset_marker(
                    current_boundary, db_path=db_path
                )
            except Exception as e:
                log.error("Monthly reset baseline initialization failed: %s", e)
                _log_monthly_reset_result(
                    None,
                    current_boundary,
                    "baseline_error",
                    MONTHLY_RESET_FAILED,
                    log.error,
                )
                return MONTHLY_RESET_FAILED

            if initialized:
                log.info(
                    "Initialized conservative monthly reset migration baseline "
                    "at %s without changing usage totals.",
                    current_boundary,
                )
                _log_monthly_reset_result(
                    None,
                    current_boundary,
                    "migration_baseline",
                    MONTHLY_RESET_BASELINED,
                )
                return MONTHLY_RESET_BASELINED

            latest_state = sqlm.fetch_system_state(db_path)
            latest_boundary = (
                latest_state.get("last_monthly_reset_date")
                if latest_state
                else None
            )
            if latest_boundary == current_boundary:
                _log_monthly_reset_result(
                    latest_boundary,
                    current_boundary,
                    "already_baselined",
                    MONTHLY_RESET_NOT_DUE,
                )
                return MONTHLY_RESET_NOT_DUE

            _log_monthly_reset_result(
                latest_boundary,
                current_boundary,
                "baseline_marker_changed",
                MONTHLY_RESET_FAILED,
                log.error,
            )
            return MONTHLY_RESET_FAILED

        try:
            reset_committed = _perform_monthly_reset(
                current_boundary, stored_boundary, db_path=db_path
            )
        except Exception as e:
            log.error("Monthly reset reconciliation failed: %s", e)
            _log_monthly_reset_result(
                stored_boundary,
                current_boundary,
                "reset_error",
                MONTHLY_RESET_FAILED,
                log.error,
            )
            return MONTHLY_RESET_FAILED

        if not reset_committed:
            latest_state = sqlm.fetch_system_state(db_path)
            latest_boundary = (
                latest_state.get("last_monthly_reset_date")
                if latest_state
                else None
            )
            if latest_boundary == current_boundary:
                _log_monthly_reset_result(
                    latest_boundary,
                    current_boundary,
                    "already_committed",
                    MONTHLY_RESET_NOT_DUE,
                )
                return MONTHLY_RESET_NOT_DUE

            _log_monthly_reset_result(
                latest_boundary,
                current_boundary,
                "marker_changed",
                MONTHLY_RESET_FAILED,
                log.error,
            )
            return MONTHLY_RESET_FAILED

        _log_monthly_reset_result(
            stored_boundary,
            current_boundary,
            "older_boundary",
            MONTHLY_RESET_COMPLETED,
        )
        return MONTHLY_RESET_COMPLETED
    finally:
        if quota_lock_acquired:
            qm.QUOTA_LOCK.release()
        qm.RESET_LOCK.release()


def monthly_events(now=None):
    """Compatibility entry point; all monthly resets use the coordinator."""
    if now is None:
        tz = dt.timezone(dt.timedelta(hours=UTC_OFFSET))
        now = dt.datetime.now(tz)
    return reconcile_monthly_reset(now)


def usage_updater(stop_event: threading.Event):

    # Initialize continuously updated variables
    quota_dict = {}
    usage_dict = {}

    num_users = 0
    num_groups = 0

    config = sqlm.fetch_active_config()

    if config is None:
        log.warning("usage_updater: System config not loaded.")
        raise RuntimeError("usage_updater: System config not loaded.")

    system_name = config["system_name"]

    qm.reconcile_system_usage_on_startup(system_name=system_name)

    while not stop_event.is_set():
        if stop_event.wait(USAGE_UPDATE_INTERVAL):
            break

        tz = dt.timezone(dt.timedelta(hours=UTC_OFFSET))
        now = dt.datetime.now(tz)
        reconcile_daily_reset(now)
        reconcile_monthly_reset(now)

        reset_lock_acquired = qm.RESET_LOCK.acquire(blocking=False)
        if not reset_lock_acquired:
            continue  # reset in progress, skip tick
        # log.debug(f"usage_updater: Acquired RESET_LOCK")
        try:
            quota_lock_acquired = qm.QUOTA_LOCK.acquire(timeout=0.1)
            if not quota_lock_acquired:
                continue  # admin is changing groups/quotas; skip tick
            # log.debug(f"usage_updater: Acquired QUOTA_LOCK")
            try:
                log.debug("Updating user byte totals...")
                usage_dict = qm.update_all_users_bytes(usage_dict)

                log.debug("Updating quota information for all users...")
                quota_dict = qm.update_quota_information_all_users(quota_dict)
                log.debug(quota_dict)

                log.debug("Enforcing quotas for all users...")
                qm.enforce_quotas_all_users(throttling=False)

                log.debug("Updating system byte totals...")
                qm.update_total_system_bytes()

                log.debug("Updating num entities system state...")
                num_users, num_groups = qm.update_num_entities_system_state(
                    num_users, num_groups
                )

            except qm.QuotaAllottmentError as e:
                log.error(f"usage_updater: Failed to execute usage update, error: {e}")
            finally:
                if quota_lock_acquired:
                    qm.QUOTA_LOCK.release()
                    # log.debug(f"usage_updater: Released QUOTA_LOCK")
        except Exception as e:
            log.error(f"usage_updater: Failed to execute usage update, error: {e}")
            stop_event.set()
            raise
        finally:
            if reset_lock_acquired:
                qm.RESET_LOCK.release()
                # log.debug(f"usage_updater: Released RESET_LOCK")


def start_usage_tracking(stop_event: threading.Event):
    """Start the wipe scheduler and usage updater threads"""
    global USAGE_TRACKER_STARTED_AT, _LAST_DAILY_RESET_RESULT
    global _LAST_MONTHLY_RESET_RESULT
    USAGE_TRACKER_STARTED_AT = time.monotonic()
    _LAST_DAILY_RESET_RESULT = None
    _LAST_MONTHLY_RESET_RESULT = None

    t_wipe_scheduler = threading.Thread(
        target=event_scheduler, args=(stop_event,), daemon=True
    )
    t_usage_updater = threading.Thread(
        target=usage_updater, args=(stop_event,), daemon=True
    )

    log.info("Usage tracking threads started")
    return [t_wipe_scheduler, t_usage_updater]
