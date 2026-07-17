from __future__ import annotations

import hashlib
import math
from collections.abc import Mapping, Sequence
from typing import Any, Literal

import numpy as np


BootstrapStatistic = Literal["mean", "median"]
BootstrapMetricInput = tuple[Sequence[float], BootstrapStatistic]


def _metric_seed(random_seed: int, metric_name: str) -> int:
    digest = hashlib.sha256(f"{random_seed}:{metric_name}".encode("utf-8")).digest()
    return int.from_bytes(digest[:8], byteorder="big", signed=False)


def _statistic(values: np.ndarray, statistic: BootstrapStatistic, *, axis: int | None = None) -> Any:
    if statistic == "mean":
        return np.mean(values, axis=axis)
    return np.median(values, axis=axis)


def bootstrap_confidence_intervals(
    metrics: Mapping[str, BootstrapMetricInput],
    *,
    confidence_level: float = 0.95,
    bootstrap_samples: int = 2000,
    random_seed: int = 42,
) -> dict[str, Any]:
    if not 0.0 < confidence_level < 1.0:
        raise ValueError("confidence_level must be between 0 and 1")
    if bootstrap_samples < 1:
        raise ValueError("bootstrap_samples must be at least 1")

    alpha = (1.0 - confidence_level) / 2.0
    metric_results: dict[str, dict[str, float | int] | None] = {}
    for metric_name, (raw_values, statistic) in metrics.items():
        if statistic not in ("mean", "median"):
            raise ValueError(f"Unsupported bootstrap statistic: {statistic}")
        finite_values: list[float] = []
        for value in raw_values:
            numeric_value = float(value)
            if math.isfinite(numeric_value):
                finite_values.append(numeric_value)
        values = np.asarray(finite_values, dtype=float)
        if values.size == 0:
            metric_results[metric_name] = None
            continue

        rng = np.random.default_rng(_metric_seed(random_seed, metric_name))
        estimates = np.empty(bootstrap_samples, dtype=float)
        batch_size = max(1, min(bootstrap_samples, 1_000_000 // values.size))
        for start in range(0, bootstrap_samples, batch_size):
            stop = min(start + batch_size, bootstrap_samples)
            indices = rng.integers(
                low=0,
                high=values.size,
                size=(stop - start, values.size),
            )
            estimates[start:stop] = _statistic(values[indices], statistic, axis=1)

        lower, upper = np.quantile(estimates, [alpha, 1.0 - alpha])
        standard_error = float(np.std(estimates, ddof=1 if bootstrap_samples > 1 else 0))
        metric_results[metric_name] = {
            "estimate": round(float(_statistic(values, statistic)), 6),
            "lower": round(float(lower), 6),
            "upper": round(float(upper), 6),
            "standard_error": round(standard_error, 6),
            "sample_size": int(values.size),
        }

    return {
        "method": "nonparametric_percentile_bootstrap",
        "confidence_level": confidence_level,
        "bootstrap_samples": bootstrap_samples,
        "random_seed": random_seed,
        "metrics": metric_results,
    }
