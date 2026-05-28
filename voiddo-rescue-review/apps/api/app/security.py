from __future__ import annotations

import base64
import hashlib
import hmac
import uuid


def verify_paddle_signature(raw_body: bytes, signature_header: str, webhook_secret: str) -> bool:
    """Verify Paddle-style ts/h1 signature without logging secrets or payload values."""
    if not webhook_secret or not signature_header:
        return False
    parts: dict[str, str] = {}
    for item in signature_header.split(";"):
        if "=" in item:
            key, value = item.split("=", 1)
            parts[key.strip()] = value.strip()
    timestamp = parts.get("ts")
    signature = parts.get("h1")
    if not timestamp or not signature:
        return False
    signed_payload = timestamp.encode("utf-8") + b":" + raw_body
    digest = hmac.new(webhook_secret.encode("utf-8"), signed_payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(digest, signature)


def token_for(value: str, secret: str) -> str:
    digest = hmac.new(secret.encode("utf-8"), value.encode("utf-8"), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest[:18]).decode("ascii").rstrip("=")


def unsubscribe_token_for_lead(lead_id: str, secret: str) -> str:
    lead_id = (lead_id or "").strip()
    return f"u_{lead_id}.{token_for(lead_id, secret)}"


def lead_id_from_unsubscribe_token(token: str, secret: str) -> str:
    token = (token or "").strip()
    if not token.startswith("u_"):
        raise ValueError("invalid_unsubscribe_token")
    body = token[2:]
    if "." in body:
        lead_id, signature = body.split(".", 1)
    else:
        lead_id, separator, signature = body[:36], body[36:37], body[37:]
        if separator != "_":
            raise ValueError("invalid_unsubscribe_token")
    if not lead_id or not signature:
        raise ValueError("invalid_unsubscribe_token")
    try:
        uuid.UUID(lead_id)
    except ValueError as exc:
        raise ValueError("invalid_unsubscribe_token") from exc
    expected = token_for(lead_id, secret)
    if not hmac.compare_digest(signature, expected):
        raise ValueError("invalid_unsubscribe_token")
    return lead_id
