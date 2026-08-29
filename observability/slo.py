from __future__ import annotations

from typing import Any


def calculate_slo(target: float, bad_events: int, total_events: int) -> dict[str, Any]:
    if not 0 < target < 1:
        raise ValueError("target must be between 0 and 1 (exclusive)")
    if bad_events < 0 or total_events < 0 or bad_events > total_events:
        raise ValueError("invalid event counts")
    allowed_bad_rate = 1.0 - target
    if total_events == 0:
        return {
            "target": target,
            "actual_bad_rate": 0.0,
            "allowed_bad_rate": allowed_bad_rate,
            "burn_rate": 0.0,
            "remaining_error_budget_fraction": 1.0,
            "breached": False,
        }
    actual_bad_rate = bad_events / total_events
    burn_rate = actual_bad_rate / allowed_bad_rate
    consumed_fraction = min(1.0, actual_bad_rate / allowed_bad_rate)
    return {
        "target": target,
        "actual_bad_rate": actual_bad_rate,
        "allowed_bad_rate": allowed_bad_rate,
        "burn_rate": burn_rate,
        "remaining_error_budget_fraction": max(0.0, 1.0 - consumed_fraction),
        "breached": bool(actual_bad_rate > allowed_bad_rate),
    }


def evaluate_multiwindow_burn(
    *,
    short_window_burn: float,
    long_window_burn: float,
    policy: str = "google_sre_multiwindow",
    fast_burn_threshold: float = 14.4,
    slow_burn_threshold: float = 6.0,
) -> dict[str, Any]:
    """Multi-window burn-rate paging policy (Google SRE Workbook style).

    A single window can't tell a real sustained incident apart from a brief
    spike that has already recovered -- both look identical while they're
    happening. Requiring the LONG window to *also* be elevated is what tells
    them apart: a short blip gets diluted away by the long window's much
    larger sample of otherwise-good events, so its long-window burn stays low
    even though its short-window burn spiked. Only a burn that is fast in
    BOTH windows has actually been sustained long enough to page on.

    - fast in both windows      -> page now (critical)
    - fast short-window spike, long window still low -> transient, no page (warning)
    - slow but sustained in both windows -> ticket, no page (warning)
    - otherwise -> healthy (info)
    """
    fast_both = short_window_burn >= fast_burn_threshold and long_window_burn >= fast_burn_threshold
    transient_spike = short_window_burn >= fast_burn_threshold and long_window_burn < slow_burn_threshold
    slow_both = short_window_burn >= slow_burn_threshold and long_window_burn >= slow_burn_threshold

    if fast_both:
        page, severity = True, "critical"
        reason = (
            f"fast sustained burn: short={short_window_burn:.2f} and "
            f"long={long_window_burn:.2f} both >= {fast_burn_threshold} -- page now"
        )
    elif transient_spike:
        page, severity = False, "warning"
        reason = (
            f"transient spike: short={short_window_burn:.2f} >= {fast_burn_threshold} but "
            f"long={long_window_burn:.2f} < {slow_burn_threshold} -- not sustained, no page"
        )
    elif slow_both:
        page, severity = False, "warning"
        reason = (
            f"sustained slow burn: short={short_window_burn:.2f} and "
            f"long={long_window_burn:.2f} both >= {slow_burn_threshold} but below the fast-burn "
            f"threshold -- file a ticket, no page"
        )
    else:
        page, severity = False, "info"
        reason = f"within budget: short={short_window_burn:.2f}, long={long_window_burn:.2f}"

    return {
        "page": page,
        "severity": severity,
        "reason": reason,
        "short_window_burn": short_window_burn,
        "long_window_burn": long_window_burn,
        "policy": policy,
    }
