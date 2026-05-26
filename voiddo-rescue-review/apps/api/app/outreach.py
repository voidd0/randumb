from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from .email_quality import beautiful_signature, check_email_quality


TEMPLATES = {
    "en": {
        "subject": "Possible issue on {business_name} website",
        "body": """Hi {name_or_team},

I checked {domain} today and found a possible issue that may affect customer enquiries:

{main_issue_short}

Screenshots and test details:
{audit_url}

If this website brings you leads, this may be worth fixing.
Vøiddo Rescue can monitor this automatically and handle small WordPress/site fixes.

One-time fix starts at {one_time_price}.
Monitoring starts at {monthly_price}/month.

{signature}

Public non-invasive website check.
Unsubscribe: {unsubscribe_url}
""",
    },
    "he": {
        "subject": "בעיה אפשרית באתר של {business_name}",
        "body": """שלום {name_or_team},

בדקתי היום את {domain} ומצאתי בעיה אפשרית שעלולה לפגוע בפניות מלקוחות:

{main_issue_short}

צילומי מסך ופרטי בדיקה:
{audit_url}

אם האתר מביא לכם לידים, שווה לבדוק את זה.
Vøiddo Rescue יכולה לנטר את זה אוטומטית ולטפל בתיקוני WordPress/אתר קטנים.

תיקון חד-פעמי מתחיל ב-{one_time_price}.
ניטור מתחיל ב-{monthly_price} לחודש.

{signature}

בדיקת אתר ציבורית ולא פולשנית.
הסרה: {unsubscribe_url}
""",
    },
    "et": {
        "subject": "Võimalik probleem {business_name} veebilehel",
        "body": """Tere {name_or_team},

Kontrollisin täna domeeni {domain} ja leidsin võimaliku probleemi, mis võib mõjutada kliendipäringuid:

{main_issue_short}

Ekraanipildid ja testi detailid:
{audit_url}

Kui see veebileht toob teile päringuid, tasub seda parandada.
Vøiddo Rescue saab seda automaatselt jälgida ja teha väiksemaid WordPressi/veebilehe parandusi.

Ühekordne parandus algab hinnast {one_time_price}.
Jälgimine algab hinnast {monthly_price}/kuus.

{signature}

Avalik mitteinvasiivne veebilehe kontroll.
Loobu kirjadest: {unsubscribe_url}
""",
    },
}


@dataclass(frozen=True)
class RateLimitDecision:
    allowed: bool
    reason: str


def render_template(language: str, context: dict[str, str]) -> dict[str, str]:
    template = TEMPLATES.get(language, TEMPLATES["en"])
    safe_context = {
        "business_name": context.get("business_name", "your business"),
        "name_or_team": context.get("contact_name") or "team",
        "domain": context.get("domain", ""),
        "main_issue_short": context.get("main_issue_short", "A public enquiry path may need attention."),
        "audit_url": context.get("audit_url", ""),
        "unsubscribe_url": context.get("unsubscribe_url", ""),
        "one_time_price": context.get("one_time_price", "$49"),
        "monthly_price": context.get("monthly_price", "$19"),
        "signature": beautiful_signature(language),
    }
    rendered = {
        "subject": template["subject"].format(**safe_context),
        "body": template["body"].format(**safe_context),
    }
    quality = check_email_quality(rendered["subject"], rendered["body"])
    rendered["qa_passed"] = str(quality.passed)
    rendered["qa_score"] = str(quality.score)
    rendered["qa_issues"] = ",".join(quality.issues)
    return rendered


def outreach_allowed(settings, suppressed: bool, sent_today: int, sent_this_domain_hour: int) -> RateLimitDecision:
    if settings.global_kill_switch:
        return RateLimitDecision(False, "global_kill_switch")
    if settings.outreach_paused:
        return RateLimitDecision(False, "outreach_paused")
    if not settings.first_live_send_flag and not settings.outreach_dry_run:
        return RateLimitDecision(False, "first_live_send_flag_missing")
    if suppressed:
        return RateLimitDecision(False, "suppressed")
    if sent_today >= settings.daily_send_limit:
        return RateLimitDecision(False, "daily_send_limit")
    if sent_this_domain_hour >= settings.hourly_domain_send_limit:
        return RateLimitDecision(False, "domain_hourly_limit")
    return RateLimitDecision(True, "allowed")


def now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
