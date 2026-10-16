import math

import pytest

from quota_manager import quota_management as qm
from quota_manager.quota_tools import smart_quota_tool as sqt


def _group(
    *,
    members,
    desired_ratio,
    min_ratio=0.0,
    min_bytes=0,
    max_bytes=100,
):
    return {
        "n": members,
        "desired_quota_ratio": desired_ratio,
        "min_quota_ratio": min_ratio,
        "min_num_bytes": min_bytes,
        "max_num_bytes": max_bytes,
        "mse_weights": None,
    }


def _config(groups, daily_bytes=100):
    return {
        "daily_bytes": daily_bytes,
        "step_size_in_bytes": 10,
        "error_tol": 5,
        "groups": groups,
    }


def _allocate(groups, daily_bytes=100):
    return sqt.quota_vector_generator(
        _config(groups, daily_bytes=daily_bytes), show_progress=False
    )


def test_populated_zero_ratio_group_is_returned_but_does_not_consume_budget():
    result = _allocate(
        {
            "enabled": _group(members=1, desired_ratio=1.0),
            "disabled": _group(members=8, desired_ratio=0.0),
        }
    )

    assert result.get("failure") is None
    assert result["v_dict"] == {"enabled": 100.0, "disabled": 0}
    assert result["r_dict"] == {"enabled": 1.0, "disabled": 0}


def test_stale_disabled_group_constraints_do_not_affect_feasibility():
    result = _allocate(
        {
            "enabled": _group(
                members=1,
                desired_ratio=1.0,
                min_ratio=0.25,
            ),
            "disabled": _group(
                members=50,
                desired_ratio=0.0,
                min_ratio=1.0,
                min_bytes=1_000,
                max_bytes=10,
            ),
        }
    )

    assert result.get("failure") is None
    assert result["v_dict"] == {"enabled": 100.0, "disabled": 0}
    assert result["r_dict"]["disabled"] == 0


def test_all_populated_groups_at_zero_return_explicit_all_zero_allocation():
    result = _allocate(
        {
            "disabled_a": _group(members=3, desired_ratio=0.0),
            "disabled_b": _group(members=7, desired_ratio=0.0),
        }
    )

    assert result.get("failure") is None
    assert result["v_dict"] == {"disabled_a": 0, "disabled_b": 0}
    assert result["r_dict"] == {"disabled_a": 0, "disabled_b": 0}


def test_all_zero_normal_plumbing_can_clear_saved_quotas(monkeypatch):
    monkeypatch.setattr(
        qm.sqlm,
        "fetch_group_quota_info_usage",
        lambda: [
            ("disabled_a", 3, 0.0, 0.0, 900, 100, None),
            ("disabled_b", 7, 0.0, 0.0, 800, 200, None),
        ],
    )
    updates = []
    monkeypatch.setattr(
        qm.sqlm,
        "update_group_quota",
        lambda group_name, quota: updates.append((group_name, quota)),
    )
    monkeypatch.setattr(qm.sqlh, "log_all_table_information", lambda *_args: None)

    group_config = qm.gen_group_config_dict_for_sqt(100)
    result = sqt.quota_vector_generator(
        sqt.gen_quota_config_dict(
            100,
            group_config,
            step_size_in_bytes=10,
            error_tol=5,
        ),
        show_progress=False,
    )
    qm.apply_new_quotas(result["v_dict"])

    assert result["v_dict"] == {"disabled_a": 0, "disabled_b": 0}
    assert updates == [("disabled_a", 0), ("disabled_b", 0)]


def test_positive_ratio_allocation_is_unchanged():
    result = _allocate(
        {
            "alpha": _group(members=1, desired_ratio=0.5),
            "beta": _group(members=1, desired_ratio=0.5),
        }
    )

    assert result.get("failure") is None
    assert result["v_dict"] == {"alpha": 50, "beta": 50}
    assert result["r_dict"] == {"alpha": 0.5, "beta": 0.5}


def test_small_positive_ratio_is_not_treated_as_disabled():
    result = _allocate(
        {
            "large": _group(members=1, desired_ratio=0.999),
            "small": _group(
                members=1,
                desired_ratio=0.001,
                min_bytes=10,
            ),
        }
    )

    assert result.get("failure") is None
    assert result["v_dict"]["small"] == 10
    assert sum(result["v_dict"].values()) == 100


@pytest.mark.parametrize("desired_ratio", [-0.1, math.inf, math.nan])
def test_invalid_desired_ratios_are_rejected(desired_ratio):
    with pytest.raises(sqt.QuotaConfigError):
        _allocate(
            {
                "invalid": _group(
                    members=1,
                    desired_ratio=desired_ratio,
                )
            }
        )
