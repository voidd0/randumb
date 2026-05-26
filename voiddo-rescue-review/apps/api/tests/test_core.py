from app.billing import checkout_config_status, hosted_checkout_url
from app.config import Settings
from app.email_quality import check_email_quality
from app.inbox import classify_reply
from app.outreach import outreach_allowed, render_template
from app.scanner import deterministic_safe_scan
from app.security import verify_paddle_signature

import hashlib
import hmac


def test_scanner_dry_run_generates_qualified_shape():
    result = deterministic_safe_scan("https://example.com", "Example")
    assert result.domain == "example.com"
    assert result.public_slug.startswith("example-com-")
    assert result.issues
    assert result.score < 100


def test_outreach_template_contains_unsubscribe_and_prices():
    rendered = render_template(
        "en",
        {
            "business_name": "Example Dental",
            "domain": "example.com",
            "main_issue_short": "The contact form may not be visible on mobile.",
            "audit_url": "https://audit.rescue.voiddo.com/r/demo",
            "unsubscribe_url": "https://go.rescue.voiddo.com/unsubscribe/demo",
        },
    )
    assert "Possible issue" in rendered["subject"]
    assert "Public non-invasive website check" in rendered["body"]
    assert "Unsubscribe:" in rendered["body"]
    assert rendered["qa_passed"] == "True"


def test_rate_limit_blocks_when_paused():
    settings = Settings(outreach_paused=True)
    decision = outreach_allowed(settings, suppressed=False, sent_today=0, sent_this_domain_hour=0)
    assert not decision.allowed
    assert decision.reason == "outreach_paused"


def test_inbox_classifier_marks_unsafe_security_accusation():
    result = classify_reply("Re: website", "This looks like an unauthorized security scan")
    assert result["classification"] == "security_accusation"
    assert result["human_review_required"] is True
    assert result["auto_reply_allowed"] is False


def test_inbox_classifier_treats_delivery_observation_as_autonomous_signal():
    result = classify_reply("Re: diagnostic", "All fine, found it in spam, starred and answered")
    assert result["classification"] == "auto_reply"
    assert result["human_review_required"] is False
    assert result["auto_reply_allowed"] is False




def test_paddle_signature_mock():
    secret = "test_secret"
    body = b'{"event_type":"transaction.paid"}'
    ts = "1700000000"
    digest = hmac.new(secret.encode(), ts.encode() + b":" + body, hashlib.sha256).hexdigest()
    assert verify_paddle_signature(body, f"ts={ts};h1={digest}", secret)
    assert not verify_paddle_signature(body, f"ts={ts};h1=bad", secret)


def test_billing_config_reports_missing_prices():
    status = checkout_config_status(
        Settings(
            _env_file=None,
            paddle_api_key="",
            paddle_webhook_secret="",
            paddle_price_monitor_monthly="",
            paddle_price_fix_lite_monthly="",
            paddle_price_rescue_pro_monthly="",
            paddle_price_audit_onetime="",
            paddle_price_contact_form_repair="",
            paddle_price_emergency_fix="",
        )
    )
    assert status["ready"] is False
    assert "monitor_monthly" in status["missing_price_keys"]


def test_hosted_checkout_url_requires_configured_base_and_price():
    missing = hosted_checkout_url(Settings(_env_file=None), "contact_form_repair", "demo")
    assert missing == ""
    url = hosted_checkout_url(
        Settings(
            _env_file=None,
            paddle_hosted_checkout_base_url="https://pay.paddle.io/checkout/hsc_test",
            paddle_price_contact_form_repair="pri_test_contact",
        ),
        "contact_form_repair",
        "demo audit",
        "buyer@example.com",
    )
    assert url.startswith("https://pay.paddle.io/checkout/hsc_test?")
    assert "price_id=pri_test_contact" in url
    assert "utm_content=demo+audit" in url
    assert "user_email=buyer%40example.com" in url


def test_email_quality_blocks_risky_copy():
    result = check_email_quality("URGENT security vulnerability", "You are hacked. Act now.")
    assert result.passed is False
    assert any(issue.startswith("risky_phrase") for issue in result.issues)
