import datetime as dt
import sqlite3
import threading

import quota_manager.quota_management as qm
import quota_manager.sql_management as sqlm
import quota_manager.usage_tracker as ut


TZ = dt.timezone(dt.timedelta(hours=2))
RESET_DATE = dt.datetime(2026, 2, 10, 0, 5, tzinfo=TZ)


def _seed_totals(usage_db, stored_date):
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
                total_system_monthly_bytes=404
            """,
            (stored_date,),
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
                   all_time_bytes, total_system_monthly_bytes
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
    }


def _patch_reset_side_effects(monkeypatch, checkpoint=None):
    checkpoint = checkpoint or (lambda *args, **kwargs: {})
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


def _assert_long_term_totals_unchanged(before, after):
    assert after["user_monthly"] == before["user_monthly"]
    assert after["user_all_time"] == before["user_all_time"]
    assert after["system_monthly"] == before["system_monthly"]
    assert after["system_all_time"] == before["system_all_time"]
    assert after["system_true_monthly"] == before["system_true_monthly"]


def test_same_day_service_restart_is_not_due(db_paths, monkeypatch):
    usage_db, _ = db_paths
    _seed_totals(usage_db, "2026-02-10")
    _patch_reset_side_effects(monkeypatch)
    before = _snapshot(usage_db)

    outcome = ut.reconcile_daily_reset(
        RESET_DATE, startup_elapsed_seconds=600, db_path=usage_db
    )

    assert outcome == ut.DAILY_RESET_NOT_DUE
    assert _snapshot(usage_db) == before


def test_current_date_earlier_than_stored_date_defers(db_paths, monkeypatch):
    usage_db, _ = db_paths
    _seed_totals(usage_db, "2026-02-11")
    _patch_reset_side_effects(monkeypatch)
    before = _snapshot(usage_db)

    outcome = ut.reconcile_daily_reset(
        RESET_DATE, startup_elapsed_seconds=600, db_path=usage_db
    )

    assert outcome == ut.DAILY_RESET_DEFERRED_CLOCK
    assert _snapshot(usage_db) == before


def test_forward_date_during_startup_grace_defers(db_paths, monkeypatch):
    usage_db, _ = db_paths
    _seed_totals(usage_db, "2026-02-09")
    _patch_reset_side_effects(monkeypatch)
    before = _snapshot(usage_db)

    outcome = ut.reconcile_daily_reset(
        RESET_DATE,
        startup_elapsed_seconds=ut.DAILY_RESET_STARTUP_GRACE_SECONDS - 1,
        db_path=usage_db,
    )

    assert outcome == ut.DAILY_RESET_DEFERRED_CLOCK
    assert _snapshot(usage_db) == before


def test_genuine_missed_day_resets_daily_totals_once(db_paths, monkeypatch):
    usage_db, _ = db_paths
    _seed_totals(usage_db, "2026-02-09")
    checkpoint_calls = []
    _patch_reset_side_effects(
        monkeypatch,
        checkpoint=lambda *args, **kwargs: checkpoint_calls.append("checkpoint"),
    )
    before = _snapshot(usage_db)

    outcome = ut.reconcile_daily_reset(
        RESET_DATE,
        startup_elapsed_seconds=ut.DAILY_RESET_STARTUP_GRACE_SECONDS,
        db_path=usage_db,
    )
    after = _snapshot(usage_db)

    assert outcome == ut.DAILY_RESET_COMPLETED
    assert checkpoint_calls == ["checkpoint"]
    assert after["user_daily"] == 0
    assert after["system_daily"] == 0
    assert after["system_date"] == "2026-02-10"
    _assert_long_term_totals_unchanged(before, after)


def test_two_callers_cannot_complete_the_same_reset(db_paths, monkeypatch):
    usage_db, _ = db_paths
    _seed_totals(usage_db, "2026-02-09")
    checkpoint_started = threading.Event()
    release_checkpoint = threading.Event()

    def blocking_checkpoint(*args, **kwargs):
        checkpoint_started.set()
        assert release_checkpoint.wait(timeout=2)
        return {}

    _patch_reset_side_effects(monkeypatch, checkpoint=blocking_checkpoint)
    outcomes = []

    def first_caller():
        outcomes.append(
            ut.reconcile_daily_reset(
                RESET_DATE, startup_elapsed_seconds=600, db_path=usage_db
            )
        )

    worker = threading.Thread(target=first_caller)
    worker.start()
    assert checkpoint_started.wait(timeout=2)

    outcomes.append(
        ut.reconcile_daily_reset(
            RESET_DATE, startup_elapsed_seconds=600, db_path=usage_db
        )
    )
    release_checkpoint.set()
    worker.join(timeout=2)

    assert not worker.is_alive()
    assert sorted(outcomes) == sorted(
        [ut.DAILY_RESET_COMPLETED, ut.DAILY_RESET_BUSY]
    )
    assert _snapshot(usage_db)["system_date"] == "2026-02-10"


def test_lock_contention_is_retryable(db_paths, monkeypatch):
    usage_db, _ = db_paths
    _seed_totals(usage_db, "2026-02-09")
    _patch_reset_side_effects(monkeypatch)
    reset_lock = threading.Lock()
    monkeypatch.setattr(qm, "RESET_LOCK", reset_lock)
    reset_lock.acquire()

    busy_outcome = ut.reconcile_daily_reset(
        RESET_DATE, startup_elapsed_seconds=600, db_path=usage_db
    )
    assert busy_outcome == ut.DAILY_RESET_BUSY
    assert _snapshot(usage_db)["system_date"] == "2026-02-09"

    reset_lock.release()
    retry_outcome = ut.reconcile_daily_reset(
        RESET_DATE, startup_elapsed_seconds=600, db_path=usage_db
    )

    assert retry_outcome == ut.DAILY_RESET_COMPLETED
    assert _snapshot(usage_db)["system_date"] == "2026-02-10"


def test_reset_failure_leaves_marker_for_retry(db_paths, monkeypatch):
    usage_db, _ = db_paths
    _seed_totals(usage_db, "2026-02-09")
    _patch_reset_side_effects(monkeypatch)
    with sqlite3.connect(usage_db) as con:
        con.execute(
            """
            CREATE TRIGGER fail_daily_reset
            BEFORE UPDATE OF daily_usage_bytes ON users
            BEGIN
                SELECT RAISE(ABORT, 'simulated daily wipe failure');
            END;
            """
        )
    before = _snapshot(usage_db)

    failed_outcome = ut.reconcile_daily_reset(
        RESET_DATE, startup_elapsed_seconds=600, db_path=usage_db
    )
    after_failure = _snapshot(usage_db)

    with sqlite3.connect(usage_db) as con:
        con.execute("DROP TRIGGER fail_daily_reset")

    retry_outcome = ut.reconcile_daily_reset(
        RESET_DATE, startup_elapsed_seconds=600, db_path=usage_db
    )
    after_retry = _snapshot(usage_db)

    assert failed_outcome == ut.DAILY_RESET_FAILED
    assert after_failure == before
    assert retry_outcome == ut.DAILY_RESET_COMPLETED
    assert after_retry["user_daily"] == 0
    assert after_retry["system_daily"] == 0
    assert after_retry["system_date"] == "2026-02-10"
    _assert_long_term_totals_unchanged(before, after_retry)
