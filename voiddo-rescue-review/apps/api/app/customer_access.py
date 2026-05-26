from __future__ import annotations

import hashlib
import secrets
from typing import Any

from .customer_journey import customer_journey_snapshot
from .db import execute, fetch_one


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def ensure_customer_access_token(customer_id: str) -> dict[str, Any]:
    existing = fetch_one("SELECT * FROM customer_access_tokens WHERE customer_id = %s AND status = 'active' ORDER BY created_at DESC LIMIT 1", (customer_id,))
    if existing:
        return {"customer_id": customer_id, "token": None, "token_created": False, "token_id": str(existing["id"])}
    token = secrets.token_urlsafe(32)
    row = execute(
        """
        INSERT INTO customer_access_tokens(customer_id, token_hash, status)
        VALUES (%s, %s, 'active')
        RETURNING *
        """,
        (customer_id, _hash_token(token)),
    )
    return {"customer_id": customer_id, "token": token, "token_created": True, "token_id": str(row["id"])}


def customer_dashboard_by_token(token: str) -> dict[str, Any]:
    token_hash = _hash_token(token)
    row = fetch_one(
        """
        SELECT c.id
        FROM customer_access_tokens t
        JOIN customers c ON c.id = t.customer_id
        WHERE t.token_hash = %s AND t.status = 'active'
        """,
        (token_hash,),
    )
    if not row:
        raise ValueError("customer_token_not_found")
    execute("UPDATE customer_access_tokens SET last_used_at = now() WHERE token_hash = %s", (token_hash,))
    journey = customer_journey_snapshot(customer_id=str(row["id"]))["result_json"]
    # The token endpoint exposes only that customer's data and does not include
    # administrative raw rows.
    return {
        "customer": journey["customer"],
        "purchased": journey["purchased"],
        "fix_requests": journey["fix_requests"],
        "onboarding": journey["onboarding"],
        "monitoring": journey["monitoring"],
        "dashboard_ready": True,
    }
