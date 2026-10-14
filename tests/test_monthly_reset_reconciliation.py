import datetime as dt
import sqlite3
import threading

import pytest

import quota_manager.quota_management as qm
import quota_manager.sql_management as sqlm
import quota_manager.usage_tracker as ut


TZ = dt.timezone(dt.timedelta(hours=2))
BILLING_BOUNDARY = dt.datetime(2026, 3, 7, 0, 5, tzinfo=TZ)


def _seed_totals(
    usage_db,
    *,
    system_date="2026-03-07",
    monthly_marker="2026-02-07",
):
    sqlm.create_group_usage("alpha", 1.0, db_path=usage_db)
    sqlm.create_user_usage("bob", "alpha", db_path=usage_db)

    with sqlite3.connect(usage_db) as con:
        con.execute(
            """
            UPDATE users
            SET daily_usage_bytes=101, monthly_usage_bytes=202,
                all_time_bytes=303, logged_in=1
            WHERE username='bob'
            """
        )
        con.execute(
            """
            UPDATE system_state
            SET system_date=?, total_daily_bytes=101,
                total_monthly_bytes=202, all_time_bytes=303,
                total_system_monthly_bytes=404,
                last_monthly_reset_date=?
            """,
            (system_date, monthly_marker),
        )


def _snapshot(usage_db):
    with sqlite3.connect(usage_db) as con:
        user = con.execute(
            """
            SELECT daily_usage_bytes, monthly_usage_bytes, all_time_bytes
            FROM users WHERE username='bob'
            """
        ).fetchone()
        system = con.execute(
            """
            SELECT system_date, total_daily_bytes, total_monthly_bytes,
                   all_time_bytes, total_system_monthly_bytes,
                   last_monthly_reset_date
            FROM system_state
            """
        ).fetchone()

    return {
        "user_daily": user[0],
        "user_monthly": user[1],
        "user_all_time": user[2],
        "system_date": system[0],
        "system_daily": system[1],
        "system_monthly": system[2],
        "system_all_time": system[3],
        "system_true_monthly": system[4],
        "monthly_marker": system[5],
    }


def _patch_monthly_checkpoint(monkeypatch, callback=None):
    callback = callback or (lambda *args, **kwargs: {})
    monkeypatch.setattr(qm, "checkpoint_monthly_usage", callback)


def _patch_daily_side_effects(monkeypatch, checkpoint):
    monkeypatch.setattr(qm, "checkpoint_all_logged_in_users", checkpoint)
    monkeypatch.setattr(qm, "log_out_all_users", lambda *args, **kwargs: None)
    monkeypatch.setattr(qm, "nftm_flush_set_ghosts", lambda *args, **kwargs: None)
    monkeypatch.setattr(qm, "wipe_ip_neigh_db", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        qm,
        "reset_throttling_and_packet_dropping_all_users",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        qm,
        "calculate_hypothetical_group_quotas_for_today",
        lambda *args, **kwargs: {},
    )
    monkeypatch.setattr(qm, "apply_new_quotas", lambda *args, **kwargs: None)
    monkeypatch.setattr(qm, "update_daily_byte_budget", lambda *args, **kwargs: None)


def _assert_daily_and_all_time_unchanged(before, after):
    assert after["user_daily"] == before["user_daily"]
    assert after["user_all_time"] == before["user_all_time"]
    assert after["system_daily"] == before["system_daily"]
    assert after["system_all_time"] == before["system_all_time"]


def test_populated_legacy_database_migrates_without_data_loss(
    db_paths, monkeypatch
):
    usage_db, _ = db_paths
    sqlm.create_group_usage("alpha", 1.0, db_path=usage_db)
    sqlm.create_user_usage("bob", "alpha", db_path=usage_db)

    with sqlite3.connect(usage_db) as con:
        con.execute(
            """
            UPDATE users
            SET daily_usage_bytes=101, monthly_usage_bytes=202,
                all_time_bytes=303
            WHERE username='bob'
            """
        )
        con.execute("DROP TABLE system_state")
        con.execute(
            """
            CREATE TABLE system_state (
                system_name TEXT PRIMARY KEY,
                system_date TEXT NOT NULL,
                wiped_this_month INTEGER NOT NULL,
                total_daily_bytes INTEGER,
                total_monthly_bytes INTEGER,
                all_time_bytes INTEGER,
                num_users INTEGER,
                num_groups INTEGER,
                total_system_monthly_bytes INTEGER,
                session_start_bytes INTEGER,
                session_total_bytes INTEGER,
                daily_budget_bytes INTEGER,
                UNIQUE(system_name)
            )
            """
        )
        con.execute(
            """
            INSERT INTO system_state
            VALUES ('dbtti', '2026-03-07', 1, 101, 202, 303,
                    1, 1, 404, 505, 606, 707)
            """
        )

    sqlm.init_usage_db()
    sqlm.init_usage_db()

    with sqlite3.connect(usage_db) as con:
        columns = {
            row[1] for row in con.execute("PRAGMA table_info(system_state)")
        }
        user_totals = con.execute(
            """
            SELECT daily_usage_bytes, monthly_usage_bytes, all_time_bytes
            FROM users WHERE username='bob'
            """
        ).fetchone()
        system_totals = con.execute(
            """
            SELECT total_daily_bytes, total_monthly_bytes, all_time_bytes,
                   total_system_monthly_bytes, session_start_bytes,
                   session_total_bytes, daily_budget_bytes,
                   last_monthly_reset_date
            FROM system_state
            """
        ).fetchone()

    assert "last_monthly_reset_date" in columns
    assert user_totals == (101, 202, 303)
    assert system_totals == (101, 202, 303, 404, 505, 606, 707, None)

    monkeypatch.setattr(
        qm,
        "checkpoint_monthly_usage",
        lambda *args, **kwargs: pytest.fail("migration baseline must not wipe"),
    )
    outcome = ut.reconcile_monthly_reset(
        BILLING_BOUNDARY, startup_elapsed_seconds=600, db_path=usage_db
    )

    assert outcome == ut.MONTHLY_RESET_BASELINED
    after = _snapshot(usage_db)
    assert after["monthly_marker"] == "2026-03-07"
    assert after["user_monthly"] == 202
    assert after["system_monthly"] == 202
    assert after["system_true_monthly"] == 404


def test_monthly_checkpoint_requests_user_and_system_samples(monkeypatch):
    calls = []
    monkeypatch.setattr(
        qm,
        "checkpoint_all_logged_in_users",
        lambda db_path=None: calls.append(("users", db_path)) or {"bob": 123},
    )
    monkeypatch.setattr(
        qm,
        "update_total_system_bytes",
        lambda db_path=None: calls.append(("system", db_path)),
    )

    result = qm.checkpoint_monthly_usage(db_path="usage.db")

    assert result == {"bob": 123}
    assert calls == [("users", "usage.db"), ("system", "usage.db")]


def test_before_boundary_is_not_due(db_paths, monkeypatch):
    usage_db, _ = db_paths
    _seed_totals(
        usage_db,
        system_date="2026-03-05",
        monthly_marker="2026-02-07",
    )
    _patch_monthly_checkpoint(monkeypatch)
    before = _snapshot(usage_db)
    now = dt.datetime(2026, 3, 5, 12, 0, tzinfo=TZ)

    outcome = ut.reconcile_monthly_reset(
        now, startup_elapsed_seconds=600, db_path=usage_db
    )

    assert outcome == ut.MONTHLY_RESET_NOT_DUE
    assert _snapshot(usage_db) == before


def test_due_boundary_checkpoints_and_resets_only_monthly_totals(
    db_paths, monkeypatch
):
    usage_db, _ = db_paths
    _seed_totals(usage_db)
    checkpoint_calls = []
    _patch_monthly_checkpoint(
        monkeypatch,
        lambda *args, **kwargs: checkpoint_calls.append("checkpoint"),
    )
    before = _snapshot(usage_db)

    outcome = ut.reconcile_monthly_reset(
        BILLING_BOUNDARY, startup_elapsed_seconds=600, db_path=usage_db
    )
    after = _snapshot(usage_db)

    assert outcome == ut.MONTHLY_RESET_COMPLETED
    assert checkpoint_calls == ["checkpoint"]
    assert after["user_monthly"] == 0
    assert after["system_monthly"] == 0
    assert after["system_true_monthly"] == 0
    assert after["monthly_marker"] == "2026-03-07"
    _assert_daily_and_all_time_unchanged(before, after)


def test_same_cycle_restart_is_not_due(db_paths, monkeypatch):
    usage_db, _ = db_paths
    _seed_totals(usage_db, monthly_marker="2026-03-07")
    _patch_monthly_checkpoint(monkeypatch)
    before = _snapshot(usage_db)

    outcome = ut.reconcile_monthly_reset(
        dt.datetime(2026, 3, 20, 8, 0, tzinfo=TZ),
        startup_elapsed_seconds=600,
        db_path=usage_db,
    )

    assert outcome == ut.MONTHLY_RESET_NOT_DUE
    assert _snapshot(usage_db) == before


def test_multiple_missed_cycles_require_one_catch_up(db_paths, monkeypatch):
    usage_db, _ = db_paths
    _seed_totals(usage_db, monthly_marker="2025-12-07")
    checkpoint_calls = []
    _patch_monthly_checkpoint(
        monkeypatch,
        lambda *args, **kwargs: checkpoint_calls.append("checkpoint"),
    )
    now = dt.datetime(2026, 3, 20, 8, 0, tzinfo=TZ)

    first = ut.reconcile_monthly_reset(
        now, startup_elapsed_seconds=600, db_path=usage_db
    )
    second = ut.reconcile_monthly_reset(
        now, startup_elapsed_seconds=600, db_path=usage_db
    )

    assert first == ut.MONTHLY_RESET_COMPLETED
    assert second == ut.MONTHLY_RESET_NOT_DUE
    assert checkpoint_calls == ["checkpoint"]
    assert _snapshot(usage_db)["monthly_marker"] == "2026-03-07"


@pytest.mark.parametrize(
    ("system_date", "monthly_marker", "now", "elapsed"),
    [
        (
            "2026-03-05",
            "2026-03-07",
            dt.datetime(2026, 3, 5, 12, 0, tzinfo=TZ),
            600,
        ),
        (
            "2026-03-06",
            "2026-02-07",
            BILLING_BOUNDARY,
            ut.DAILY_RESET_STARTUP_GRACE_SECONDS - 1,
        ),
    ],
)
def test_backward_or_untrusted_clock_defers_without_changes(
    db_paths,
    monkeypatch,
    system_date,
    monthly_marker,
    now,
    elapsed,
):
    usage_db, _ = db_paths
    _seed_totals(
        usage_db,
        system_date=system_date,
        monthly_marker=monthly_marker,
    )
    _patch_monthly_checkpoint(monkeypatch)
    before = _snapshot(usage_db)

    outcome = ut.reconcile_monthly_reset(
        now, startup_elapsed_seconds=elapsed, db_path=usage_db
    )

    assert outcome == ut.MONTHLY_RESET_DEFERRED_CLOCK
    assert _snapshot(usage_db) == before


def test_lock_contention_leaves_marker_for_retry(db_paths, monkeypatch):
    usage_db, _ = db_paths
    _seed_totals(usage_db)
    _patch_monthly_checkpoint(monkeypatch)
    reset_lock = threading.Lock()
    monkeypatch.setattr(qm, "RESET_LOCK", reset_lock)
    reset_lock.acquire()

    busy = ut.reconcile_monthly_reset(
        BILLING_BOUNDARY, startup_elapsed_seconds=600, db_path=usage_db
    )
    assert busy == ut.MONTHLY_RESET_BUSY
    assert _snapshot(usage_db)["monthly_marker"] == "2026-02-07"

    reset_lock.release()
    retry = ut.reconcile_monthly_reset(
        BILLING_BOUNDARY, startup_elapsed_seconds=600, db_path=usage_db
    )

    assert retry == ut.MONTHLY_RESET_COMPLETED
    assert _snapshot(usage_db)["monthly_marker"] == "2026-03-07"


def test_reset_failure_rolls_back_marker_and_retries(db_paths, monkeypatch):
    usage_db, _ = db_paths
    _seed_totals(usage_db)
    _patch_monthly_checkpoint(monkeypatch)
    with sqlite3.connect(usage_db) as con:
        con.execute(
            """
            CREATE TRIGGER fail_monthly_reset
            BEFORE UPDATE OF monthly_usage_bytes ON users
            BEGIN
                SELECT RAISE(ABORT, 'simulated monthly wipe failure');
            END;
            """
        )
    before = _snapshot(usage_db)

    failed = ut.reconcile_monthly_reset(
        BILLING_BOUNDARY, startup_elapsed_seconds=600, db_path=usage_db
    )
    after_failure = _snapshot(usage_db)

    with sqlite3.connect(usage_db) as con:
        con.execute("DROP TRIGGER fail_monthly_reset")

    retry = ut.reconcile_monthly_reset(
        BILLING_BOUNDARY, startup_elapsed_seconds=600, db_path=usage_db
    )
    after_retry = _snapshot(usage_db)

    assert failed == ut.MONTHLY_RESET_FAILED
    assert after_failure == before
    assert retry == ut.MONTHLY_RESET_COMPLETED
    assert after_retry["monthly_marker"] == "2026-03-07"
    _assert_daily_and_all_time_unchanged(before, after_retry)


def test_daily_and_monthly_due_together_serialize_and_complete_once(
    db_paths, monkeypatch
):
    usage_db, _ = db_paths
    _seed_totals(
        usage_db,
        system_date="2026-03-06",
        monthly_marker="2026-02-07",
    )
    daily_checkpoint_started = threading.Event()
    release_daily_checkpoint = threading.Event()
    daily_checkpoint_calls = []
    monthly_checkpoint_calls = []

    def blocking_daily_checkpoint(*args, **kwargs):
        daily_checkpoint_calls.append("checkpoint")
        daily_checkpoint_started.set()
        assert release_daily_checkpoint.wait(timeout=2)
        return {}

    _patch_daily_side_effects(monkeypatch, blocking_daily_checkpoint)
    _patch_monthly_checkpoint(
        monkeypatch,
        lambda *args, **kwargs: monthly_checkpoint_calls.append("checkpoint"),
    )
    daily_outcomes = []

    worker = threading.Thread(
        target=lambda: daily_outcomes.append(
            ut.reconcile_daily_reset(
                BILLING_BOUNDARY,
                startup_elapsed_seconds=600,
                db_path=usage_db,
            )
        )
    )
    worker.start()
    assert daily_checkpoint_started.wait(timeout=2)

    monthly_while_daily_runs = ut.reconcile_monthly_reset(
        BILLING_BOUNDARY, startup_elapsed_seconds=600, db_path=usage_db
    )
    release_daily_checkpoint.set()
    worker.join(timeout=2)
    assert not worker.is_alive()

    monthly_retry = ut.reconcile_monthly_reset(
        BILLING_BOUNDARY, startup_elapsed_seconds=600, db_path=usage_db
    )
    daily_repeat = ut.reconcile_daily_reset(
        BILLING_BOUNDARY, startup_elapsed_seconds=600, db_path=usage_db
    )
    monthly_repeat = ut.reconcile_monthly_reset(
        BILLING_BOUNDARY, startup_elapsed_seconds=600, db_path=usage_db
    )
    after = _snapshot(usage_db)

    assert daily_outcomes == [ut.DAILY_RESET_COMPLETED]
    assert monthly_while_daily_runs == ut.MONTHLY_RESET_BUSY
    assert monthly_retry == ut.MONTHLY_RESET_COMPLETED
    assert daily_repeat == ut.DAILY_RESET_NOT_DUE
    assert monthly_repeat == ut.MONTHLY_RESET_NOT_DUE
    assert daily_checkpoint_calls == ["checkpoint"]
    assert monthly_checkpoint_calls == ["checkpoint"]
    assert after["system_date"] == "2026-03-07"
    assert after["monthly_marker"] == "2026-03-07"
    assert after["user_daily"] == 0
    assert after["user_monthly"] == 0
