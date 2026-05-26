from __future__ import annotations

import base64
import hashlib
import hmac


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
