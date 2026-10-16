import logging
import re

import pytest

import quota_manager.quota_management as qm
import quota_manager.sql_management as sqlm
import quota_manager.flask_tools.admin_management_flask_server as admin_server


TOKEN_RE = re.compile(r'name="csrf_token" value="([^"]+)"')


@pytest.fixture()
def manual_reset_client(db_paths):
    admin_server.admin_management_app.config.update(TESTING=True)
    with admin_server.admin_management_app.test_client() as client:
        yield client


def _seed_user(usage_db):
    sqlm.create_group_usage("alpha", 1.0, db_path=usage_db)
    sqlm.create_user_usage("bob", "alpha", db_path=usage_db)


def _load_page_and_token(client, auth_header):
    response = client.get(
        "/admin/manual-usage-reset", headers=auth_header
    )
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    match = TOKEN_RE.search(body)
    assert match is not None
    return response, match.group(1)


def _selected_user_data(token, **overrides):
    data = {
        "csrf_token": token,
        "username": "bob",
        "scope": qm.MANUAL_RESET_DAILY,
        "confirmation": admin_server.MANUAL_RESET_SELECTED_CONFIRMATION,
    }
    data.update(overrides)
    return data


def _forbid_dangerous_operations(monkeypatch):
    calls = []

    def forbidden(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("dangerous operation must not be called")

    monkeypatch.setattr(qm, "system_hard_reset", forbidden)
    monkeypatch.setattr(qm, "reboot_system", forbidden, raising=False)
    return calls


def test_manual_reset_page_and_actions_require_authentication(manual_reset_client):
    assert manual_reset_client.get("/admin/manual-usage-reset").status_code == 401

    for endpoint in (
        "/admin/manual-usage-reset/user",
        "/admin/manual-usage-reset/all/daily",
        "/admin/manual-usage-reset/all/monthly",
    ):
        response = manual_reset_client.post(endpoint, data={})
        assert response.status_code == 401


def test_manual_reset_page_renders_users_actions_and_safety_text(
    manual_reset_client, admin_auth_header, db_paths
):
    usage_db, _ = db_paths
    _seed_user(usage_db)

    page, _ = _load_page_and_token(manual_reset_client, admin_auth_header)
    body = page.get_data(as_text=True)
    landing = manual_reset_client.get("/admin", headers=admin_auth_header)
    landing_body = landing.get_data(as_text=True)

    assert "Manual Usage Reset" in body
    assert "does not delete user accounts" in body
    assert "does not reboot the Pi" in body
    assert "bob" in body
    assert "Reset usage for one user" in body
    assert "Reset daily usage for all users" in body
    assert "Reset monthly usage for all users" in body
    assert admin_server.MANUAL_RESET_SELECTED_CONFIRMATION in body
    assert admin_server.MANUAL_RESET_ALL_DAILY_CONFIRMATION in body
    assert admin_server.MANUAL_RESET_ALL_MONTHLY_CONFIRMATION in body
    assert len(
        {
            admin_server.MANUAL_RESET_SELECTED_CONFIRMATION,
            admin_server.MANUAL_RESET_ALL_DAILY_CONFIRMATION,
            admin_server.MANUAL_RESET_ALL_MONTHLY_CONFIRMATION,
        }
    ) == 3
    assert 'href="/admin/manual-usage-reset"' in landing_body
    assert "Delete All Accounts and Usage" in landing_body


@pytest.mark.parametrize(
    "endpoint",
    [
        "/admin/manual-usage-reset/user",
        "/admin/manual-usage-reset/all/daily",
        "/admin/manual-usage-reset/all/monthly",
    ],
)
def test_action_endpoints_reject_get(
    manual_reset_client, admin_auth_header, endpoint
):
    response = manual_reset_client.get(endpoint, headers=admin_auth_header)
    assert response.status_code == 405


def test_invalid_username_and_scope_never_call_backend(
    manual_reset_client, admin_auth_header, db_paths, monkeypatch
):
    usage_db, _ = db_paths
    _seed_user(usage_db)
    backend_calls = []
    monkeypatch.setattr(
        qm,
        "manual_reset_user_usage",
        lambda *args, **kwargs: backend_calls.append((args, kwargs)),
    )

    _, token = _load_page_and_token(manual_reset_client, admin_auth_header)
    invalid_user = manual_reset_client.post(
        "/admin/manual-usage-reset/user",
        data=_selected_user_data(token, username="nobody"),
        headers=admin_auth_header,
        follow_redirects=True,
    )
    assert invalid_user.status_code == 200
    assert "selected user no longer exists" in invalid_user.get_data(as_text=True)

    _, token = _load_page_and_token(manual_reset_client, admin_auth_header)
    invalid_scope = manual_reset_client.post(
        "/admin/manual-usage-reset/user",
        data=_selected_user_data(token, scope="database_column"),
        headers=admin_auth_header,
        follow_redirects=True,
    )
    assert invalid_scope.status_code == 200
    assert "selected reset type is invalid" in invalid_scope.get_data(as_text=True)
    assert backend_calls == []


@pytest.mark.parametrize(
    ("endpoint", "data_factory"),
    [
        (
            "/admin/manual-usage-reset/user",
            lambda token: _selected_user_data(
                token,
                confirmation=admin_server.MANUAL_RESET_ALL_DAILY_CONFIRMATION,
            ),
        ),
        (
            "/admin/manual-usage-reset/all/daily",
            lambda token: {
                "csrf_token": token,
                "confirmation": admin_server.MANUAL_RESET_ALL_MONTHLY_CONFIRMATION,
            },
        ),
        (
            "/admin/manual-usage-reset/all/monthly",
            lambda token: {
                "csrf_token": token,
                "confirmation": admin_server.MANUAL_RESET_SELECTED_CONFIRMATION,
            },
        ),
    ],
)
def test_each_action_rejects_the_wrong_confirmation_phrase(
    manual_reset_client,
    admin_auth_header,
    db_paths,
    monkeypatch,
    endpoint,
    data_factory,
):
    usage_db, _ = db_paths
    _seed_user(usage_db)
    calls = []
    monkeypatch.setattr(
        qm,
        "manual_reset_user_usage",
        lambda *args, **kwargs: calls.append("user"),
    )
    monkeypatch.setattr(
        qm,
        "manual_reset_all_daily_usage",
        lambda *args, **kwargs: calls.append("daily"),
    )
    monkeypatch.setattr(
        qm,
        "manual_reset_all_monthly_usage",
        lambda *args, **kwargs: calls.append("monthly"),
    )

    _, token = _load_page_and_token(manual_reset_client, admin_auth_header)
    response = manual_reset_client.post(
        endpoint,
        data=data_factory(token),
        headers=admin_auth_header,
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "confirmation phrase did not match" in response.get_data(as_text=True)
    assert calls == []


def test_missing_or_replayed_csrf_token_never_calls_backend(
    manual_reset_client, admin_auth_header, db_paths, monkeypatch
):
    usage_db, _ = db_paths
    _seed_user(usage_db)
    calls = []

    def backend(username, scope, *, audit_identity):
        calls.append((username, scope, audit_identity))
        return qm.MANUAL_RESET_COMPLETED

    monkeypatch.setattr(qm, "manual_reset_user_usage", backend)

    missing = manual_reset_client.post(
        "/admin/manual-usage-reset/user",
        data=_selected_user_data(""),
        headers=admin_auth_header,
        follow_redirects=True,
    )
    assert "security check failed" in missing.get_data(as_text=True)
    assert calls == []

    _, token = _load_page_and_token(manual_reset_client, admin_auth_header)
    data = _selected_user_data(token)
    first = manual_reset_client.post(
        "/admin/manual-usage-reset/user",
        data=data,
        headers=admin_auth_header,
        follow_redirects=False,
    )
    replay = manual_reset_client.post(
        "/admin/manual-usage-reset/user",
        data=data,
        headers=admin_auth_header,
        follow_redirects=False,
    )

    assert first.status_code == 303
    assert replay.status_code == 303
    assert calls == [("bob", qm.MANUAL_RESET_DAILY, "admin")]


@pytest.mark.parametrize(
    "scope",
    [
        qm.MANUAL_RESET_DAILY,
        qm.MANUAL_RESET_MONTHLY,
        qm.MANUAL_RESET_DAILY_AND_MONTHLY,
    ],
)
def test_selected_user_valid_scopes_call_backend_once_and_use_prg(
    manual_reset_client,
    admin_auth_header,
    db_paths,
    monkeypatch,
    caplog,
    scope,
):
    usage_db, _ = db_paths
    _seed_user(usage_db)
    calls = []
    dangerous_calls = _forbid_dangerous_operations(monkeypatch)

    def backend(username, selected_scope, *, audit_identity):
        calls.append((username, selected_scope, audit_identity))
        return qm.MANUAL_RESET_COMPLETED

    monkeypatch.setattr(qm, "manual_reset_user_usage", backend)
    caplog.set_level(logging.INFO, logger=admin_server.__name__)
    _, token = _load_page_and_token(manual_reset_client, admin_auth_header)

    response = manual_reset_client.post(
        "/admin/manual-usage-reset/user",
        data=_selected_user_data(token, scope=scope),
        headers=admin_auth_header,
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["Location"].endswith("/admin/manual-usage-reset")
    assert calls == [("bob", scope, "admin")]
    assert dangerous_calls == []
    assert "administrator='admin'" in caplog.text
    assert "operation='selected_user'" in caplog.text
    assert "outcome='completed'" in caplog.text

    result_page = manual_reset_client.get(
        response.headers["Location"], headers=admin_auth_header
    )
    assert "was reset for bob" in result_page.get_data(as_text=True)

    manual_reset_client.get(
        response.headers["Location"], headers=admin_auth_header
    )
    assert calls == [("bob", scope, "admin")]


@pytest.mark.parametrize(
    ("endpoint", "confirmation", "backend_name", "success_text"),
    [
        (
            "/admin/manual-usage-reset/all/daily",
            admin_server.MANUAL_RESET_ALL_DAILY_CONFIRMATION,
            "manual_reset_all_daily_usage",
            "Daily usage was reset for all users.",
        ),
        (
            "/admin/manual-usage-reset/all/monthly",
            admin_server.MANUAL_RESET_ALL_MONTHLY_CONFIRMATION,
            "manual_reset_all_monthly_usage",
            "Monthly usage was reset for all users.",
        ),
    ],
)
def test_valid_global_actions_call_only_the_matching_backend(
    manual_reset_client,
    admin_auth_header,
    monkeypatch,
    endpoint,
    confirmation,
    backend_name,
    success_text,
):
    calls = []
    dangerous_calls = _forbid_dangerous_operations(monkeypatch)

    def backend(*, audit_identity):
        calls.append(audit_identity)
        return qm.MANUAL_RESET_COMPLETED

    monkeypatch.setattr(qm, backend_name, backend)
    _, token = _load_page_and_token(manual_reset_client, admin_auth_header)
    response = manual_reset_client.post(
        endpoint,
        data={"csrf_token": token, "confirmation": confirmation},
        headers=admin_auth_header,
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert calls == ["admin"]
    assert dangerous_calls == []
    result_page = manual_reset_client.get(
        response.headers["Location"], headers=admin_auth_header
    )
    assert success_text in result_page.get_data(as_text=True)


@pytest.mark.parametrize(
    ("outcome", "expected_text"),
    [
        (qm.MANUAL_RESET_BUSY, "operation is busy"),
        (qm.MANUAL_RESET_DEFERRED_CLOCK, "system clock is not yet trusted"),
        (qm.MANUAL_RESET_INVALID_USER, "selected user no longer exists"),
        (qm.MANUAL_RESET_FAILED, "usage reset failed"),
    ],
)
def test_backend_outcomes_display_precise_non_success_messages(
    manual_reset_client,
    admin_auth_header,
    db_paths,
    monkeypatch,
    outcome,
    expected_text,
):
    usage_db, _ = db_paths
    _seed_user(usage_db)
    monkeypatch.setattr(
        qm, "manual_reset_user_usage", lambda *args, **kwargs: outcome
    )
    _, token = _load_page_and_token(manual_reset_client, admin_auth_header)

    response = manual_reset_client.post(
        "/admin/manual-usage-reset/user",
        data=_selected_user_data(token),
        headers=admin_auth_header,
        follow_redirects=True,
    )
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert expected_text in body
    assert "was reset for bob" not in body


def test_unexpected_backend_exception_displays_failure_not_success(
    manual_reset_client, admin_auth_header, db_paths, monkeypatch
):
    usage_db, _ = db_paths
    _seed_user(usage_db)

    def backend_failure(*args, **kwargs):
        raise RuntimeError("simulated backend failure")

    monkeypatch.setattr(qm, "manual_reset_user_usage", backend_failure)
    _, token = _load_page_and_token(manual_reset_client, admin_auth_header)

    response = manual_reset_client.post(
        "/admin/manual-usage-reset/user",
        data=_selected_user_data(token),
        headers=admin_auth_header,
        follow_redirects=True,
    )
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "usage reset failed" in body
    assert "was reset for bob" not in body


def test_manual_routes_never_call_factory_reset_or_reboot(
    manual_reset_client, admin_auth_header, db_paths, monkeypatch
):
    usage_db, _ = db_paths
    _seed_user(usage_db)
    dangerous_calls = _forbid_dangerous_operations(monkeypatch)
    monkeypatch.setattr(
        qm,
        "manual_reset_user_usage",
        lambda *args, **kwargs: qm.MANUAL_RESET_COMPLETED,
    )
    monkeypatch.setattr(
        qm,
        "manual_reset_all_daily_usage",
        lambda *args, **kwargs: qm.MANUAL_RESET_COMPLETED,
    )
    monkeypatch.setattr(
        qm,
        "manual_reset_all_monthly_usage",
        lambda *args, **kwargs: qm.MANUAL_RESET_COMPLETED,
    )

    actions = (
        (
            "/admin/manual-usage-reset/user",
            lambda token: _selected_user_data(token),
        ),
        (
            "/admin/manual-usage-reset/all/daily",
            lambda token: {
                "csrf_token": token,
                "confirmation": admin_server.MANUAL_RESET_ALL_DAILY_CONFIRMATION,
            },
        ),
        (
            "/admin/manual-usage-reset/all/monthly",
            lambda token: {
                "csrf_token": token,
                "confirmation": admin_server.MANUAL_RESET_ALL_MONTHLY_CONFIRMATION,
            },
        ),
    )

    for endpoint, data_factory in actions:
        _, token = _load_page_and_token(manual_reset_client, admin_auth_header)
        response = manual_reset_client.post(
            endpoint,
            data=data_factory(token),
            headers=admin_auth_header,
            follow_redirects=False,
        )
        assert response.status_code == 303

    assert dangerous_calls == []
