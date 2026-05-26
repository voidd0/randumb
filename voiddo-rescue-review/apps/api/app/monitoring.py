from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from psycopg.types.json import Jsonb

from .config import get_settings
from .db import execute, fetch_all, fetch_one
from .p0 import effective_pause_state, json_safe
from .scanner import deterministic_safe_scan


def normalize_domain(url: str) -> str:
    parsed = urlparse(url if "://" in url else f"https://{url}")
    return (parsed.netloc or parsed.path).removeprefix("www.").lower().strip("/")


def ensure_monitoring_target(customer_id: str, site_url: str) -> dict[str, Any]:
    domain = normalize_domain(site_url)
    existing = fetch_one("SELECT * FROM monitoring_targets WHERE customer_id = %s AND domain = %s ORDER BY created_at DESC LIMIT 1", (customer_id, domain))
    if existing:
        return dict(existing)
    row = execute(
        """
        INSERT INTO monitoring_targets(customer_id, domain, site_url, status)
        VALUES (%s, %s, %s, 'active')
        RETURNING *
        """,
        (customer_id, domain, site_url if site_url.startswith(("http://", "https://")) else f"https://{domain}"),
    )
    return dict(row)


def run_monitoring_check(target_id: str, dry_run: bool = True) -> dict[str, Any]:
    target = fetch_one("SELECT * FROM monitoring_targets WHERE id = %s", (target_id,))
    if not target:
        raise ValueError("monitoring_target_not_found")
    if dry_run:
        scan = deterministic_safe_scan(target["site_url"], target["domain"])
        row = execute(
            """
            INSERT INTO monitoring_runs(monitoring_target_id, status, score, summary, result_json, completed_at)
            VALUES (%s, 'completed', %s, %s, %s, now())
            RETURNING *
            """,
            (target_id, scan.score, scan.summary, Jsonb(json_safe(scan.model_dump()))),
        )
        execute("UPDATE monitoring_targets SET last_checked_at = now(), status = 'active' WHERE id = %s", (target_id,))
        return dict(row)
    job = execute(
        """
        INSERT INTO scanner_jobs(url, business_name, dry_run, status, result_json)
        VALUES (%s, %s, false, 'queued', %s)
        RETURNING id
        """,
        (target["site_url"], target["domain"], Jsonb({"monitoring_target_id": str(target["id"])})),
    )
    row = execute(
        """
        INSERT INTO monitoring_runs(monitoring_target_id, scanner_job_id, status, result_json)
        VALUES (%s, %s, 'queued', %s)
        RETURNING *
        """,
        (target_id, job["id"], Jsonb({"policy": "safe_public_scanner_job_queued"})),
    )
    return dict(row)


def process_due_monitoring_targets(limit: int = 5, dry_run: bool = True) -> dict[str, Any]:
    settings = get_settings()
    if settings.global_kill_switch or effective_pause_state("scanner", settings.scanning_paused):
        return {"status": "blocked_paused", "processed": 0, "failed": 0, "sends_started": False}
    targets = fetch_all(
        """
        SELECT id
        FROM monitoring_targets
        WHERE status = 'active'
          AND (last_checked_at IS NULL OR last_checked_at <= now() - interval '24 hours')
        ORDER BY last_checked_at NULLS FIRST, created_at
        LIMIT %s
        """,
        (limit,),
    )
    processed = 0
    failed = 0
    runs: list[dict[str, Any]] = []
    for target in targets:
        try:
            run = run_monitoring_check(str(target["id"]), dry_run=dry_run)
            runs.append({"target_id": str(target["id"]), "run_id": str(run["id"]), "status": run["status"]})
            processed += 1
        except Exception as exc:
            failed += 1
            execute(
                """
                INSERT INTO system_events(type, severity, message, payload_json)
                VALUES ('monitoring.run_failed', 'warning', 'Monitoring target check failed', %s)
                """,
                (Jsonb({"target_id": str(target["id"]), "error": type(exc).__name__, "safe": True}),),
            )
            task = execute(
                """
                INSERT INTO codex_tasks(type, priority, status, title, description, input_json)
                VALUES ('scanner_failed_case', 'P2', 'open', 'Monitoring check failed', %s, %s)
                RETURNING *
                """,
                (
                    "A safe monitoring check failed and needs studio review before any customer-facing action.",
                    Jsonb({"target_id": str(target["id"]), "error": type(exc).__name__, "safe": True}),
                ),
            )
            runs.append({"target_id": str(target["id"]), "status": "failed", "codex_task_id": str(task["id"])})
    return {"status": "completed", "processed": processed, "failed": failed, "runs": runs, "sends_started": False, "dry_run": dry_run}
