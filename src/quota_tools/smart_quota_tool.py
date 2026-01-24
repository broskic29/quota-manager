import numpy as np
import math
from tqdm import tqdm
import multiprocessing  # Add in future to speed up calculation.


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
    quota_config_dict,
):
    """
    Search for quota vectors v such that:
      - sum(v[i] * weights[i]) == total
      - r_i = v_i / sum(v) satisfies r_i >= min_r[i]
      - minimizes weighted MSE against desired_r
    """

    groups = [group for group in quota_config_dict["groups"]]
    weights = [group["n"] for group in quota_config_dict["groups"].values()]
    v_min = [group["min_num_mbytes"] for group in quota_config_dict["groups"].values()]
    v_max = [group["max_num_mbytes"] for group in quota_config_dict["groups"].values()]
    desired_r = [
        group["desired_quota_ratio"] for group in quota_config_dict["groups"].values()
    ]
    min_r = [group["min_quota_ratio"] for group in quota_config_dict["groups"].values()]
    mse_weights = [
        group["mse_weights"] for group in quota_config_dict["groups"].values()
    ]

    total_daily_mbytes = quota_config_dict["daily_mbytes"]
    step = quota_config_dict["step_size_in_mbytes"]
    tol = quota_config_dict["error_tol"]

    weights = np.asarray(weights, dtype=float)
    v_min = np.asarray(v_min, dtype=float)
    v_max = np.asarray(v_max, dtype=float)
    desired_r = np.asarray(desired_r, dtype=float)
    min_r = np.asarray(min_r, dtype=float)

    n = len(weights)

    best = {
        "mse": float("inf"),
        "v_dict": None,
        "r_dict": None,
    }

    grids = [np.arange(v_min[i], v_max[i] + step / 2, step) for i in range(n)]

    nodes_visited = 0
    UPDATE_EVERY = 10_000

    def recurse(i, current_v, remaining_budget, avg_bar, max_bar):
        nonlocal nodes_visited
        nodes_visited += 1

        if nodes_visited % UPDATE_EVERY == 0:
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

            if mse < best["mse"]:
                best = {
                    "mse": mse,
                    "v_dict": {name: v for name, v in zip(groups, v.copy())},
                    "r_dict": {name: r for name, r in zip(groups, r.copy())},
                }
            return

        # Prune impossible branches
        min_possible = np.sum(v_min[i:] * weights[i:])
        max_possible = np.sum(v_max[i:] * weights[i:])

        if not (min_possible - tol <= remaining_budget <= max_possible + tol):
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

    with tqdm(
        total=n_recursions_avg, desc="Finding best solution, average time bound..."
    ) as avg_bar, tqdm(
        total=n_recursions_max, desc="Finding best solution, max time bound..."
    ) as max_bar:
        recurse(0, [], total_daily_mbytes, avg_bar, max_bar)
    return best


def gen_quota_config_dict(
    total_daily_mbytes,
    groups_config_dict,
    step_size_in_mbytes=10,
    error_tol=1e-6,
):
    quota_config_dict = {
        "daily_mbytes": total_daily_mbytes,
        "step_size_in_mbytes": step_size_in_mbytes,
        "error_tol": error_tol,
    }

    quota_config_dict["groups"] = groups_config_dict

    return quota_config_dict


def main():

    quota_config_dict = {
        "daily_mbytes": 25600,
        "step_size_in_mbytes": 10,
        "error_tol": 1e-6,
        "groups": {
            "regular_students": {
                "n": 100,
                "desired_quota_ratio": 0.1,
                "min_quota_ratio": 0.05,
                "max_num_mbytes": 3000,
                "min_num_mbytes": 150,
                "mse_weights": None,
            },
            "computer_students": {
                "n": 10,
                "desired_quota_ratio": 0.2,
                "min_quota_ratio": 0.1,
                "max_num_mbytes": 3000,
                "min_num_mbytes": 150,
                "mse_weights": None,
            },
            "staff": {
                "n": 8,
                "desired_quota_ratio": 0.3,
                "min_quota_ratio": 0.1,
                "max_num_mbytes": 3000,
                "min_num_mbytes": 150,
                "mse_weights": None,
            },
            "admin": {
                "n": 3,
                "desired_quota_ratio": 0.4,
                "min_quota_ratio": 0.1,
                "max_num_mbytes": 3000,
                "min_num_mbytes": 150,
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
