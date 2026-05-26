from __future__ import annotations

import re
from typing import Any


TEMPLATES: dict[str, dict[str, dict[str, str]]] = {
    "first_audit_notice": {
        "en": {
            "subject": "Possible issue on {{business_name}} website",
            "body": "Hi {{name_or_team}},\n\nI checked {{domain}} from a public browser session and found a possible issue that may affect customer enquiries:\n\n{{main_issue_short}}\n\nScreenshots and test details:\n{{audit_url}}\n\nIf this website brings you leads, this may be worth fixing. Vøiddo Rescue can monitor this automatically and handle small WordPress/site fixes.\n\nOne-time fix starts at {{one_time_price}}. Monitoring starts at {{monthly_price}}/month.\n\nBest,\nVøiddo Rescue\n\nPublic non-invasive website check.\nUnsubscribe: {{unsubscribe_url}}",
        },
        "he": {
            "subject": "בעיה אפשרית באתר של {{business_name}}",
            "body": "שלום {{name_or_team}},\n\nבדקתי את {{domain}} דרך דפדפן ציבורי ומצאתי בעיה אפשרית שעלולה לפגוע בפניות מלקוחות:\n\n{{main_issue_short}}\n\nצילומי מסך ופרטי בדיקה:\n{{audit_url}}\n\nאם האתר מביא לכם לידים, כדאי לבדוק את זה. Vøiddo Rescue יכול לנטר את האתר ולטפל בתיקונים קטנים.\n\nתיקון חד-פעמי החל מ-{{one_time_price}}. ניטור החל מ-{{monthly_price}} לחודש.\n\nבברכה,\nVøiddo Rescue\n\nבדיקת אתר ציבורית ולא פולשנית.\nהסרה: {{unsubscribe_url}}",
        },
        "et": {
            "subject": "Võimalik probleem {{business_name}} veebilehel",
            "body": "Tere {{name_or_team}},\n\nKontrollisin {{domain}} avaliku brauseriseansiga ja leidsin võimaliku probleemi, mis võib mõjutada kliendipäringuid:\n\n{{main_issue_short}}\n\nEkraanipildid ja testi detailid:\n{{audit_url}}\n\nKui veebileht toob teile päringuid, tasub see üle vaadata. Vøiddo Rescue saab saiti jälgida ja väiksemaid parandusi hallata.\n\nÜhekordne parandus alates {{one_time_price}}. Jälgimine alates {{monthly_price}} kuus.\n\nParimat,\nVøiddo Rescue\n\nAvalik mitteinvasiivne veebilehe kontroll.\nLoobu: {{unsubscribe_url}}",
        },
    },
    "followup_1_soft": {
        "en": {"subject": "Re: possible website enquiry issue", "body": "Hi {{name_or_team}},\n\nSmall follow-up on the public check for {{domain}}. The audit page is here:\n{{audit_url}}\n\nNo pressure. If the issue is already handled, you can ignore this.\n\nBest,\nVøiddo Rescue\nUnsubscribe: {{unsubscribe_url}}"},
        "he": {"subject": "מעקב קצר לגבי האתר", "body": "שלום {{name_or_team}},\n\nמעקב קצר לגבי הבדיקה הציבורית של {{domain}}:\n{{audit_url}}\n\nאם זה כבר טופל, אפשר להתעלם.\n\nVøiddo Rescue\nהסרה: {{unsubscribe_url}}"},
        "et": {"subject": "Lühike järelkiri veebilehe kontrolli kohta", "body": "Tere {{name_or_team}},\n\nLühike järelkiri {{domain}} avaliku kontrolli kohta:\n{{audit_url}}\n\nKui see on juba lahendatud, võite kirja ignoreerida.\n\nVøiddo Rescue\nLoobu: {{unsubscribe_url}}"},
    },
    "followup_2_value": {
        "en": {"subject": "Keeping {{domain}} monitored", "body": "Hi {{name_or_team}},\n\nThe practical value is simple: get notified when contact paths, mobile CTAs, or public page availability break.\n\nAudit: {{audit_url}}\n\nMonitoring starts at {{monthly_price}}/month.\n\nBest,\nVøiddo Rescue\nUnsubscribe: {{unsubscribe_url}}"},
        "he": {"subject": "ניטור שוטף ל-{{domain}}", "body": "שלום {{name_or_team}},\n\nהערך פשוט: לקבל התראה כשנתיבי יצירת קשר, CTA במובייל או זמינות ציבורית נשברים.\n\nבדיקה: {{audit_url}}\n\nניטור החל מ-{{monthly_price}} לחודש.\n\nVøiddo Rescue\nהסרה: {{unsubscribe_url}}"},
        "et": {"subject": "{{domain}} pidev jälgimine", "body": "Tere {{name_or_team}},\n\nVäärtus on lihtne: märguanne, kui kontaktitee, mobiili CTA või avalik saadavus katkeb.\n\nAudit: {{audit_url}}\n\nJälgimine alates {{monthly_price}} kuus.\n\nVøiddo Rescue\nLoobu: {{unsubscribe_url}}"},
    },
    "reply_ask_price": {"en": {"subject": "Vøiddo Rescue pricing", "body": "Pricing starts at {{one_time_price}} for a one-time fix and {{monthly_price}}/month for monitoring.\n\nAudit: {{audit_url}}\n\nVøiddo Rescue"}},
    "reply_ask_details": {"en": {"subject": "Vøiddo Rescue details", "body": "The check is public and non-invasive. We verify visible website issues such as contact paths, mobile layout, availability, and public CTAs.\n\nAudit: {{audit_url}}\n\nVøiddo Rescue"}},
    "reply_wrong_person": {"en": {"subject": "Thanks", "body": "Thanks for letting us know. We will stop this thread unless you forward it to the right website owner.\n\nVøiddo Rescue"}},
    "unsubscribe_confirmed": {"en": {"subject": "Unsubscribed", "body": "You have been unsubscribed from Vøiddo Rescue outreach. No action is required."}},
    "payment_onboarding": {"en": {"subject": "Vøiddo Rescue onboarding", "body": "Thanks for your purchase. Your dashboard is ready here:\n{{customer_url}}\n\nNext step: review the current audit and connect the read-only WordPress agent if needed.\n\nVøiddo Rescue"}},
    "fix_request_created": {"en": {"subject": "Fix request created", "body": "Your fix request has been created.\n\nRequest: {{fix_request_title}}\nStatus: {{status}}\n\nVøiddo Rescue"}},
    "warmup_neutral": {"en": {"subject": "Vøiddo Rescue warmup check", "body": "This is a requested Vøiddo Rescue mail warmup check. No action is required."}},
    "deliverability_diagnostic": {"en": {"subject": "Vøiddo Rescue mail diagnostic", "body": "This is a requested mail delivery diagnostic for Vøiddo Rescue. No action is required."}},
}


DEFAULT_SAMPLE = {
    "business_name": "Example Studio",
    "name_or_team": "team",
    "domain": "example.com",
    "main_issue_short": "The public homepage may not show a clear enquiry path on mobile.",
    "audit_url": "https://audit.rescue.voiddo.com/r/demo",
    "unsubscribe_url": "https://go.rescue.voiddo.com/unsubscribe/demo",
    "one_time_price": "$99",
    "monthly_price": "$19",
    "customer_url": "https://app.rescue.voiddo.com/customer",
    "fix_request_title": "Contact form repair",
    "status": "new",
}


def render_email_template(template_key: str, language: str = "en", data: dict[str, Any] | None = None) -> dict[str, Any]:
    templates = TEMPLATES.get(template_key)
    if not templates:
        raise ValueError("unknown_template")
    template = templates.get(language) or templates.get("en")
    if not template:
        raise ValueError("language_not_available")
    values = {**DEFAULT_SAMPLE, **(data or {})}

    def sub(text: str) -> str:
        for key, value in values.items():
            text = text.replace("{{" + key + "}}", str(value))
        return text

    subject = sub(template["subject"])
    body = sub(template["body"])
    return {"template_key": template_key, "language": language, "subject": subject, "text": body, "html": ""}


def qa_email_template(rendered: dict[str, Any]) -> dict[str, Any]:
    subject = rendered["subject"]
    body = rendered["text"]
    issues: list[str] = []
    if len(subject) > 78:
        issues.append("subject_too_long")
    if re.search(r"{{[^}]+}}", subject + body):
        issues.append("unresolved_template_var")
    risky = ["hacked", "vulnerability", "urgent", "security breach", "we scanned your security"]
    lower = body.lower()
    for word in risky:
        if word in lower:
            issues.append(f"risky_phrase:{word}")
    if rendered["template_key"].startswith("first_") or rendered["template_key"].startswith("followup_"):
        if "unsubscribe" not in lower and "הסרה" not in body and "loobu" not in lower:
            issues.append("missing_unsubscribe")
        if "http" not in body:
            issues.append("missing_proof_link")
    if not body.strip():
        issues.append("empty_body")
    return {"passed": not issues, "issues": issues, "score": max(0, 100 - len(issues) * 20)}


def render_all_samples() -> list[dict[str, Any]]:
    outputs = []
    for key, languages in TEMPLATES.items():
        for language in languages:
            rendered = render_email_template(key, language)
            outputs.append({**rendered, "qa": qa_email_template(rendered)})
    return outputs
