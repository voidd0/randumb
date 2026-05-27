from __future__ import annotations

import os
import uuid
from io import StringIO
import csv

from fastapi.testclient import TestClient

from app.audit_strength import score_audit_strength
from app.db import execute, fetch_one
from app.language_gate import check_no_ai_public_language
from app.main import app
from app.scout_quality import run_scout_self_check
from app.scouts import create_scout_run, create_scout_source, prepare_scout_source_from_adapter, process_scout_run
from app.source_adapters import directory_rows_to_csv, domain_list_to_csv, normalize_domain


client = TestClient(app)


def admin_headers() -> dict[str, str]:
    return {"X-Admin-Token": os.environ["ADMIN_AUTH_TOKEN"]}


def test_domain_list_adapter_normalizes_and_dedupes():
    csv_text = domain_list_to_csv("https://www.example.com\nexample.com, test.com", "EE", "dentists")
    rows = list(csv.DictReader(StringIO(csv_text)))
    assert [row["website_url"] for row in rows] == ["https://example.com", "https://test.com"]


def test_directory_adapter_outputs_import_csv():
    csv_text = directory_rows_to_csv("name,website,email,city\nAcme,https://acme.example.test,hi@acme.example.test,Tallinn", "EE", "dentists")
    assert "Acme" in csv_text
    assert "hi@acme.example.test" in csv_text


def test_adapter_source_preflight_creates_readiness_without_processing_or_leaking_recipients():
    token = uuid.uuid4().hex[:8]
    result = prepare_scout_source_from_adapter(
        "directory",
        {
            "name": f"p80-directory-{token}",
            "csv": f"name,website,email,city,source_url\nAcme,https://p80-{token}.example.test,owner@p80-{token}.example.test,Tallinn,https://directory.example.test/acme\n",
            "country": "EE",
            "language": "en",
            "niche": "dentists",
        },
    )
    try:
        assert result["source"]["config_redacted"] is True
        assert result["readiness"]["status"] == "PASS_SOURCE_READY"
        assert result["created_scout_runs"] == 0
        assert result["created_scanner_jobs"] == 0
        assert result["processed_now"] is False
        assert result["send_mail"] is False
        assert result["live_outreach_allowed"] is False
        assert result["raw_recipient_addresses_included"] is False
        assert "owner@" not in str(result)
    finally:
        execute("DELETE FROM scout_source_readiness_checks WHERE source_id = %s", (result["source"]["id"],))
        execute("DELETE FROM scout_sources WHERE id = %s", (result["source"]["id"],))


def test_normalize_domain_removes_www_and_paths():
    assert normalize_domain("https://www.example.com/path") == "example.com"


def test_scout_self_check_passes_for_accepted_run():
    token = uuid.uuid4().hex[:8]
    csv_text = f"business_name,website_url,email,country,niche\nOne,https://self-{token}.example.test,a@self-{token}.example.test,QA,p8_niche\n"
    source = create_scout_source({"name": f"self-check-{token}", "source_type": "manual_csv_scout", "config_json": {"csv": csv_text}})
    run = create_scout_run(str(source["id"]))
    process_scout_run(str(run["id"]))
    check = run_scout_self_check(str(run["id"]))
    assert check["status"] == "pass"
    assert check["accepted_count"] == 1


def test_scout_self_check_flags_empty_run():
    run = execute("INSERT INTO scout_runs(status) VALUES ('completed') RETURNING id")
    check = run_scout_self_check(str(run["id"]))
    assert check["status"] == "needs_review"


def test_audit_strength_scores_proof_and_commercial_quality():
    token = uuid.uuid4().hex[:8]
    business = execute("INSERT INTO businesses(name, domain, source) VALUES (%s, %s, 'p8_test') RETURNING id", (f"Audit {token}", f"audit-{token}.example.test"))
    lead = execute("INSERT INTO leads(business_id, email, source) VALUES (%s, %s, 'p8_test') RETURNING id", (business["id"], f"owner@audit-{token}.example.test"))
    audit = execute("INSERT INTO audits(business_id, lead_id, domain, url, status, score, summary, public_slug, checked_at) VALUES (%s, %s, %s, %s, 'completed', 80, 'Strong summary', %s, now()) RETURNING id", (business["id"], lead["id"], f"audit-{token}.example.test", f"https://audit-{token}.example.test", f"audit-{token}"))
    for i in range(3):
        execute("INSERT INTO audit_issues(audit_id, issue_type, severity, title, public_text) VALUES (%s, 'contact', 'high', 'Issue', 'Issue text')", (audit["id"],))
    execute("INSERT INTO screenshots(audit_id, type, file_path, public_url, viewport) VALUES (%s, 'desktop', '/tmp/x.png', '/media/x.png', 'desktop')", (audit["id"],))
    score = score_audit_strength(str(audit["id"]))
    assert score["final_score"] >= 70


def test_audit_strength_flags_missing_evidence():
    token = uuid.uuid4().hex[:8]
    business = execute("INSERT INTO businesses(name, domain, source) VALUES (%s, %s, 'p8_test') RETURNING id", (f"Weak {token}", f"weak-{token}.example.test"))
    audit = execute("INSERT INTO audits(business_id, domain, url, status, score, public_slug, checked_at) VALUES (%s, %s, %s, 'completed', 40, %s, now()) RETURNING id", (business["id"], f"weak-{token}.example.test", f"https://weak-{token}.example.test", f"weak-{token}"))
    score = score_audit_strength(str(audit["id"]))
    assert any(issue["code"] == "missing_screenshots" for issue in score["issues_json"])


def test_no_ai_public_language_gate_passes_templates():
    result = check_no_ai_public_language()
    assert result["status"] == "pass"


def test_no_ai_public_language_gate_fails_bad_sample():
    result = check_no_ai_public_language([{"name": "bad", "text": "Generated by AI"}], "pytest_bad")
    assert result["status"] == "fail"


def test_p8_admin_endpoints_work():
    assert client.post("/admin/source-adapters/domain-list", json={"text": "example.com"}).status_code == 401
    assert client.post("/admin/source-adapters/domain-list", json={"text": "example.com"}, headers=admin_headers()).status_code == 200
    assert client.post("/admin/source-adapters/domain-list/source", json={"text": "example.com"}).status_code == 401
    response = client.post(
        "/admin/source-adapters/domain-list/source",
        json={"text": "p80-admin-source.example.test", "country": "EE", "niche": "dentists", "name": "p80-admin-source"},
        headers=admin_headers(),
    )
    assert response.status_code == 200
    payload = response.json()["result"]
    try:
        assert payload["created_scout_runs"] == 0
        assert payload["created_scanner_jobs"] == 0
        assert payload["source"]["config_redacted"] is True
        assert payload["readiness"]["send_mail"] is False
    finally:
        execute("DELETE FROM scout_source_readiness_checks WHERE source_id = %s", (payload["source"]["id"],))
        execute("DELETE FROM scout_sources WHERE id = %s", (payload["source"]["id"],))
    assert client.post("/admin/language/no-ai-gate", json={"samples": [{"name": "ok", "text": "Built by Vøiddo Rescue"}]}, headers=admin_headers()).status_code == 200


def test_p8_tables_exist():
    for table in ["scout_self_checks", "audit_strength_scores", "public_language_gate_runs"]:
        row = fetch_one("SELECT to_regclass(%s) AS name", (table,))
        assert row["name"] == table
