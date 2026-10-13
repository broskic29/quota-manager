import quota_manager.quota_management as qm
import quota_manager.sql_management as sqlm
import quota_manager.sqlite_helper_functions as sqlh


USERNAME = "bob"
USER_IP = "10.0.0.2"
START_BYTES = 1000
FINAL_BYTES = 2500
FINAL_DELTA = FINAL_BYTES - START_BYTES


def _create_logged_in_user(usage_db):
    sqlm.create_group_usage("alpha", 1.0, db_path=usage_db)
    sqlm.create_user_usage(USERNAME, "alpha", db_path=usage_db)
    sqlm.login_user_usage(
        USERNAME, "aa:bb:cc:dd:ee:ff", USER_IP, db_path=usage_db
    )
    sqlm.update_session_start_bytes(
        START_BYTES, username=USERNAME, db_path=usage_db
    )


def test_throttle_persists_final_delta_before_nft_transition(db_paths, monkeypatch):
    usage_db, _ = db_paths
    _create_logged_in_user(usage_db)
    usage_seen_by_nft = []

    monkeypatch.setattr(qm.nftm, "get_bytes_from_user", lambda ip: FINAL_BYTES)

    def throttle_ip(ip_addr):
        assert ip_addr == USER_IP
        usage_seen_by_nft.append(
            sqlm.fetch_daily_bytes_usage(USERNAME, db_path=usage_db)
        )

    monkeypatch.setattr(qm.nftm, "throttle_ip", throttle_ip)

    qm.throttle_single_user(USERNAME)

    assert usage_seen_by_nft == [FINAL_DELTA]
    assert sqlm.fetch_daily_bytes_usage(USERNAME, db_path=usage_db) == FINAL_DELTA


def test_drop_repeats_checkpoint_without_double_counting(db_paths, monkeypatch):
    usage_db, _ = db_paths
    _create_logged_in_user(usage_db)
    usage_seen_by_nft = []

    monkeypatch.setattr(qm.nftm, "get_bytes_from_user", lambda ip: FINAL_BYTES)

    assert qm.checkpoint_user_usage(USERNAME, db_path=usage_db) == FINAL_BYTES
    assert sqlm.fetch_daily_bytes_usage(USERNAME, db_path=usage_db) == FINAL_DELTA

    def drop_ip(ip_addr):
        assert ip_addr == USER_IP
        usage_seen_by_nft.append(
            sqlm.fetch_daily_bytes_usage(USERNAME, db_path=usage_db)
        )

    monkeypatch.setattr(qm.nftm, "drop_ip", drop_ip)

    qm.drop_single_user(USERNAME)

    assert usage_seen_by_nft == [FINAL_DELTA]
    assert sqlm.fetch_daily_bytes_usage(USERNAME, db_path=usage_db) == FINAL_DELTA


def test_logout_persists_final_delta_before_high_speed_delete(db_paths, monkeypatch):
    usage_db, _ = db_paths
    _create_logged_in_user(usage_db)
    usage_seen_at_high_speed_delete = []

    monkeypatch.setattr(qm.nftm, "get_bytes_from_user", lambda ip: FINAL_BYTES)

    def operation_on_set_element(operation, family, table, set_name, element):
        if operation == "delete" and set_name == qm.nftm.HIGH_SPEED_SET_NAME:
            usage_seen_at_high_speed_delete.append(
                sqlm.fetch_daily_bytes_usage(USERNAME, db_path=usage_db)
            )

    monkeypatch.setattr(qm.nftm, "operation_on_set_element", operation_on_set_element)
    monkeypatch.setattr(qm, "remove_user_from_ip_timeouts", lambda *args: None)

    assert qm.log_out_user(USERNAME) is True

    assert usage_seen_at_high_speed_delete == [FINAL_DELTA]
    assert sqlm.fetch_daily_bytes_usage(USERNAME, db_path=usage_db) == FINAL_DELTA
    assert sqlm.check_if_user_logged_in(USERNAME, db_path=usage_db) is False


def test_direct_high_speed_delete_persists_final_delta(db_paths, monkeypatch):
    usage_db, _ = db_paths
    _create_logged_in_user(usage_db)
    usage_seen_by_nft = []

    monkeypatch.setattr(qm.nftm, "get_bytes_from_user", lambda ip: FINAL_BYTES)

    def operation_on_set_element(operation, family, table, set_name, element):
        assert operation == "delete"
        assert set_name == qm.nftm.HIGH_SPEED_SET_NAME
        assert element == USER_IP
        usage_seen_by_nft.append(
            sqlm.fetch_daily_bytes_usage(USERNAME, db_path=usage_db)
        )

    monkeypatch.setattr(qm.nftm, "operation_on_set_element", operation_on_set_element)

    qm.delete_user_from_set(USERNAME, qm.nftm.HIGH_SPEED_SET_NAME)

    assert usage_seen_by_nft == [FINAL_DELTA]
    assert sqlm.fetch_daily_bytes_usage(USERNAME, db_path=usage_db) == FINAL_DELTA


def test_missing_counter_checkpoint_does_not_logout_user(db_paths, monkeypatch):
    usage_db, _ = db_paths
    _create_logged_in_user(usage_db)
    logout_calls = []

    def missing_counter(ip_addr):
        assert ip_addr == USER_IP
        raise sqlh.IPAddressError(f"Usage bytes undefined for user {ip_addr}")

    monkeypatch.setattr(qm.nftm, "get_bytes_from_user", missing_counter)
    monkeypatch.setattr(qm, "log_out_user", logout_calls.append)

    assert qm.checkpoint_user_usage(USERNAME, db_path=usage_db) is None
    assert sqlm.fetch_daily_bytes_usage(USERNAME, db_path=usage_db) == 0
    assert sqlm.check_if_user_logged_in(USERNAME, db_path=usage_db) is True
    assert logout_calls == []
