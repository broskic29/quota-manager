import numpy as np
import math
from tqdm import tqdm
import multiprocessing


def weighted_mse(r, desired_r, weights=None):
    if weights is None:
        weights = np.ones_like(r)
    return np.sum(weights * (r - desired_r) ** 2)


def quota_vector_generator(
    weights,
    total,
    v_min,
    v_max,
    step,
    desired_r,
    min_r,
    mse_weights=None,
    tol=1e-6,
):
    """
    Search for quota vectors v such that:
      - sum(v[i] * weights[i]) == total
      - r_i = v_i / sum(v) satisfies r_i >= min_r[i]
      - minimizes weighted MSE against desired_r
    """

    weights = np.asarray(weights, dtype=float)
    v_min = np.asarray(v_min, dtype=float)
    v_max = np.asarray(v_max, dtype=float)
    desired_r = np.asarray(desired_r, dtype=float)
    min_r = np.asarray(min_r, dtype=float)

    n = len(weights)

    best = {
        "mse": float("inf"),
        "v": None,
        "r": None,
    }

    grids = [np.arange(v_min[i], v_max[i] + step / 2, step) for i in range(n)]

    def recurse(i, current_v, remaining_budget, avg_bar, max_bar):
        avg_bar.update(1)
        max_bar.update(1)
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
                    "v": v.copy(),
                    "r": r.copy(),
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
        recurse(0, [], total, avg_bar, max_bar)
    return best


def main():
    weights = [80, 6, 7, 3]  # users per group
    total = 25600  # MB/day
    v_min = [150, 150, 150, 150]
    v_max = [3000, 3000, 3000, 3000]
    step = 10

    desired_r = [0.1, 0.2, 0.3, 0.4]
    min_r = [0.05, 0.1, 0.1, 0.1]

    result = quota_vector_generator(
        weights=weights,
        total=total,
        v_min=v_min,
        v_max=v_max,
        step=step,
        desired_r=desired_r,
        min_r=min_r,
    )

    print(result)

    # Soln!
    # {'mse': np.float64(9.789960840156634e-05), 'v': array([200., 440., 630., 850.]), 'r': array([0.09433962, 0.20754717, 0.29716981, 0.4009434 ])}


if __name__ == "__main__":
    main()
