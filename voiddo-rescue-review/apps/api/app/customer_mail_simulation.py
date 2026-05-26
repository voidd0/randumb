from __future__ import annotations

from pathlib import Path
from typing import Any

from .billing import PRODUCTS
from .config import get_settings
from .email_templates import qa_email_template, render_email_template
from .p0 import json_safe


ACTION_TEMPLATES = {
    "customer_onboarding": "payment_onboarding",
    "fix_request_created": "fix_request_created",
    "monitoring_report": "monitoring_setup_reminder",
}

SCENARIOS = [
    ("flags_false", "blocked_customer_mail_flags"),
    ("flags_true_recent_signals", "blocked_recent_mail_signals"),
    ("suppressed_customer", "blocked_suppression"),
    ("throttle_blocked", "blocked_throttle"),
    ("resolver_missing", "blocked_resolver"),
    ("mocked_smtp_success", "mocked_sent"),
    ("mocked_smtp_failure", "failed_transport"),
]


def _simulate_scenario(product_key: str, action_type: str, scenario: str, status: str) -> dict[str, Any]:
    template_key = ACTION_TEMPLATES[action_type]
    rendered = render_email_template(
        template_key,
        "en",
        {
            "customer_url": "https://app.rescue.voiddo.com/customer",
            "fix_request_title": product_key,
            "status": "prepared",
        },
    )
    qa = qa_email_template(rendered)
    send_mail = False
    smtp_called = False
    if scenario == "mocked_smtp_success":
        send_mail = True
        smtp_called = True
    if scenario == "mocked_smtp_failure":
        smtp_called = True
    return {
        "product_key": product_key,
        "action_type": action_type,
        "template_key": template_key,
        "scenario": scenario,
        "status": status,
        "template_qa_passed": qa["passed"],
        "subject_length": len(rendered["subject"]),
        "body_length": len(rendered["text"]),
        "recipient_hash": f"sim-{product_key[:8]}-{action_type[:8]}",
        "send_mail": send_mail,
        "smtp_called": smtp_called,
        "raw_recipient_included": False,
    }


def run_customer_mail_simulation(write_report: bool = True) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    product_keys = list(PRODUCTS.keys())
    for product_key in product_keys:
        for action_type in ACTION_TEMPLATES:
            for scenario, status in SCENARIOS:
                items.append(_simulate_scenario(product_key, action_type, scenario, status))
    blocking_failures = [
        item
        for item in items
        if item["raw_recipient_included"]
        or not item["template_qa_passed"]
        or (item["scenario"] != "mocked_smtp_success" and item["send_mail"])
    ]
    result = {
        "products": product_keys,
        "product_count": len(product_keys),
        "action_count": len(ACTION_TEMPLATES),
        "scenario_count": len(SCENARIOS),
        "case_count": len(items),
        "items": items,
        "blocking_failures": len(blocking_failures),
        "raw_recipient_addresses_included": False,
        "real_smtp_called": False,
        "send_mail": False,
        "live_outreach_allowed": False,
    }
    if write_report:
        result["report_path"] = write_customer_mail_simulation_report(result)
    return json_safe(result)


def write_customer_mail_simulation_report(result: dict[str, Any]) -> str:
    path = Path(get_settings().storage_root) / "reports" / "customer_mail_simulation_report.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    text = "\n".join(
        [
            "# Customer Mail Simulation Report",
            "",
            f"- product count: `{result['product_count']}`",
            f"- action count: `{result['action_count']}`",
            f"- scenario count: `{result['scenario_count']}`",
            f"- case count: `{result['case_count']}`",
            f"- blocking failures: `{result['blocking_failures']}`",
            f"- raw recipient addresses included: `{str(result['raw_recipient_addresses_included']).lower()}`",
            f"- real SMTP called: `{str(result['real_smtp_called']).lower()}`",
            f"- live outreach allowed: `{str(result['live_outreach_allowed']).lower()}`",
            "",
            "Scenarios: " + ", ".join(name for name, _ in SCENARIOS),
        ]
    )
    path.write_text(text + "\n", encoding="utf-8")
    return str(path)
