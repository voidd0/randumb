from __future__ import annotations


UNSAFE = {
    "angry",
    "legal_threat",
    "security_accusation",
    "custom_technical_request",
    "wants_call",
    "paid",
}


def classify_reply(subject: str, body: str) -> dict[str, object]:
    text = f"{subject}\n{body}".lower()
    if any(word in text for word in ["unsubscribe", "remove me", "stop emailing"]):
        label = "unsubscribe"
    elif any(word in text for word in ["delivery status notification", "undelivered", "mail delivery failed"]):
        label = "bounce"
    elif any(word in text for word in ["lawyer", "legal", "sue", "gdpr complaint"]):
        label = "legal_threat"
    elif any(word in text for word in ["hack", "security scan", "unauthorized", "attack"]):
        label = "security_accusation"
    elif any(word in text for word in ["price", "cost", "how much"]):
        label = "ask_price"
    elif any(word in text for word in ["details", "what did you find", "screenshot"]):
        label = "ask_details"
    elif any(word in text for word in ["not interested", "no thanks"]):
        label = "not_interested"
    elif any(word in text for word in ["call me", "book a call", "meeting"]):
        label = "wants_call"
    elif any(word in text for word in ["out of office", "automatic reply"]):
        label = "out_of_office"
    elif any(word in text for word in ["paid", "receipt", "invoice paid"]):
        label = "paid"
    elif any(word in text for word in ["yes", "interested", "fix it"]):
        label = "interested"
    else:
        label = "human_review_required"
    return {
        "classification": label,
        "human_review_required": label in UNSAFE or label == "human_review_required",
        "auto_reply_allowed": label in {"ask_price", "ask_details", "wrong_person", "out_of_office", "unsubscribe"},
    }
