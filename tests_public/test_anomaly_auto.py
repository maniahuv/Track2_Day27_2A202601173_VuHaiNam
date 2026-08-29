"""Tests for the seasonality-aware `auto` method (Phase 3 upgrade).

Weekdays run ~600 rows/day and Saturdays run ~250 rows/day in
data/history/metrics_history.csv. Pooling both into one z-score baseline
inflates std enough that a naive z-score can miss a real drop -- these tests
pin down that failure mode and show that `method="auto"` with a
same-weekday `context` catches it instead.
"""
from student_api import detect_metric

MIXED_HISTORY = [600, 610, 595, 608, 604, 250, 246, 612, 598, 255]
SATURDAY_HISTORY = [250, 246, 255, 258, 262, 235, 259]


def test_naive_zscore_masks_a_real_70_percent_drop_on_seasonal_data():
    dropped_value = 75  # ~70% below a normal ~255 Saturday
    naive = detect_metric(dropped_value, MIXED_HISTORY, method="zscore")
    assert naive["is_anomaly"] is False  # masked: pooled std hides the drop


def test_auto_same_weekday_context_catches_the_same_drop():
    dropped_value = 75
    result = detect_metric(
        dropped_value,
        MIXED_HISTORY,
        method="auto",
        context={"metric_name": "row_count", "day_of_week": 5, "same_segment_history": SATURDAY_HISTORY},
    )
    assert result["is_anomaly"] is True


def test_auto_does_not_flag_a_legitimate_saturday_value():
    result = detect_metric(
        258,
        MIXED_HISTORY,
        method="auto",
        context={"metric_name": "row_count", "day_of_week": 5, "same_segment_history": SATURDAY_HISTORY},
    )
    assert result["is_anomaly"] is False
