import logging

import quota_manager.quota_management as qm
import quota_manager.sqlite_helper_functions as sqlh


def test_missing_counter_does_not_logout(monkeypatch, caplog):
    username = "alice"
    user_ip = "192.0.2.10"
    logout_calls = []

    monkeypatch.setattr(
        qm.sqlm, "fetch_user_ip_address_usage", lambda requested: user_ip
    )

    def missing_counter(requested_ip):
        assert requested_ip == user_ip
        raise sqlh.IPAddressError(f"Usage bytes undefined for user {requested_ip}")

    monkeypatch.setattr(qm.nftm, "get_bytes_from_user", missing_counter)
    monkeypatch.setattr(qm, "log_out_user", logout_calls.append)

    with caplog.at_level(logging.WARNING, logger=qm.log.name):
        result = qm.fetch_user_bytes(username)

    assert result is None
    assert logout_calls == []
    assert username in caplog.text
    assert user_ip in caplog.text


def test_successful_counter_read_returns_bytes(monkeypatch):
    username = "alice"
    user_ip = "192.0.2.10"
    logout_calls = []

    monkeypatch.setattr(
        qm.sqlm, "fetch_user_ip_address_usage", lambda requested: user_ip
    )
    monkeypatch.setattr(qm.nftm, "get_bytes_from_user", lambda requested: 4096)
    monkeypatch.setattr(qm, "log_out_user", logout_calls.append)

    assert qm.fetch_user_bytes(username) == 4096
    assert logout_calls == []
