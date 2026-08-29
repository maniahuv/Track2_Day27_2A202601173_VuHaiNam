from __future__ import annotations

from typing import Any, Iterable

import numpy as np


def _population_stability_index(current: np.ndarray, baseline: np.ndarray, *, bins: int) -> float:
    """PSI between two samples, binned on the baseline's own quantiles.

    Quantile bins (roughly equal-frequency on the baseline) make PSI sensitive
    to where the baseline actually has data, unlike fixed-width bins which
    waste resolution on empty ranges. Counts are clipped away from zero before
    the log so a bin with no observations doesn't blow up to +-inf noise.
    """
    edges = np.unique(np.quantile(baseline, np.linspace(0.0, 1.0, bins + 1)))
    if edges.size < 3:
        # Baseline is (near-)constant: any spread in current is a real shift.
        return 0.0 if np.allclose(current, baseline.mean()) else float("inf")
    edges = edges.copy()
    edges[0], edges[-1] = -np.inf, np.inf

    base_counts, _ = np.histogram(baseline, bins=edges)
    cur_counts, _ = np.histogram(current, bins=edges)
    base_frac = np.clip(base_counts / base_counts.sum(), 1e-6, None)
    cur_frac = np.clip(cur_counts / cur_counts.sum(), 1e-6, None)
    return float(np.sum((cur_frac - base_frac) * np.log(cur_frac / base_frac)))


def detect_distribution_shift(
    current_values: Iterable[float],
    baseline_values: Iterable[float],
    *,
    psi_threshold: float = 0.25,
) -> dict[str, Any]:
    """Population Stability Index (PSI) distribution drift detector.

    The previous mean-ratio approach only sees a shift if the AVERAGE moves --
    it is blind to shape changes, e.g. a distribution that keeps the same mean
    but splits into two clusters, or one whose spread doubles. PSI compares
    the full binned frequency profile against the baseline instead of a
    single summary statistic, so it catches shape drift a mean-ratio check
    would miss entirely. PSI >= 0.25 is the common industry threshold for a
    "significant" shift (0.1-0.25 is "moderate", below 0.1 is noise).
    """
    cur = np.asarray(list(current_values), dtype=float)
    base = np.asarray(list(baseline_values), dtype=float)
    if cur.size == 0 or base.size == 0:
        return {"is_anomaly": False, "score": 0.0, "method": "psi", "reason": "empty_input"}
    if base.size < 5:
        return {"is_anomaly": False, "score": 0.0, "method": "psi", "reason": "insufficient_baseline"}

    bins = min(10, max(2, base.size // 2))
    score = _population_stability_index(cur, base, bins=bins)
    return {
        "is_anomaly": bool(score >= psi_threshold),
        "score": score,
        "method": "psi",
        "reason": (
            f"baseline_mean={float(np.mean(base)):.3f}, current_mean={float(np.mean(cur)):.3f}, "
            f"bins={bins}, psi_threshold={psi_threshold}"
        ),
    }
