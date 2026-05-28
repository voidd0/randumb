from __future__ import annotations

from typing import Any

from psycopg.types.json import Jsonb

from .db import execute, fetch_all


TOOLS = ["huanshu", "axe-core-playwright", "pa11y", "lighthouse-ci", "pixelmatch"]
TOOL_ALIASES = {
    "huanshu-local": "huanshu",
    "huanshu-local-adapter": "huanshu",
    "huashu": "huanshu",
    "huashu-design": "huanshu",
    "huashu-design-plugin": "huanshu",
    "@axe-core/playwright": "axe-core-playwright",
    "axe": "axe-core-playwright",
    "@lhci/cli": "lighthouse-ci",
    "lhci": "lighthouse-ci",
}


def normalize_quality_tool(tool: str) -> str:
    raw = (tool or "huanshu").strip().lower()
    normalized = TOOL_ALIASES.get(raw, raw)
    if normalized not in TOOLS:
        raise ValueError("unknown_quality_tool")
    return normalized


def record_quality_plugin_run(tool: str, target: str, status: str, score: int = 0, issues: list[dict[str, Any]] | None = None, artifact_path: str = "") -> dict[str, Any]:
    tool = normalize_quality_tool(tool)
    artifact_path = artifact_path or ""
    row = execute(
        """
        INSERT INTO quality_plugin_runs(tool, target, status, score, issues_json, artifact_path)
        VALUES (%s, %s, %s, %s, %s, %s)
        RETURNING *
        """,
        (tool, target, status, score, Jsonb(issues or []), artifact_path),
    )
    return dict(row)


def quality_plugin_manifest() -> dict[str, Any]:
    return {
        "canonical": "huanshu",
        "additional_plugins": [
            {"tool": "axe-core-playwright", "package": "@axe-core/playwright", "purpose": "accessibility DOM assertions"},
            {"tool": "pa11y", "package": "pa11y", "purpose": "WCAG page audit CLI"},
            {"tool": "lighthouse-ci", "package": "@lhci/cli", "purpose": "performance/accessibility/best-practice budget"},
            {"tool": "pixelmatch", "package": "pixelmatch + pngjs", "purpose": "screenshot regression checks"},
        ],
        "decision_rule": "huanshu must PASS and additional plugin blockers must be zero before publishing money-facing visuals",
    }


def latest_quality_summary() -> dict[str, Any]:
    rows = fetch_all(
        """
        SELECT DISTINCT ON (tool, target) tool, target, status, score, issues_json, artifact_path, created_at
        FROM quality_plugin_runs
        ORDER BY tool, target, created_at DESC
        """
    )
    blockers = [row for row in rows if row["status"] not in {"PASS", "PASS_WITH_WARNINGS"}]
    return {"tools": TOOLS, "runs": rows, "blockers": blockers, "all_pass": not blockers and bool(rows)}
