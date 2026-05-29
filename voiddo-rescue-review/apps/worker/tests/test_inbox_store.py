from __future__ import annotations

from worker.inbox_store import _bounce_reason, _extract_bounced_recipient


def test_bounce_reason_detects_domain_not_found():
    body = "Diagnostic-Code: smtp; 550 Host or domain name not found. Name service error for name=bad.example"
    assert _bounce_reason("Delivery Status Notification", body) == "domain_not_found"


def test_extract_bounced_recipient_from_final_recipient():
    body = "Final-Recipient: rfc822; Person@Example.test\nAction: failed"
    assert _extract_bounced_recipient(body) == "person@example.test"


def test_extract_bounced_recipient_missing_is_empty():
    assert _extract_bounced_recipient("delivery failed without address") == ""
