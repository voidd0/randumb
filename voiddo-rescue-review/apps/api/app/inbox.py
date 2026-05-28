from __future__ import annotations

import re


UNSAFE = {
    "angry",
    "legal_threat",
    "security_accusation",
    "custom_technical_request",
    "wants_call",
    "paid",
}


def _has(text: str, terms: list[str]) -> bool:
    for term in terms:
        pattern = r"(?<![a-z0-9])" + re.escape(term) + r"(?![a-z0-9])"
        if re.search(pattern, text):
            return True
    return False


def classify_reply(subject: str, body: str) -> dict[str, object]:
    text = f"{subject}\n{body}".lower()
    if _has(text, ["unsubscribe", "remove me", "stop emailing"]):
        label = "unsubscribe"
    elif _has(text, ["wrong person", "not the right person", "not my website", "contact someone else"]):
        label = "wrong_person"
    elif _has(text, ["angry", "harassment", "stop this now", "this is spam", "report you"]):
        label = "angry"
    elif _has(text, ["found it in spam", "in spam", "spam folder", "starred and answered", "starred and sent", "all fine"]):
        label = "auto_reply"
    elif _has(text, ["delivery status notification", "undelivered", "mail delivery failed"]):
        label = "bounce"
    elif _has(text, ["lawyer", "legal", "sue", "gdpr complaint"]):
        label = "legal_threat"
    elif _has(text, ["hack", "security scan", "unauthorized", "attack"]):
        label = "security_accusation"
    elif _has(text, ["price", "cost", "how much"]):
        label = "ask_price"
    elif _has(text, ["details", "what did you find", "screenshot"]):
        label = "ask_details"
    elif _has(text, ["not interested", "no thanks"]):
        label = "not_interested"
    elif _has(text, ["call me", "book a call", "meeting"]):
        label = "wants_call"
    elif _has(text, ["out of office", "automatic reply"]):
        label = "out_of_office"
    elif _has(text, ["paid", "receipt", "invoice paid"]):
        label = "paid"
    elif _has(text, ["yes", "interested", "fix it"]):
        label = "interested"
    else:
        label = "human_review_required"
    return {
        "classification": label,
        "human_review_required": label in UNSAFE or label == "human_review_required",
        "auto_reply_allowed": label in {"ask_price", "ask_details", "wrong_person", "out_of_office", "unsubscribe"},
    }
