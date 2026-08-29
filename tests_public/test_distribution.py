from student_api import detect_distribution


def test_extreme_mean_shift_detected():
    baseline = [9, 10, 11, 10, 10]
    current = [190, 200, 210, 205]
    assert detect_distribution(current, baseline)["is_anomaly"] is True


def test_shape_only_shift_missed_by_mean_ratio_is_caught_by_psi():
    # Same mean as baseline, but spread across [0, 20] instead of a tight
    # cluster around 10 -- a mean-ratio check (ratio ~= 1.0) would completely
    # miss this. PSI compares the binned shape, not just the average.
    baseline = [9.8, 10.0, 10.1, 9.9, 10.0, 10.2, 9.9, 10.0, 10.1, 9.9, 10.0, 10.0, 9.9, 10.1, 10.0]
    current = [0, 2, 4, 6, 8, 10, 12, 14, 16, 18, 20, 10, 10, 10, 10]
    assert detect_distribution(current, baseline)["is_anomaly"] is True
