from __future__ import annotations

import json
from collections import deque
from pathlib import Path
from typing import Any


def load_graph(path: str | Path) -> dict[str, list[str]]:
    with open(path, "r", encoding="utf-8") as f:
        payload = json.load(f)
    return payload["dataset_lineage"] if "dataset_lineage" in payload else payload


def load_column_graph(path: str | Path) -> dict[str, list[str]]:
    with open(path, "r", encoding="utf-8") as f:
        payload = json.load(f)
    return payload.get("column_lineage", {})


def _bfs_downstream(graph: dict[str, list[str]], start: str) -> list[str]:
    """Transitive downstream nodes in BFS order, excluding start."""
    seen = {start}
    q: deque[str] = deque([start])
    out: list[str] = []
    while q:
        node = q.popleft()
        for child in graph.get(node, []):
            if child not in seen:
                seen.add(child)
                out.append(child)
                q.append(child)
    return out


def get_downstream_assets(graph: dict[str, list[str]], start: str) -> list[str]:
    """Return transitive downstream assets in BFS order, excluding start."""
    return _bfs_downstream(graph, start)


def get_column_downstream(column_graph: dict[str, list[str]], start_column: str) -> list[str]:
    """Return transitive downstream columns in BFS order, excluding start_column."""
    return _bfs_downstream(column_graph, start_column)


def extract_dbt_dataset_graph(
    manifest_path: str | Path, *, node_types: set[str] | None = None
) -> dict[str, list[str]]:
    """dbt manifest parser: dataset lineage keyed by friendly node name.

    dbt's `child_map` is keyed by verbose unique_ids like
    "model.data_reliability_lab.stg_orders". This reduces each id to its
    resource name so the result composes with the same BFS traversal as the
    hand-authored data/baseline/lineage_graph.json, and drops test/unit_test
    nodes by default (`node_types` defaults to {"model", "seed"}) since those
    are checks, not downstream data assets.
    """
    path = Path(manifest_path)
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    allowed_types = node_types or {"model", "seed"}

    def resource_type(unique_id: str) -> str:
        return unique_id.split(".")[0]

    def friendly_name(unique_id: str) -> str:
        return unique_id.split(".")[-1]

    graph: dict[str, list[str]] = {}
    for parent, children in manifest.get("child_map", {}).items():
        if resource_type(parent) not in allowed_types:
            continue
        graph[friendly_name(parent)] = [
            friendly_name(child) for child in children if resource_type(child) in allowed_types
        ]
    return graph
