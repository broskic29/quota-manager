from types import SimpleNamespace

from pyroute2.netlink.rtnl.ndmsg import (
    NUD_DELAY,
    NUD_FAILED,
    NUD_INCOMPLETE,
    NUD_PROBE,
    NUD_REACHABLE,
    NUD_STALE,
)

import quota_manager.ip_neigh_timeout_listener as listener
import quota_manager.quota_management as qm


def _neighbor(ip_addr, mac_addr, state):
    return {
        "state": state,
        "attrs": [("NDA_DST", ip_addr), ("NDA_LLADDR", mac_addr)],
    }


def test_poll_ip_neigh_returns_all_usable_neighbors(monkeypatch):
    neighbors = [
        _neighbor("192.0.2.10", "00:00:00:00:00:10", NUD_REACHABLE),
        _neighbor("192.0.2.11", "00:00:00:00:00:11", NUD_STALE),
        _neighbor("192.0.2.12", "00:00:00:00:00:12", NUD_DELAY),
        _neighbor("192.0.2.13", "00:00:00:00:00:13", NUD_PROBE),
        _neighbor("192.0.2.14", "00:00:00:00:00:14", NUD_FAILED),
        _neighbor("192.0.2.15", "00:00:00:00:00:15", NUD_INCOMPLETE),
    ]
    monkeypatch.setattr(qm, "ip", SimpleNamespace(get_neighbours=lambda: neighbors))
    monkeypatch.setattr(qm.time, "monotonic", lambda: 100.0)

    assert qm.poll_ip_neigh() == [
        ("192.0.2.10", "00:00:00:00:00:10", 100.0),
        ("192.0.2.11", "00:00:00:00:00:11", 100.0),
        ("192.0.2.12", "00:00:00:00:00:12", 100.0),
        ("192.0.2.13", "00:00:00:00:00:13", 100.0),
    ]


def test_listener_updates_every_observed_neighbor(monkeypatch):
    observations = [
        ("192.0.2.10", "00:00:00:00:00:10", 100.0),
        ("192.0.2.11", "00:00:00:00:00:11", 100.0),
    ]
    updates = []

    class OneCycleStopEvent:
        def __init__(self):
            self.checks = 0

        def is_set(self):
            self.checks += 1
            return self.checks > 1

        def wait(self, _timeout):
            return False

    monkeypatch.setattr(listener, "poll_ip_neigh", lambda: observations)
    monkeypatch.setattr(
        listener,
        "ip_timeout_updater",
        lambda ip_addr, mac_addr, now: updates.append((ip_addr, mac_addr, now)),
    )

    listener.ip_neigh_poll_and_update(OneCycleStopEvent())

    assert updates == observations


def test_observed_client_refreshes_timestamp_and_clears_timeout(monkeypatch):
    ip_addr = "192.0.2.10"
    mac_addr = "00:00:00:00:00:10"
    updates = []

    monkeypatch.setattr(
        qm,
        "check_which_users_logged_in_for_ip_address",
        lambda requested_ip: (["alice"], 1),
    )
    monkeypatch.setattr(
        qm.sqlm,
        "select_ip_row",
        lambda requested_ip: (1, ip_addr, mac_addr, 1.0, 1),
    )
    monkeypatch.setattr(
        qm.sqlm,
        "update_ip_db",
        lambda requested_ip, now, timeout: updates.append(
            (requested_ip, now, timeout)
        ),
    )

    qm.ip_timeout_updater(ip_addr, mac_addr, now=1000.0)

    assert updates == [(ip_addr, 1000.0, 0)]


def test_enforcer_expires_only_client_older_than_timeout(monkeypatch):
    old_ip = "192.0.2.10"
    recent_ip = "192.0.2.11"
    old_mac = "00:00:00:00:00:10"
    recent_mac = "00:00:00:00:00:11"
    now = 1000.0
    enforced = []
    removed = []

    rows = {
        old_ip: (1, old_ip, old_mac, now - qm.sqlm.IP_TIMEOUT - 1, 0),
        recent_ip: (2, recent_ip, recent_mac, now - qm.sqlm.IP_TIMEOUT, 1),
    }

    monkeypatch.setattr(
        qm.sqlm,
        "fetch_all_ip_addr_ip_timeouts",
        lambda: [(old_ip, old_mac), (recent_ip, recent_mac)],
    )
    monkeypatch.setattr(qm.sqlm, "select_ip_row", rows.get)
    monkeypatch.setattr(qm.time, "monotonic", lambda: now)

    def enforce(ip_addr, mac_addr):
        enforced.append((ip_addr, mac_addr))
        return True

    monkeypatch.setattr(qm, "ip_enforce_timeout", enforce)
    monkeypatch.setattr(
        qm,
        "remove_user_from_ip_timeouts",
        lambda username, ip_addr: removed.append((username, ip_addr)),
    )

    qm.ip_timeout_enforcer()

    assert enforced == [(old_ip, old_mac)]
    assert removed == [(None, old_ip)]
