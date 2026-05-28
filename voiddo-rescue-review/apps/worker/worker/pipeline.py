from __future__ import annotations

import json
import multiprocessing as mp
import os
from typing import Any
from urllib.parse import urlparse

from psycopg.types.json import Jsonb

from .db import connect
from .scanner import safe_public_scan


class ScannerJobTimeout(RuntimeError):
    pass


class ScannerChildError(RuntimeError):
    def __init__(self, error_type: str):
        super().__init__(error_type)
        self.error_type = error_type


def _scan_child(url: str, storage_root: str, queue: mp.Queue) -> None:
    try:
        queue.put({"ok": True, "result": safe_public_scan(url, storage_root)})
    except Exception as exc:
        queue.put({"ok": False, "error": type(exc).__name__})


def run_safe_public_scan_with_timeout(url: str, storage_root: str) -> dict[str, Any]:
    timeout_seconds = max(30, min(int(os.environ.get("SCANNER_JOB_TIMEOUT_SECONDS", "150") or 150), 300))
    queue: mp.Queue = mp.Queue(maxsize=1)
    process = mp.Process(target=_scan_child, args=(url, storage_root, queue), daemon=True)
    process.start()
    process.join(timeout_seconds)
    if process.is_alive():
        process.terminate()
        process.join(5)
        if process.is_alive():
            process.kill()
            process.join(5)
        raise ScannerJobTimeout(f"scanner_job_timeout_{timeout_seconds}s")
    if queue.empty():
        raise RuntimeError("scanner_child_exited_without_result")
    payload = queue.get()
    if payload.get("ok"):
        return payload["result"]
    raise ScannerChildError(str(payload.get("error") or "scanner_child_error"))


def timeout_scan_result(url: str, timeout_seconds: int) -> dict[str, Any]:
    from .scanner import _slug

    parsed = urlparse(url)
    domain = parsed.netloc.lower()
    issue = {
        "issue_type": "availability",
        "severity": "critical",
        "title": "Homepage timed out during public browser check",
        "public_text": "The homepage did not finish a safe public browser check within the allowed time window.",
        "recommendation": "Check hosting response time, blocking scripts, redirects, and heavy media before sending customers to the site.",
        "evidence_json": {"timeout_seconds": timeout_seconds, "mode": "safe_public_browser_timeout"},
    }
    return {
        "domain": domain,
        "url": url,
        "status": "completed",
        "http_status": 0,
        "duration_ms": timeout_seconds * 1000,
        "title": "",
        "meta_description": "",
        "h1": [],
        "counts": {"links": 0, "forms": 0, "mailto": 0, "tel": 0, "whatsapp": 0, "booking": 0},
        "contact_evidence": {
            "mailto_emails": [],
            "has_phone_link": False,
            "has_whatsapp_link": False,
            "has_booking_link": False,
            "has_form": False,
        },
        "public_slug": _slug(url),
        "score": 55,
        "issues": [issue],
        "screenshots": [],
        "robots_url": "",
        "sitemap_url": "",
        "safe_scan": True,
        "partial_audit": True,
        "partial_reason": "scanner_job_timeout",
    }


def claim_scanner_job() -> dict[str, Any] | None:
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                WITH picked AS (
                  SELECT id
                  FROM scanner_jobs
                  WHERE status = 'queued'
                  ORDER BY priority DESC, queued_at ASC
                  FOR UPDATE SKIP LOCKED
                  LIMIT 1
                )
                UPDATE scanner_jobs
                SET status = 'running', started_at = now(), updated_at = now()
                FROM picked
                WHERE scanner_jobs.id = picked.id
                RETURNING scanner_jobs.id, scanner_jobs.url, scanner_jobs.business_name, scanner_jobs.dry_run, scanner_jobs.priority, scanner_jobs.result_json
                """
            )
            row = cur.fetchone()
        conn.commit()
    return dict(row) if row else None


def _summary(result: dict[str, Any]) -> str:
    issues = result.get("issues") or []
    if not issues:
        return "Public browser check completed with no major visible issues."
    top = issues[0]
    return f"{top.get('title', 'Possible issue')} detected during a public non-invasive browser check."


def persist_scan_result(job: dict[str, Any], result: dict[str, Any]) -> str:
    audit_base_url = os.environ.get("AUDIT_BASE_URL", "https://audit.rescue.voiddo.com")
    api_base_url = os.environ.get("API_BASE_URL", "https://api.rescue.voiddo.com")
    with connect() as conn:
        with conn.cursor() as cur:
            business_id = None
            lead_id = None
            job_meta = job.get("result_json") or {}
            if isinstance(job_meta, str):
                try:
                    job_meta = json.loads(job_meta)
                except Exception:
                    job_meta = {}
            target_audit_id = job.get("audit_id")
            if target_audit_id:
                cur.execute("SELECT id, business_id, lead_id FROM audits WHERE id = %s", (target_audit_id,))
                target_audit = cur.fetchone()
                if target_audit:
                    business_id = target_audit.get("business_id")
                    lead_id = target_audit.get("lead_id")
                else:
                    target_audit_id = None
            if job_meta.get("lead_id"):
                cur.execute("SELECT id, business_id FROM leads WHERE id = %s", (job_meta["lead_id"],))
                lead = cur.fetchone()
                if lead:
                    lead_id = lead["id"]
                    business_id = lead["business_id"]
            contact_emails = []
            contact_evidence = result.get("contact_evidence") or {}
            if isinstance(contact_evidence, dict):
                contact_emails = [str(item).strip().lower() for item in contact_evidence.get("mailto_emails") or [] if "@" in str(item)]
            discovered_email = contact_emails[0] if contact_emails else None
            if discovered_email:
                cur.execute("SELECT 1 FROM suppression_list WHERE lower(email) = lower(%s)", (discovered_email,))
                if cur.fetchone():
                    discovered_email = None
            if not business_id and job.get("business_name"):
                cur.execute(
                    """
                    INSERT INTO businesses(name, website_url, domain, source, status)
                    VALUES (%s, %s, %s, 'scanner_job', 'scanned')
                    RETURNING id
                    """,
                    (job["business_name"], result["url"], result["domain"]),
                )
                business_id = cur.fetchone()["id"]
            if target_audit_id:
                cur.execute(
                    """
                    UPDATE audits
                    SET status = 'completed',
                        business_id = COALESCE(%s, business_id),
                        lead_id = COALESCE(%s, lead_id),
                        domain = %s,
                        url = %s,
                        score = %s,
                        summary = %s,
                        checked_at = now()
                    WHERE id = %s
                    RETURNING id
                    """,
                    (business_id, lead_id, result["domain"], result["url"], result["score"], _summary(result), target_audit_id),
                )
            else:
                cur.execute(
                    """
                    INSERT INTO audits(business_id, lead_id, domain, url, status, score, summary, public_slug, checked_at)
                    VALUES (%s, %s, %s, %s, 'completed', %s, %s, %s, now())
                    ON CONFLICT (public_slug) DO UPDATE
                      SET status = 'completed',
                          business_id = COALESCE(EXCLUDED.business_id, audits.business_id),
                          lead_id = COALESCE(EXCLUDED.lead_id, audits.lead_id),
                          score = EXCLUDED.score,
                          summary = EXCLUDED.summary,
                          checked_at = now()
                    RETURNING id
                    """,
                    (business_id, lead_id, result["domain"], result["url"], result["score"], _summary(result), result["public_slug"]),
                )
            audit_id = cur.fetchone()["id"]
            if discovered_email and lead_id:
                cur.execute("UPDATE leads SET email = COALESCE(email, %s), updated_at = now() WHERE id = %s", (discovered_email, lead_id))
            if discovered_email and business_id:
                cur.execute("UPDATE businesses SET email = COALESCE(email, %s), updated_at = now() WHERE id = %s", (discovered_email, business_id))
            cur.execute("DELETE FROM audit_issues WHERE audit_id = %s", (audit_id,))
            cur.execute("DELETE FROM screenshots WHERE audit_id = %s", (audit_id,))
            for issue in result.get("issues", []):
                cur.execute(
                    """
                    INSERT INTO audit_issues(audit_id, issue_type, severity, title, public_text, internal_notes, evidence_json, recommendation)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        audit_id,
                        issue.get("issue_type", "unknown"),
                        issue.get("severity", "low"),
                        issue.get("title", "Possible issue"),
                        issue.get("public_text", ""),
                        "Generated by safe_public_scan.",
                        Jsonb(issue.get("evidence_json") or {}),
                        issue.get("recommendation", ""),
                    ),
                )
            for shot in result.get("screenshots", []):
                file_path = shot.get("file_path", "")
                public_url = ""
                marker = "/screenshots/"
                if marker in file_path:
                    public_url = f"{api_base_url}/media/screenshots/{file_path.split(marker, 1)[1]}"
                cur.execute(
                    """
                    INSERT INTO screenshots(audit_id, type, file_path, public_url, viewport)
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (audit_id, shot.get("type", "screenshot"), file_path, public_url, shot.get("viewport")),
                )
            persisted_result = dict(result)
            if job_meta:
                persisted_result["job_meta"] = job_meta
            if lead_id:
                persisted_result["lead_id"] = str(lead_id)
            if job_meta.get("scout_lead_id"):
                persisted_result["scout_lead_id"] = str(job_meta["scout_lead_id"])
            cur.execute(
                """
                UPDATE scanner_jobs
                SET status = 'completed', audit_id = %s, result_json = %s, completed_at = now(), updated_at = now()
                WHERE id = %s
                """,
                (audit_id, Jsonb(persisted_result), job["id"]),
            )
        conn.commit()
    return str(audit_id)


def fail_scanner_job(job_id: str, error: str) -> None:
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE scanner_jobs
                SET status = 'failed', error = %s, completed_at = now(), updated_at = now()
                WHERE id = %s
                """,
                (error[:1000], job_id),
            )
        conn.commit()


def process_one_scanner_job() -> dict[str, Any]:
    job = claim_scanner_job()
    if not job:
        return {"processed": False}
    try:
        result = run_safe_public_scan_with_timeout(job["url"], os.environ.get("STORAGE_ROOT", "/app/storage"))
        audit_id = persist_scan_result(job, result)
        return {"processed": True, "job_id": str(job["id"]), "priority": int(job.get("priority") or 0), "audit_id": audit_id, "slug": result.get("public_slug")}
    except ScannerJobTimeout:
        timeout_seconds = max(30, min(int(os.environ.get("SCANNER_JOB_TIMEOUT_SECONDS", "150") or 150), 300))
        result = timeout_scan_result(job["url"], timeout_seconds)
        audit_id = persist_scan_result(job, result)
        return {
            "processed": True,
            "job_id": str(job["id"]),
            "priority": int(job.get("priority") or 0),
            "audit_id": audit_id,
            "slug": result.get("public_slug"),
            "partial_audit": True,
        }
    except Exception as exc:
        error_type = getattr(exc, "error_type", type(exc).__name__)
        fail_scanner_job(str(job["id"]), error_type)
        return {"processed": True, "job_id": str(job["id"]), "priority": int(job.get("priority") or 0), "failed": True, "error": error_type}


def process_scanner_jobs(limit: int = 1) -> dict[str, Any]:
    safe_limit = max(1, min(int(limit or 1), 5))
    results: list[dict[str, Any]] = []
    for _ in range(safe_limit):
        result = process_one_scanner_job()
        if not result.get("processed"):
            break
        results.append(result)
    return {
        "processed": bool(results),
        "processed_count": len(results),
        "failed_count": len([item for item in results if item.get("failed")]),
        "max_per_tick": safe_limit,
        "results": results,
    }
