import threading
import datetime as dt
import logging

import quota_manager.sql_management as sqlm
import quota_manager.quota_management as qm

from quota_manager.sqlite_helper_functions import UTC_OFFSET

USAGE_UPDATE_INTERVAL = 1
ONE_DAY = 1
ONE_MONTH = 1

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

        if now.day == qm.ACCOUNT_BILLING_DAY:
            monthly_events(now)

        daily_events(now)


def daily_events(now):

    sqlm.usage_daily_wipe()
    log.info("Daily wipe complete.")

    qm.log_out_all_users()
    log.info("All users logged out.")

    qm.wipe_ip_neigh_db()
    log.info("IP neigh db wiped.")

    qm.reset_throttling_and_packet_dropping_all_users()
    log.info("Throttling and packet dropping reset.")

    qm.update_group_quotas(now, qm.ACCOUNT_BILLING_DAY)
    log.info("Updated daily quotas for all groups.")


def monthly_events(now):
    sqlm.usage_monthly_wipe()
    log.info("Monthly wipe complete.")


def usage_updater(stop_event: threading.Event):

    while not stop_event.is_set():
        if stop_event.wait(USAGE_UPDATE_INTERVAL):
            break

        try:
            usage_update_event()

        except Exception:
            log.exception("usage_updater crashed during update loop.")
            stop_event.set()
            break


def usage_update_event():

    log.debug("Checking for missed system wipes...")
    updating_system_wipes()

    log.debug("Updating user byte totals...")
    usage_dict = qm.update_all_users_bytes()
    log.debug(usage_dict)

    log.debug("Updating system state...")
    system_state_update()

    log.debug("Updating quota information for all users...")
    quota_dict = qm.update_quota_information_all_users(quota_dict)

    log.debug("Enforcing quotas for all users...")
    qm.enforce_quotas_all_users(throttling=False)


def start_usage_tracking(stop_event: threading.Event):
    """Start the wipe scheduler and usage updater threads"""
    t_wipe_scheduler = threading.Thread(
        target=event_scheduler, args=(stop_event,), daemon=True
    )
    t_usage_updater = threading.Thread(
        target=usage_updater, args=(stop_event,), daemon=True
    )

    log.info("Usage tracking threads started")
    return [t_wipe_scheduler, t_usage_updater]


def updating_system_wipes():
    tz = dt.timezone(dt.timedelta(hours=UTC_OFFSET))
    now = dt.datetime.now(tz)

    date_str = now.date().isoformat()

    log.debug("Checking to see if system was daily wiped...")
    system_daily_wiped = qm.system_daily_wipe_check(now)
    if not system_daily_wiped:
        log.debug("System not daily wiped, wiping system...")
        daily_events(now)
        sqlm.update_system_state_usage(system_date=date_str)

    log.debug("Checking to see if system was monthly wiped...")
    system_monthly_wiped = qm.system_monthly_wipe_check()
    if not system_monthly_wiped:
        log.debug("System not monthly wiped, wiping system...")
        monthly_events(now)
        sqlm.update_system_state_usage(wiped_this_month=True)


def system_state_update():
    log.debug("Updating num_users, num_groups...")
    qm.update_num_entities_system_state()
