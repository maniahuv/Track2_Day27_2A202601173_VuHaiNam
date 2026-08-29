"""Anomaly detection starter.

Z-score is deliberately the default baseline. Students should improve `auto`
mode for seasonality/outliers rather than deleting the simple implementation.
"""
from __future__ import annotations

from typing import Any, Iterable

import numpy as np


def zscore_detector(current: float, history: Iterable[float], threshold: float = 3.0) -> dict[str, Any]:
    values = np.asarray(list(history), dtype=float)
    if values.size < 3:
        return {"is_anomaly": False, "score": 0.0, "method": "zscore", "reason": "insufficient_history"}
    mean = float(np.mean(values))
    std = float(np.std(values))
    if std == 0:
        score = float("inf") if float(current) != mean else 0.0
    else:
        score = abs(float(current) - mean) / std
    return {
        "is_anomaly": bool(score > threshold),
        "score": float(score),
        "method": "zscore",
        "reason": f"mean={mean:.3f}, std={std:.3f}, threshold={threshold}",
    }


def mad_detector(current: float, history: Iterable[float], threshold: float = 3.5) -> dict[str, Any]:
    """Median/MAD detector: robust to the outliers and skew that break z-score."""
    values = np.asarray(list(history), dtype=float)
    if values.size < 5:
        return {"is_anomaly": False, "score": 0.0, "method": "mad", "reason": "insufficient_history"}
    median = float(np.median(values))
    mad = float(np.median(np.abs(values - median)))
    if mad == 0:
        # A perfectly flat history would otherwise make any nonzero deviation
        # score as "infinitely" anomalous. Fall back to a small scale-relative
        # epsilon so the detector stays usable instead of exploding to inf.
        mad = max(abs(median) * 0.01, 1e-9)
    modified_z = 0.6745 * abs(float(current) - median) / mad
    return {
        "is_anomaly": bool(modified_z > threshold),
        "score": float(modified_z),
        "method": "mad",
        "reason": f"median={median:.3f}, mad={mad:.3f}, threshold={threshold}",
    }


def context_aware_detector(
    current: float,
    history: Iterable[float],
    *,
    context: dict[str, Any] | None,
) -> dict[str, Any]:
    """Seasonality-aware scorer used by `detect_anomaly(method="auto")`.

    Prefers `context["same_segment_history"]` (e.g. same-weekday values) over
    the raw, possibly multi-segment `history`, then always scores with the
    robust median/MAD detector instead of a mean/std z-score. Pooling weekday
    and weekend history into one z-score baseline inflates std enough that
    even a large genuine drop can stay under the z>3 threshold (see
    reports/agent_log.md Decision 3 for the worked example).
    """
    context = context or {}
    same_segment = context.get("same_segment_history")
    segment_values = list(same_segment) if same_segment is not None else []
    use_segment = len(segment_values) >= 5
    baseline = segment_values if use_segment else list(history)
    baseline_source = "same_segment_history" if use_segment else "raw_history"

    result = mad_detector(current, baseline)
    result["method"] = f"auto:{baseline_source}+mad"
    result["reason"] += f"; baseline_source={baseline_source}"

    known_event = context.get("known_event")
    if known_event:
        # Annotate only -- whether an explained deviation should still page is
        # an SLO/burn-rate decision (Phase 5), not something this detector
        # should silently decide on its own.
        result["reason"] += f"; known_event={known_event!r}"

    return result


def detect_anomaly(
    current: float,
    history: Iterable[float],
    *,
    method: str = "auto",
    threshold: float = 3.0,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Stable lab API.

    - `zscore`: basic mean/std z-score.
    - `mad`: median/MAD, robust to outliers and a flat/zero-variance history.
    - `auto`: context-aware. Uses `context["same_segment_history"]` (e.g.
      same-weekday values) when available, and always scores with median/MAD
      so seasonality-inflated variance cannot mask a real drop.
    """
    if method == "mad":
        return mad_detector(current, history)
    if method == "zscore":
        return zscore_detector(current, history, threshold=threshold)
    if method == "auto":
        return context_aware_detector(current, history, context=context)
    raise ValueError(f"Unsupported method: {method}")
