import sqlite3
import threading

import quota_manager.quota_management as qm
import quota_manager.usage_tracker as ut


def _system_name():
    return qm.sqlm.fetch_active_config()["system_name"]


def _set_system_state(
    usage_db,
    *,
    daily,
    monthly,
    all_time,
    true_monthly,
    session_start,
    session_total,
):
    with sqlite3.connect(usage_db) as con:
        con.execute(
            """
            UPDATE system_state
            SET total_daily_bytes=?, total_monthly_bytes=?, all_time_bytes=?,
                total_system_monthly_bytes=?, session_start_bytes=?,
                session_total_bytes=?
            WHERE system_name=?
            """,
            (
                daily,
                monthly,
                all_time,
                true_monthly,
                session_start,
                session_total,
                _system_name(),
            ),
        )


def _fetch_system_state(usage_db):
    with sqlite3.connect(usage_db) as con:
        row = con.execute(
            """
            SELECT total_daily_bytes, total_monthly_bytes, all_time_bytes,
                   total_system_monthly_bytes, session_start_bytes,
                   session_total_bytes
            FROM system_state
            WHERE system_name=?
            """,
            (_system_name(),),
        ).fetchone()

    return {
        "daily": row[0],
        "monthly": row[1],
        "all_time": row[2],
        "true_monthly": row[3],
        "session_start": row[4],
        "session_total": row[5],
    }


def _run_startup_only():
    stop_event = threading.Event()
    stop_event.set()
    ut.usage_updater(stop_event)


def test_restart_persists_outstanding_positive_delta_once(db_paths, monkeypatch):
    usage_db, _ = db_paths
    _set_system_state(
        usage_db,
        daily=1200,
        monthly=5400,
        all_time=9000,
        true_monthly=3000,
        session_start=1000,
        session_total=400,
    )
    monkeypatch.setattr(
        qm.nftm, "get_system_bytes_subprocess", lambda *args: 1700
    )

    _run_startup_only()
    first_restart = _fetch_system_state(usage_db)
    _run_startup_only()
    second_restart = _fetch_system_state(usage_db)

    assert first_restart == {
        "daily": 1200,
        "monthly": 5400,
        "all_time": 9000,
        "true_monthly": 3300,
        "session_start": 1000,
        "session_total": 700,
    }
    assert second_restart == first_restart


def test_restart_with_no_new_bytes_preserves_totals(db_paths, monkeypatch):
    usage_db, _ = db_paths
    _set_system_state(
        usage_db,
        daily=1200,
        monthly=5400,
        all_time=9000,
        true_monthly=3000,
        session_start=1000,
        session_total=400,
    )
    monkeypatch.setattr(
        qm.nftm, "get_system_bytes_subprocess", lambda *args: 1400
    )

    before = _fetch_system_state(usage_db)
    _run_startup_only()
    after = _fetch_system_state(usage_db)

    assert after == before


def test_restart_after_counter_reset_preserves_committed_totals(
    db_paths, monkeypatch
):
    usage_db, _ = db_paths
    _set_system_state(
        usage_db,
        daily=1200,
        monthly=5400,
        all_time=9000,
        true_monthly=3000,
        session_start=1000,
        session_total=400,
    )
    monkeypatch.setattr(
        qm.nftm, "get_system_bytes_subprocess", lambda *args: 300
    )

    _run_startup_only()
    after = _fetch_system_state(usage_db)

    assert after == {
        "daily": 1200,
        "monthly": 5400,
        "all_time": 9000,
        "true_monthly": 3000,
        "session_start": 300,
        "session_total": 0,
    }


def test_first_install_establishes_baseline_without_billing_history(
    db_paths, monkeypatch
):
    usage_db, _ = db_paths
    _set_system_state(
        usage_db,
        daily=0,
        monthly=0,
        all_time=0,
        true_monthly=0,
        session_start=0,
        session_total=0,
    )
    monkeypatch.setattr(
        qm.nftm, "get_system_bytes_subprocess", lambda *args: 800
    )

    _run_startup_only()
    after = _fetch_system_state(usage_db)

    assert after == {
        "daily": 0,
        "monthly": 0,
        "all_time": 0,
        "true_monthly": 0,
        "session_start": 800,
        "session_total": 0,
    }
