from student_api import rag_embedding_shift, rag_length_shift


def test_rag_length_collapse_is_detected():
    baseline_batch_means = [40, 42, 39, 41, 43, 40, 42]
    current_texts = ["x y", "a b c", "one two"]
    assert rag_length_shift(current_texts, baseline_batch_means)["is_anomaly"] is True


# Real embedding_norm_mean history from data/history/metrics_history.csv.
BASELINE_NORMS = [0.9794, 0.9742, 0.995, 1.0223, 0.9622, 1.02, 0.9923, 1.0691, 0.9778, 1.0307, 1.0088, 0.9909, 1.0295, 0.9944]


def test_collapsed_embedding_norms_are_detected():
    # e.g. a broken embedding call falling back to near-zero vectors.
    current_norms = [0.30, 0.28, 0.31, 0.29]
    assert rag_embedding_shift(current_norms, BASELINE_NORMS)["is_anomaly"] is True


def test_normal_embedding_norms_are_not_flagged():
    current_norms = [0.98, 1.00, 0.97, 1.01]
    assert rag_embedding_shift(current_norms, BASELINE_NORMS)["is_anomaly"] is False
