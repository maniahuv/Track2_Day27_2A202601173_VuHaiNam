"""Contract validator: deterministic checks driven by a YAML data contract.

Covers not-null/unique/accepted-values/range, declared-type drift, and
contract-level freshness. Each issue carries a severity-aware `action`
(block/quarantine/warn); `pipeline_action` aggregates the strictest one
across a batch. Cross-field/cross-table assertions and richer observability
metadata are still open extension points.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
import yaml


ACTION_BY_SEVERITY = {"critical": "block", "warning": "quarantine", "info": "warn"}


def action_for_severity(severity: str) -> str:
    return ACTION_BY_SEVERITY.get(severity, "warn")


def _issue(
    check: str,
    *,
    column: str | None,
    severity: str,
    passed: bool,
    details: str,
) -> dict[str, Any]:
    return {
        "check": check,
        "column": column,
        "severity": severity,
        "passed": bool(passed),
        "action": action_for_severity(severity),
        "details": details,
    }


def load_contract(path: str | Path) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _type_invalid_mask(series: pd.Series, declared_type: str) -> pd.Series:
    """Boolean mask of non-null values that violate the contract's declared type.

    pd.to_numeric(..., errors="coerce") alone turns bad values into NaN, which the
    range check then silently ignores. This mask makes that drift visible instead.
    """
    notna = series.notna()
    declared_type = declared_type.lower()

    if declared_type in {"integer", "int"}:
        numeric = pd.to_numeric(series, errors="coerce")
        non_numeric = notna & numeric.isna()
        non_integer = notna & numeric.notna() & (numeric % 1 != 0)
        return non_numeric | non_integer

    if declared_type in {"number", "float", "numeric"}:
        numeric = pd.to_numeric(series, errors="coerce")
        return notna & numeric.isna()

    if declared_type in {"datetime", "timestamp", "date"}:
        parsed = pd.to_datetime(series, utc=True, errors="coerce")
        return notna & parsed.isna()

    if declared_type in {"boolean", "bool"}:
        valid = {True, False, "true", "false", "True", "False", 0, 1, "0", "1"}
        return notna & ~series.isin(valid)

    if declared_type in {"string", "str", "text"}:
        return notna & pd.Series(pd.api.types.is_numeric_dtype(series), index=series.index)

    return pd.Series(False, index=series.index)


def _validate_freshness(df: pd.DataFrame, freshness: dict[str, Any] | None) -> dict[str, Any] | None:
    if not freshness:
        return None
    column = freshness.get("column")
    max_delay = freshness.get("max_delay_minutes")
    severity = freshness.get("severity", "warning")
    if column is None or max_delay is None or column not in df.columns:
        return None

    parsed = pd.to_datetime(df[column], utc=True, errors="coerce")
    if parsed.notna().sum() == 0:
        return _issue(
            "freshness",
            column=column,
            severity=severity,
            passed=False,
            details=f"no_valid_timestamps_in_{column}",
        )

    latest = parsed.max()
    delay_minutes = (pd.Timestamp.now(tz="UTC") - latest).total_seconds() / 60.0
    return _issue(
        "freshness",
        column=column,
        severity=severity,
        passed=(delay_minutes <= max_delay),
        details=f"latest={latest.isoformat()}, delay_minutes={delay_minutes:.2f}, max_delay_minutes={max_delay}",
    )


def validate_dataframe(df: pd.DataFrame, contract: dict[str, Any]) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    columns = contract.get("columns", {})

    for column, rules in columns.items():
        severity = rules.get("severity", "warning")
        required = bool(rules.get("required", False))

        if column not in df.columns:
            if required:
                issues.append(
                    _issue(
                        "required_column",
                        column=column,
                        severity=severity,
                        passed=False,
                        details=f"Missing required column: {column}",
                    )
                )
            continue

        series = df[column]

        if required:
            null_count = int(series.isna().sum())
            issues.append(
                _issue(
                    "not_null",
                    column=column,
                    severity=severity,
                    passed=(null_count == 0),
                    details=f"null_count={null_count}",
                )
            )

        if rules.get("unique"):
            duplicate_count = int(series.duplicated(keep=False).sum())
            issues.append(
                _issue(
                    "unique",
                    column=column,
                    severity=severity,
                    passed=(duplicate_count == 0),
                    details=f"duplicate_rows={duplicate_count}",
                )
            )

        accepted = rules.get("accepted_values")
        if accepted is not None:
            invalid_mask = series.notna() & ~series.isin(accepted)
            invalid_count = int(invalid_mask.sum())
            issues.append(
                _issue(
                    "accepted_values",
                    column=column,
                    severity=severity,
                    passed=(invalid_count == 0),
                    details=f"invalid_count={invalid_count}; accepted={accepted}",
                )
            )

        if "min" in rules or "max" in rules:
            numeric = pd.to_numeric(series, errors="coerce")
            invalid = pd.Series(False, index=series.index)
            if "min" in rules:
                invalid |= numeric < rules["min"]
            if "max" in rules:
                invalid |= numeric > rules["max"]
            invalid_count = int(invalid.fillna(False).sum())
            issues.append(
                _issue(
                    "range",
                    column=column,
                    severity=severity,
                    passed=(invalid_count == 0),
                    details=f"invalid_count={invalid_count}",
                )
            )

        declared_type = rules.get("type")
        if declared_type:
            invalid_mask = _type_invalid_mask(series, declared_type)
            invalid_count = int(invalid_mask.sum())
            issues.append(
                _issue(
                    "type",
                    column=column,
                    severity=severity,
                    passed=(invalid_count == 0),
                    details=f"declared_type={declared_type}; invalid_count={invalid_count}",
                )
            )

    freshness_issue = _validate_freshness(df, contract.get("freshness"))
    if freshness_issue is not None:
        issues.append(freshness_issue)

    return issues


def failed_issues(issues: list[dict[str, Any]], min_severity: str | None = None) -> list[dict[str, Any]]:
    failed = [i for i in issues if not i.get("passed", False)]
    if min_severity is None:
        return failed
    order = {"info": 0, "warning": 1, "critical": 2}
    threshold = order[min_severity]
    return [i for i in failed if order.get(i.get("severity", "warning"), 1) >= threshold]


def pipeline_action(issues: list[dict[str, Any]]) -> str:
    """Strictest action implied by failed issues: block > quarantine > warn > none."""
    priority = {"block": 3, "quarantine": 2, "warn": 1}
    action = "none"
    rank = 0
    for issue in issues:
        if issue.get("passed", False):
            continue
        candidate = issue.get("action", "warn")
        candidate_rank = priority.get(candidate, 1)
        if candidate_rank > rank:
            rank = candidate_rank
            action = candidate
    return action
