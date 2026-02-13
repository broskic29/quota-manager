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
            monthly_events()

        daily_events(now)


def daily_events(now):

    sqlm.usage_daily_wipe()

    qm.log_out_all_users()

    qm.wipe_ip_neigh_db()

    qm.reset_throttling_and_packet_dropping_all_users()

    qm.update_group_quotas(now, qm.ACCOUNT_BILLING_DAY)


def monthly_events():
    sqlm.usage_monthly_wipe()


def usage_updater(stop_event: threading.Event):

    quota_dict = {}
    usage_dict = {}

    while not stop_event.is_set():
        if stop_event.wait(USAGE_UPDATE_INTERVAL):
            break

        try:
            tz = dt.timezone(dt.timedelta(hours=UTC_OFFSET))
            now = dt.datetime.now(tz)

            system_daily_wiped = qm.system_daily_wipe_check(now)
            if not system_daily_wiped:
                log.debug("System not daily wiped, wiping system...")
                daily_events(now)
                qm.update_system_date(now)

            system_monthly_wiped = qm.system_monthly_wipe_check()
            if not system_monthly_wiped:
                log.debug("System not monthly wiped, wiping system...")
                monthly_events()
                qm.update_monthly_wipe()

            usage_dict = qm.update_all_users_bytes(usage_dict)

            quota_dict = qm.update_quota_information_all_users(quota_dict)

            qm.enforce_quotas_all_users(throttling=False)
        except Exception as e:
            log.exception(f"usage_updater: System crashed during update loop: {e}")
            stop_event.set()
            break


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
