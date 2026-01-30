import sys
import numpy as np
import math
from tqdm import tqdm
import multiprocessing  # Add in future to speed up calculation.


import math
from math import fsum


DEFAULT_STEP_SIZE_10_MB = 10 * 1024**2


class QuotaConfigError(ValueError):
    pass


def validate_quota_config(cfg: dict) -> None:
    tol = float(cfg["error_tol"])
    step = float(cfg["step_size_in_bytes"])
    daily = float(cfg["daily_bytes"])
    groups = cfg.get("groups", {})

    if not groups:
        raise QuotaConfigError("No groups configured.")

    if step <= 0:
        raise QuotaConfigError("step_size_in_bytes must be > 0.")
    if tol <= 0:
        raise QuotaConfigError("error_tol must be > 0.")
    if daily < 0:
        raise QuotaConfigError("daily_bytes must be >= 0.")

    # tol too much smaller than step
    if step / tol > 10:
        raise QuotaConfigError(
            f"error_tol ({tol}) is >10 times smaller than step ({step})."
        )

    active = [(name, g) for name, g in groups.items() if g.get("n", 0) > 0]
    if not active:
        raise QuotaConfigError("All groups have n=0; nothing to allocate.")

    # bounds + feasibility
    min_cost = 0.0
    max_cost = 0.0
    min_r_sum = 0.0
    desired_sum = 0.0

    for name, g in active:
        n = float(g["n"])
        vmin = float(g["min_num_bytes"])
        vmax = float(g["max_num_bytes"]) if g["max_num_bytes"] else None
        if n < 0:
            raise QuotaConfigError(f"{name}: n must be >= 0")
        if vmin < 0 or (vmax and vmax < 0):
            raise QuotaConfigError(f"{name}: min/max bytes must be >= 0")
        if vmax and (vmin > vmax):
            raise QuotaConfigError(f"{name}: min_num_bytes > max_num_bytes")

        mr = float(g["min_quota_ratio"])
        dr = float(g["desired_quota_ratio"])
        if not math.isfinite(mr) or not (0.0 <= mr <= 1.0):
            raise QuotaConfigError(f"{name}: min_quota_ratio must be in [0,1]")
        if not math.isfinite(dr) or dr < 0.0:
            raise QuotaConfigError(
                f"{name}: desired_quota_ratio must be >= 0 and finite"
            )

        min_cost += vmin * n
        max_cost += vmax * n if vmax else 0
        min_r_sum += mr
        desired_sum += dr

    if min_r_sum > 1.0 + tol:
        raise QuotaConfigError(
            f"Sum(min_quota_ratio)={min_r_sum} exceeds 1; impossible."
        )

    if daily < min_cost - tol:
        raise QuotaConfigError(
            f"daily_bytes ({daily}) below min feasible total ({min_cost})."
        )

    # grid representability (practical check, not perfect for multi-group)
    snapped = round(daily / step) * step
    if abs(daily - snapped) > max(tol, step * 1e-6):
        raise QuotaConfigError(
            f"daily_bytes ({daily}) not close to a step-multiple ({snapped}); "
            f"no exact grid solution likely unless tol is large."
        )


def weighted_mse(r, desired_r, weights=None):
    if weights is None:
        w = np.ones_like(r, dtype=float)
    else:
        w = np.asarray([1.0 if x is None else float(x) for x in weights], dtype=float)
        if w.shape != r.shape:
            raise ValueError(f"weights shape {w.shape} must match r shape {r.shape}")
    diff = r - desired_r
    return np.sum(w * diff * diff)


def quota_vector_generator(
    quota_config_dict, leftover_penalty=1e-3, quantize=True, show_progress=None
):
    """
    Search for quota vectors v such that:
      - sum(v[i] * weights[i]) == total
      - r_i = v_i / sum(v) satisfies r_i >= min_r[i]
      - minimizes weighted MSE against desired_r
    """

    # Validate config first.
    validate_quota_config(quota_config_dict)

    groups = [group for group in quota_config_dict["groups"]]
    weights = [group["n"] for group in quota_config_dict["groups"].values()]
    v_min = [group["min_num_bytes"] for group in quota_config_dict["groups"].values()]
    v_max = [group["max_num_bytes"] for group in quota_config_dict["groups"].values()]
    desired_r = [
        group["desired_quota_ratio"] for group in quota_config_dict["groups"].values()
    ]
    min_r = [group["min_quota_ratio"] for group in quota_config_dict["groups"].values()]
    mse_weights = [
        group["mse_weights"] for group in quota_config_dict["groups"].values()
    ]

    step = int(quota_config_dict["step_size_in_bytes"])
    tol = quota_config_dict["error_tol"]

    if quantize:
        total_daily_bytes = float(quota_config_dict["daily_bytes"])

        total_daily_bytes = round(total_daily_bytes / step) * step
        total_daily_bytes = float(total_daily_bytes)
    else:
        total_daily_bytes = int(
            round(quota_config_dict["daily_bytes"])
        )  # or already int

    # Generate arrays of integers
    weights = np.asarray(weights, dtype=int)
    v_min = np.asarray([int(round(x)) for x in v_min], dtype=int)
    v_max = np.asarray([int(round(x)) for x in v_max], dtype=int)

    desired_r = np.asarray([round(r, 2) for r in desired_r], dtype=float)
    min_r = np.asarray(min_r, dtype=float)

    # Filter for active groups only
    active_idx = [k for k, w in enumerate(weights) if w > 0]

    groups = [groups[k] for k in active_idx]
    weights = weights[active_idx]
    v_min = v_min[active_idx]
    v_max = v_max[active_idx]
    desired_r = desired_r[active_idx]
    min_r = min_r[active_idx]
    mse_weights = [mse_weights[k] for k in active_idx]  # keep as list if it has None
    n = len(weights)

    n = len(weights)

    best = {
        "mse": float("inf"),
        "v_dict": None,
        "r_dict": None,
    }

    # build integer grids
    grids = [range(int(v_min[i]), int(v_max[i]) + step, step) for i in range(n)]

    nodes_visited = 0
    UPDATE_EVERY = 10_000

    def recurse(i, current_v, remaining_budget, avg_bar, max_bar):
        nonlocal nodes_visited
        nodes_visited += 1

        if show_progress and nodes_visited % UPDATE_EVERY == 0:
            avg_bar.update(UPDATE_EVERY)
            max_bar.update(UPDATE_EVERY)

        nonlocal best

        if i == n:
            if abs(remaining_budget) > tol:
                return

            v = np.array(current_v)
            v_sum = np.sum(v)

            if v_sum <= 0:
                return

            r = v / v_sum

            if np.any(r < min_r - tol):
                return

            mse = weighted_mse(r, desired_r, mse_weights)
            mse += (abs(remaining_budget) / total_daily_bytes) * leftover_penalty

            leftover_mb = (abs(remaining_budget) / total_daily_bytes) * 1024**2

            if mse < best["mse"]:
                best = {
                    "mse": mse,
                    "leftover_mb": leftover_mb,
                    "v_dict": {name: v for name, v in zip(groups, v.copy())},
                    "r_dict": {name: r for name, r in zip(groups, r.copy())},
                }
            return

        # Prune impossible branches
        min_possible = np.sum(v_min[i:] * weights[i:])
        max_possible = np.sum(v_max[i:] * weights[i:])

        if not (min_possible - tol <= remaining_budget <= max_possible + tol):
            return

        # If we're at the last dimension, solve it directly
        if i == n - 1:
            v_last = remaining_budget / weights[i]

            # snap to grid
            v_last = round(v_last / step) * step

            # (optional) snap might introduce tiny float noise
            cost = v_last * weights[i]
            new_remaining = remaining_budget - cost

            if v_min[i] - tol <= v_last <= v_max[i] + tol and abs(new_remaining) <= tol:
                recurse(
                    i + 1,  # or n; both work given your base case is i==n
                    current_v + [v_last],
                    new_remaining,
                    avg_bar,
                    max_bar,
                )
            return

        for v_i in grids[i]:
            cost = v_i * weights[i]
            if cost > remaining_budget + tol:
                continue

            recurse(
                i + 1,
                current_v + [v_i],
                remaining_budget - cost,
                avg_bar,
                max_bar,
            )

    k_avg = ((np.average(v_max) - np.average(v_min)) / step) + 1
    n_recursions_avg = k_avg ** (n - 1) / (math.factorial(n - 1))

    k_max = ((np.max(v_max) - np.max(v_min)) / step) + 1
    n_recursions_max = k_max**n

    if show_progress is None:
        show_progress = sys.stderr.isatty()

    with tqdm(
        total=n_recursions_avg,
        desc="Finding best solution, average time bound...",
        disable=not show_progress,
    ) as avg_bar, tqdm(
        total=n_recursions_max,
        desc="Finding best solution, max time bound...",
        disable=not show_progress,
    ) as max_bar:
        recurse(0, [], total_daily_bytes, avg_bar, max_bar)
    return best


def gen_quota_config_dict(
    total_daily_bytes,
    groups_config_dict,
    step_size_in_bytes=DEFAULT_STEP_SIZE_10_MB,
    error_tol=None,
):
    if error_tol is None:
        error_tol = int(step_size_in_bytes / 2)

    quota_config_dict = {
        "daily_bytes": total_daily_bytes,
        "step_size_in_bytes": step_size_in_bytes,
        "error_tol": error_tol,
    }

    quota_config_dict["groups"] = groups_config_dict

    return quota_config_dict


def main():

    quota_config_dict = {
        "daily_bytes": (500 / 20) * 1024**3,
        "step_size_in_bytes": 10 * 1024**2,
        "error_tol": 5 * 1024**2,
        "groups": {
            "regular_students": {
                "n": 100,
                "desired_quota_ratio": 0.1,
                "min_quota_ratio": 0.05,
                "max_num_bytes": 1000 * 1024**2,
                "min_num_bytes": 150 * 1024**2,
                "mse_weights": None,
            },
            "computer_students": {
                "n": 10,
                "desired_quota_ratio": 0.2,
                "min_quota_ratio": 0.1,
                "max_num_bytes": 1500 * 1024**2,
                "min_num_bytes": 300 * 1024**2,
                "mse_weights": None,
            },
            "staff": {
                "n": 8,
                "desired_quota_ratio": 0.3,
                "min_quota_ratio": 0.1,
                "max_num_bytes": 1750 * 1024**2,
                "min_num_bytes": 500 * 1024**2,
                "mse_weights": None,
            },
            "admin": {
                "n": 3,
                "desired_quota_ratio": 0.4,
                "min_quota_ratio": 0.1,
                "max_num_bytes": 2000 * 1024**2,
                "min_num_bytes": 750 * 1024**2,
                "mse_weights": None,
            },
        },
    }

    # quota_config_dict = {
    #     "daily_bytes": 89478485333,
    #     "step_size_in_bytes": 0.1 * 1024**2,
    #     "error_tol": 0.05 * 1024**2,
    #     "groups": {
    #         "admin": {
    #             "n": 1,
    #             "desired_quota_ratio": 1.0,
    #             "min_quota_ratio": 0.0,
    #             "max_num_bytes": 89478485333,
    #             "min_num_bytes": 0.0,
    #             "mse_weights": None,
    #         }
    #     },
    # }

    quota_config_dict = {
        "daily_bytes": 84508934144.0,
        "step_size_in_bytes": 10485760,
        "error_tol": 5242880,
        "groups": {
            "admin": {
                "n": 1,
                "desired_quota_ratio": 0.4444444444444445,
                "min_quota_ratio": 0.1,
                "max_num_bytes": 56339289429.33333,
                "min_num_bytes": 153600,
                "mse_weights": None,
            },
            "computer_students": {
                "n": 1,
                "desired_quota_ratio": 0.22222222222222224,
                "min_quota_ratio": 0.1,
                "max_num_bytes": 28169644714.666664,
                "min_num_bytes": 153600,
                "mse_weights": None,
            },
            "default": {
                "n": 0,
                "desired_quota_ratio": 0,
                "min_quota_ratio": 0,
                "max_num_bytes": 0,
                "min_num_bytes": 0,
                "mse_weights": None,
            },
            "staff": {
                "n": 1,
                "desired_quota_ratio": 0.33333333333333326,
                "min_quota_ratio": 0.1,
                "max_num_bytes": None,
                "min_num_bytes": 153600,
                "mse_weights": None,
            },
        },
    }

    result = quota_vector_generator(quota_config_dict=quota_config_dict)

    print(result)

    # Soln!
    # {'mse': np.float64(9.789960840156634e-05), 'v': array([200., 440., 630., 850.]), 'r': array([0.09433962, 0.20754717, 0.29716981, 0.4009434 ])}


if __name__ == "__main__":
    main()

# reduce total num bytes by whatever the max error caused by tolerance would be.
