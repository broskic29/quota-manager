import datetime as dt
import logging
import sqlite3
import threading

import pytest

import quota_manager.quota_management as qm
import quota_manager.sql_management as sqlm
import quota_manager.usage_tracker as ut


TZ = dt.timezone(dt.timedelta(hours=2))
NOW = dt.datetime(2026, 3, 10, 12, 0, tzinfo=TZ)


def _seed_usage(usage_db, radius_db):
    sqlm.create_group_usage("alpha", 1.0, db_path=usage_db)
    sqlm.create_user_usage(
        "bob",
        "alpha",
        mac_address="aa:bb:cc:dd:ee:01",
        ip_address="10.0.0.2",
        db_path=usage_db,
    )
    sqlm.create_user_usage(
        "alice",
        "alpha",
        mac_address="aa:bb:cc:dd:ee:02",
        ip_address="10.0.0.3",
        db_path=usage_db,
    )

    with sqlite3.connect(usage_db) as con:
        con.execute(
            """
            UPDATE users
            SET daily_usage_bytes=100, monthly_usage_bytes=200,
                session_total_bytes=40, all_time_bytes=300,
                session_start_bytes=900, logged_in=0, exceeds_quota=1
            WHERE username='bob'
            """
        )
        con.execute(
            """
            UPDATE users
            SET daily_usage_bytes=50, monthly_usage_bytes=70,
                session_total_bytes=20, all_time_bytes=90,
                session_start_bytes=400, logged_in=0, exceeds_quota=0
            WHERE username='alice'
            """
        )
        con.execute(
            """
            UPDATE system_state
            SET system_date='2026-03-09', total_daily_bytes=150,
                total_monthly_bytes=270, all_time_bytes=390,
                total_system_monthly_bytes=999,
                last_monthly_reset_date='2026-02-07'
            """
        )

    with sqlite3.connect(radius_db) as con:
        con.execute(
            """
            INSERT INTO radcheck (username, attribute, op, value)
            VALUES ('bob', 'Cleartext-Password', ':=', 'secret')
            """
        )


def _snapshot(usage_db, radius_db):
    with sqlite3.connect(usage_db) as con:
        bob = con.execute(
            """
            SELECT username, mac_address, ip_address, daily_usage_bytes,
                   monthly_usage_bytes, session_total_bytes, all_time_bytes,
                   session_start_bytes, logged_in, exceeds_quota
            FROM users WHERE username='bob'
            """
        ).fetchone()
        alice = con.execute(
            """
            SELECT daily_usage_bytes, monthly_usage_bytes, all_time_bytes,
                   session_total_bytes, session_start_bytes, logged_in
            FROM users WHERE username='alice'
            """
        ).fetchone()
        group_name = con.execute(
            """
            SELECT g.group_name
            FROM users u
            JOIN group_users gu ON gu.user_id = u.id
            JOIN groups g ON g.id = gu.group_id
            WHERE u.username='bob'
            """
        ).fetchone()[0]
        system = con.execute(
            """
            SELECT system_date, total_daily_bytes, total_monthly_bytes,
                   all_time_bytes, total_system_monthly_bytes,
                   last_monthly_reset_date
            FROM system_state
            """
        ).fetchone()

    with sqlite3.connect(radius_db) as con:
        radius = con.execute(
            """
            SELECT username, attribute, op, value
            FROM radcheck WHERE username='bob'
            """
        ).fetchall()

    return {
        "bob": bob,
        "alice": alice,
        "group": group_name,
        "system": system,
        "radius": radius,
    }


@pytest.mark.parametrize(
    ("scope", "expected_bob_daily", "expected_bob_monthly", "expected_system_daily", "expected_system_monthly"),
    [
        (qm.MANUAL_RESET_DAILY, 0, 200, 50, 270),
        (qm.MANUAL_RESET_MONTHLY, 100, 0, 150, 70),
        (qm.MANUAL_RESET_DAILY_AND_MONTHLY, 0, 0, 50, 70),
    ],
)
def test_selected_user_scopes_preserve_account_and_other_state(
    db_paths,
    caplog,
    scope,
    expected_bob_daily,
    expected_bob_monthly,
    expected_system_daily,
    expected_system_monthly,
):
    usage_db, radius_db = db_paths
    _seed_usage(usage_db, radius_db)
    before = _snapshot(usage_db, radius_db)
    caplog.set_level(logging.INFO)

    outcome = qm.manual_reset_user_usage(
        "bob", scope, audit_identity="admin-one", db_path=usage_db
    )
    after = _snapshot(usage_db, radius_db)

    assert outcome == qm.MANUAL_RESET_COMPLETED
    assert after["bob"][3] == expected_bob_daily
    assert after["bob"][4] == expected_bob_monthly
    assert after["system"][1] == expected_system_daily
    assert after["system"][2] == expected_system_monthly
    assert after["system"][4] == before["system"][4]

    # Identity, addresses, session state, quota state, all-time usage, group,
    # and RADIUS credentials are not part of a usage-forgiveness operation.
    preserved_bob_indexes = (0, 1, 2, 5, 6, 7, 8, 9)
    assert tuple(after["bob"][i] for i in preserved_bob_indexes) == tuple(
        before["bob"][i] for i in preserved_bob_indexes
    )
    assert after["group"] == before["group"]
    assert after["radius"] == before["radius"]
    assert after["alice"] == before["alice"]
    assert after["system"][3] == before["system"][3]
    assert "audit_identity=admin-one" in caplog.text
    assert f"reset_type={scope}" in caplog.text
    assert "outcome=completed" in caplog.text


def test_logged_in_user_checkpoints_final_delta_without_reappearance(
    db_paths, monkeypatch
):
    usage_db, radius_db = db_paths
    _seed_usage(usage_db, radius_db)
    with sqlite3.connect(usage_db) as con:
        con.execute(
            """
            UPDATE users
            SET logged_in=1, session_start_bytes=1000,
                session_total_bytes=0
            WHERE username='bob'
            """
        )

    monkeypatch.setattr(qm.nftm, "get_bytes_from_user", lambda ip: 1250)

    outcome = qm.manual_reset_user_usage(
        "bob",
        qm.MANUAL_RESET_DAILY,
        audit_identity="admin-two",
        db_path=usage_db,
    )
    after_reset = _snapshot(usage_db, radius_db)

    assert outcome == qm.MANUAL_RESET_COMPLETED
    assert after_reset["bob"][3] == 0
    assert after_reset["bob"][4] == 450
    assert after_reset["bob"][5] == 250
    assert after_reset["bob"][6] == 550
    assert after_reset["bob"][7] == 1000
    assert after_reset["bob"][8] == 1
    assert after_reset["system"][1] == 50
    assert after_reset["system"][2] == 520
    assert after_reset["system"][4] == 999

    qm.update_user_bytes("bob", usage_dict={}, db_path=usage_db)
    after_same_counter = _snapshot(usage_db, radius_db)
    assert after_same_counter == after_reset


def test_selected_user_missing_counter_fails_without_clearing(db_paths, monkeypatch):
    usage_db, radius_db = db_paths
    _seed_usage(usage_db, radius_db)
    with sqlite3.connect(usage_db) as con:
        con.execute("UPDATE users SET logged_in=1 WHERE username='bob'")
    before = _snapshot(usage_db, radius_db)

    monkeypatch.setattr(qm, "fetch_user_bytes", lambda username: None)
    outcome = qm.manual_reset_user_usage(
        "bob",
        qm.MANUAL_RESET_DAILY,
        audit_identity="admin-three",
        db_path=usage_db,
    )

    assert outcome == qm.MANUAL_RESET_FAILED
    assert _snapshot(usage_db, radius_db) == before


def test_selected_user_rejects_missing_user_and_invalid_scope(db_paths):
    usage_db, radius_db = db_paths
    _seed_usage(usage_db, radius_db)
    before = _snapshot(usage_db, radius_db)

    missing = qm.manual_reset_user_usage(
        "nobody",
        qm.MANUAL_RESET_DAILY,
        audit_identity="admin-four",
        db_path=usage_db,
    )
    invalid_scope = qm.manual_reset_user_usage(
        "bob", "arbitrary_column", audit_identity="admin-four", db_path=usage_db
    )

    assert missing == qm.MANUAL_RESET_INVALID_USER
    assert invalid_scope == qm.MANUAL_RESET_INVALID_SCOPE
    assert _snapshot(usage_db, radius_db) == before


def test_selected_user_busy_result_can_be_retried(db_paths, monkeypatch):
    usage_db, radius_db = db_paths
    _seed_usage(usage_db, radius_db)
    reset_lock = threading.Lock()
    monkeypatch.setattr(qm, "RESET_LOCK", reset_lock)
    reset_lock.acquire()

    busy = qm.manual_reset_user_usage(
        "bob",
        qm.MANUAL_RESET_DAILY,
        audit_identity="admin-five",
        db_path=usage_db,
    )
    assert busy == qm.MANUAL_RESET_BUSY
    assert _snapshot(usage_db, radius_db)["bob"][3] == 100

    reset_lock.release()
    completed = qm.manual_reset_user_usage(
        "bob",
        qm.MANUAL_RESET_DAILY,
        audit_identity="admin-five",
        db_path=usage_db,
    )
    assert completed == qm.MANUAL_RESET_COMPLETED
    assert _snapshot(usage_db, radius_db)["bob"][3] == 0


def test_selected_user_transaction_rolls_back_on_failure(db_paths):
    usage_db, radius_db = db_paths
    _seed_usage(usage_db, radius_db)
    before = _snapshot(usage_db, radius_db)
    with sqlite3.connect(usage_db) as con:
        con.execute(
            """
            CREATE TRIGGER fail_manual_user_reset
            BEFORE UPDATE OF total_daily_bytes ON system_state
            BEGIN
                SELECT RAISE(ABORT, 'simulated aggregate failure');
            END;
            """
        )

    outcome = qm.manual_reset_user_usage(
        "bob",
        qm.MANUAL_RESET_DAILY,
        audit_identity="admin-six",
        db_path=usage_db,
    )

    assert outcome == qm.MANUAL_RESET_FAILED
    assert _snapshot(usage_db, radius_db) == before


def test_selected_user_aggregate_subtraction_is_clamped_at_zero(db_paths):
    usage_db, radius_db = db_paths
    _seed_usage(usage_db, radius_db)
    with sqlite3.connect(usage_db) as con:
        con.execute(
            """
            UPDATE system_state
            SET total_daily_bytes=10, total_monthly_bytes=20
            """
        )

    outcome = qm.manual_reset_user_usage(
        "bob",
        qm.MANUAL_RESET_DAILY_AND_MONTHLY,
        audit_identity="admin-clamp",
        db_path=usage_db,
    )
    after = _snapshot(usage_db, radius_db)

    assert outcome == qm.MANUAL_RESET_COMPLETED
    assert after["system"][1] == 0
    assert after["system"][2] == 0


def test_global_daily_reset_preserves_other_periods_and_marks_date(
    db_paths, monkeypatch
):
    usage_db, radius_db = db_paths
    _seed_usage(usage_db, radius_db)
    before = _snapshot(usage_db, radius_db)
    checkpoint_calls = []
    monkeypatch.setattr(
        qm,
        "checkpoint_all_logged_in_users",
        lambda db_path=None: checkpoint_calls.append(db_path) or {},
    )

    outcome = qm.manual_reset_all_daily_usage(
        audit_identity="admin-seven",
        now=NOW,
        startup_elapsed_seconds=600,
        db_path=usage_db,
    )
    after = _snapshot(usage_db, radius_db)

    assert outcome == qm.MANUAL_RESET_COMPLETED
    assert checkpoint_calls == [usage_db]
    assert after["bob"][3] == 0
    assert after["alice"][0] == 0
    assert after["system"][0] == "2026-03-10"
    assert after["system"][1] == 0
    assert after["bob"][4] == before["bob"][4]
    assert after["alice"][1] == before["alice"][1]
    assert after["bob"][6] == before["bob"][6]
    assert after["system"][2:] == before["system"][2:]

    automatic_outcome = ut.reconcile_daily_reset(
        NOW, startup_elapsed_seconds=600, db_path=usage_db
    )
    assert automatic_outcome == ut.DAILY_RESET_NOT_DUE


def test_global_monthly_reset_preserves_daily_and_marks_boundary(
    db_paths, monkeypatch
):
    usage_db, radius_db = db_paths
    _seed_usage(usage_db, radius_db)
    before = _snapshot(usage_db, radius_db)
    checkpoint_calls = []
    monkeypatch.setattr(
        qm,
        "checkpoint_monthly_usage",
        lambda db_path=None: checkpoint_calls.append(db_path) or {},
    )

    outcome = qm.manual_reset_all_monthly_usage(
        audit_identity="admin-eight",
        now=NOW,
        startup_elapsed_seconds=600,
        db_path=usage_db,
    )
    after = _snapshot(usage_db, radius_db)

    assert outcome == qm.MANUAL_RESET_COMPLETED
    assert checkpoint_calls == [usage_db]
    assert after["bob"][4] == 0
    assert after["alice"][1] == 0
    assert after["system"][2] == 0
    assert after["system"][4] == 0
    assert after["system"][5] == "2026-03-07"
    assert after["bob"][3] == before["bob"][3]
    assert after["alice"][0] == before["alice"][0]
    assert after["bob"][6] == before["bob"][6]
    assert after["system"][0:2] == before["system"][0:2]
    assert after["system"][3] == before["system"][3]

    automatic_outcome = ut.reconcile_monthly_reset(
        NOW, startup_elapsed_seconds=600, db_path=usage_db
    )
    assert automatic_outcome == ut.MONTHLY_RESET_NOT_DUE
    assert checkpoint_calls == [usage_db]


@pytest.mark.parametrize(
    ("stored_date", "startup_elapsed", "expected_decision"),
    [
        ("2026-03-11", 600, "clock_behind"),
        ("2026-03-09", 1, "startup_grace"),
    ],
)
def test_global_daily_reset_defers_for_untrusted_clock(
    db_paths, caplog, stored_date, startup_elapsed, expected_decision
):
    usage_db, radius_db = db_paths
    _seed_usage(usage_db, radius_db)
    with sqlite3.connect(usage_db) as con:
        con.execute("UPDATE system_state SET system_date=?", (stored_date,))
    before = _snapshot(usage_db, radius_db)
    caplog.set_level(logging.INFO)

    outcome = qm.manual_reset_all_daily_usage(
        audit_identity="admin-nine",
        now=NOW,
        startup_elapsed_seconds=startup_elapsed,
        db_path=usage_db,
    )

    assert outcome == qm.MANUAL_RESET_DEFERRED_CLOCK
    assert _snapshot(usage_db, radius_db) == before
    assert expected_decision in caplog.text


def test_global_daily_transaction_failure_keeps_totals_and_marker(
    db_paths, monkeypatch
):
    usage_db, radius_db = db_paths
    _seed_usage(usage_db, radius_db)
    monkeypatch.setattr(
        qm, "checkpoint_all_logged_in_users", lambda db_path=None: {}
    )
    with sqlite3.connect(usage_db) as con:
        con.execute(
            """
            CREATE TRIGGER fail_manual_daily_reset
            BEFORE UPDATE OF daily_usage_bytes ON users
            BEGIN
                SELECT RAISE(ABORT, 'simulated daily failure');
            END;
            """
        )
    before = _snapshot(usage_db, radius_db)

    outcome = qm.manual_reset_all_daily_usage(
        audit_identity="admin-ten",
        now=NOW,
        startup_elapsed_seconds=600,
        db_path=usage_db,
    )

    assert outcome == qm.MANUAL_RESET_FAILED
    assert _snapshot(usage_db, radius_db) == before


def test_global_monthly_transaction_failure_keeps_totals_and_marker(
    db_paths, monkeypatch
):
    usage_db, radius_db = db_paths
    _seed_usage(usage_db, radius_db)
    monkeypatch.setattr(qm, "checkpoint_monthly_usage", lambda db_path=None: {})
    with sqlite3.connect(usage_db) as con:
        con.execute(
            """
            CREATE TRIGGER fail_manual_monthly_reset
            BEFORE UPDATE OF monthly_usage_bytes ON users
            BEGIN
                SELECT RAISE(ABORT, 'simulated monthly failure');
            END;
            """
        )
    before = _snapshot(usage_db, radius_db)

    outcome = qm.manual_reset_all_monthly_usage(
        audit_identity="admin-eleven",
        now=NOW,
        startup_elapsed_seconds=600,
        db_path=usage_db,
    )

    assert outcome == qm.MANUAL_RESET_FAILED
    assert _snapshot(usage_db, radius_db) == before
