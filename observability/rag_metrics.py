from __future__ import annotations

from typing import Any, Iterable

import numpy as np

from observability.anomaly import mad_detector, zscore_detector


def approximate_token_lengths(texts: Iterable[str]) -> list[int]:
    # Deliberately simple proxy; no tokenizer/model download needed.
    return [len(str(t).split()) for t in texts]


def detect_text_length_shift(
    current_texts: Iterable[str],
    baseline_batch_means: Iterable[float],
    *,
    threshold: float = 3.0,
) -> dict[str, Any]:
    lengths = approximate_token_lengths(current_texts)
    current_mean = float(np.mean(lengths)) if lengths else 0.0
    result = zscore_detector(current_mean, baseline_batch_means, threshold=threshold)
    result["metric"] = "mean_text_length"
    result["current_mean"] = current_mean
    return result


def detect_embedding_norm_shift(
    current_norms: Iterable[float], baseline_norms: Iterable[float], *, threshold: float = 3.5
) -> dict[str, Any]:
    """Embedding-space drift signal from precomputed vector norms.

    No embedding model is required: a change in embedding model/version, an
    encoding bug, or garbled/truncated input text typically shifts the norm
    distribution even without inspecting the actual vectors. Reuses the same
    robust median/MAD detector as the Phase 3 anomaly module instead of a
    third bespoke statistic -- embedding norms across many documents can be
    skewed by a handful of unusually long/short docs, which is exactly the
    scenario median/MAD is robust to and mean/std is not.
    """
    norms = list(current_norms)
    current_mean = float(np.mean(norms)) if norms else 0.0
    result = mad_detector(current_mean, baseline_norms, threshold=threshold)
    result["metric"] = "mean_embedding_norm"
    result["current_mean"] = current_mean
    return result
