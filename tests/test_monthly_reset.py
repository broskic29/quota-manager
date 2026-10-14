import sqlite3
import datetime as dt

import quota_manager.quota_management as qm
import quota_manager.sql_management as sqlm
import quota_manager.usage_tracker as ut


def test_monthly_events_resets_monthly_and_clears_temporary_quota(
    db_paths, monkeypatch
):
    usage_db, _ = db_paths

    sqlm.create_group_usage("alpha", 1.0, db_path=usage_db)
    sqlm.create_user_usage("bob", "alpha", db_path=usage_db)

    with sqlite3.connect(usage_db) as con:
        con.execute(
            """
            UPDATE users
            SET daily_usage_bytes = 111,
                monthly_usage_bytes = 222
            WHERE username = 'bob'
            """
        )
        con.execute(
            """
            UPDATE system_state
            SET system_date = '2026-03-07',
                last_monthly_reset_date = '2026-02-07'
            """
        )

    monkeypatch.setattr(qm, "checkpoint_monthly_usage", lambda *a, **k: {})

    tz = dt.timezone(dt.timedelta(hours=2))
    now = dt.datetime(2026, 3, 7, 0, 1, tzinfo=tz)  # billing day example
    outcome = ut.monthly_events(now)

    with sqlite3.connect(usage_db) as con:
        row = con.execute(
            "SELECT daily_usage_bytes, monthly_usage_bytes FROM users WHERE username='bob'"
        ).fetchone()

    daily, monthly = row
    assert outcome == ut.MONTHLY_RESET_COMPLETED
    assert daily == 111, "Monthly wipe should not touch daily usage"
    assert monthly == 0
