from __future__ import annotations

from dataclasses import dataclass
from email import message_from_bytes
from email.message import Message
import imaplib
import os
import ssl
from typing import Any

import httpx


@dataclass
class StudioMailPollResult:
    enabled: bool
    scanned: int = 0
    submitted: int = 0
    stored: int = 0
    owner_commands: int = 0
    marked_seen: int = 0
    error: str = ""


def _tls_context() -> ssl.SSLContext:
    if os.environ.get("MAIL_TLS_VERIFY", "true").lower() == "true":
        return ssl.create_default_context()
    return ssl._create_unverified_context()


def _extract_text(msg: Message) -> str:
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                payload = part.get_payload(decode=True) or b""
                return payload.decode(part.get_content_charset() or "utf-8", errors="replace")
        for part in msg.walk():
            if part.get_content_type() == "text/html":
                payload = part.get_payload(decode=True) or b""
                return payload.decode(part.get_content_charset() or "utf-8", errors="replace")
        return ""
    payload = msg.get_payload(decode=True) or b""
    return payload.decode(msg.get_content_charset() or "utf-8", errors="replace")


def _read_password(username: str) -> str:
    password = os.environ.get("STUDIO_MAIL_PASSWORD", "")
    if password:
        return password
    path = os.environ.get("STUDIO_MAILBOX_CREDS_FILE", "/run/secrets/voiddo_mailbox_creds")
    try:
        with open(path, "r", encoding="utf-8") as handle:
            for line in handle:
                stripped = line.strip()
                if not stripped or stripped.startswith("#"):
                    continue
                parts = stripped.split(None, 1)
                if len(parts) == 2 and parts[0].strip().lower() == username.lower():
                    return parts[1].strip()
    except FileNotFoundError:
        return ""
    return ""


def _message_payload(mailbox: str, uid: str, raw: bytes) -> dict[str, Any]:
    msg = message_from_bytes(raw)
    message_id = str(msg.get("Message-ID") or msg.get("Message-Id") or uid)
    return {
        "mailbox": mailbox,
        "uid": uid,
        "message_id": message_id,
        "sender": str(msg.get("From", "")),
        "reply_to": str(msg.get("Reply-To", "")),
        "to": str(msg.get("To", "")),
        "delivered_to": str(msg.get("Delivered-To", "")),
        "x_original_to": str(msg.get("X-Original-To", "")),
        "subject": str(msg.get("Subject", "")),
        "body": _extract_text(msg)[:8000],
        "authentication_results": str(msg.get("Authentication-Results", "")),
    }


def _submit_messages(messages: list[dict[str, Any]]) -> dict[str, Any]:
    if not messages:
        return {"stored_count": 0, "owner_command_count": 0}
    api_base = os.environ.get("API_INTERNAL_BASE_URL", "http://api:8080").rstrip("/")
    token = os.environ.get("ADMIN_AUTH_TOKEN", "")
    if not token:
        raise RuntimeError("admin_token_missing")
    with httpx.Client(timeout=30.0) as client:
        response = client.post(
            f"{api_base}/admin/studio-mail/ingest",
            headers={"X-Admin-Token": token},
            json={"messages": messages, "dry_run": False},
        )
        response.raise_for_status()
        return response.json().get("ingest", {})


def poll_studio_mailbox(limit: int = 20) -> dict[str, Any]:
    if os.environ.get("STUDIO_MAIL_MONITOR_ENABLED", "false").lower() != "true":
        return StudioMailPollResult(enabled=False).__dict__
    username = os.environ.get("STUDIO_MAIL_USERNAME", "").strip()
    password = _read_password(username)
    if not username or not password:
        return StudioMailPollResult(enabled=True, error="studio_mail_credentials_missing").__dict__

    host = os.environ.get("STUDIO_MAIL_IMAP_HOST", os.environ.get("IMAP_HOST", "mail.voiddo.com"))
    port = int(os.environ.get("STUDIO_MAIL_IMAP_PORT", os.environ.get("IMAP_PORT", "993")) or "993")
    safe_limit = max(1, min(int(limit or 20), 50))
    payloads: list[dict[str, Any]] = []
    uids: list[bytes] = []

    with imaplib.IMAP4_SSL(host, port, ssl_context=_tls_context(), timeout=30) as imap:
        imap.login(username, password)
        imap.select("INBOX")
        status, data = imap.uid("search", None, "UNSEEN")
        if status != "OK":
            imap.logout()
            return StudioMailPollResult(enabled=True, error="imap_search_failed").__dict__
        for uid_b in (data[0].split() or [])[:safe_limit]:
            status, fetched = imap.uid("fetch", uid_b, "(BODY.PEEK[])")
            if status != "OK" or not fetched or not isinstance(fetched[0], tuple):
                continue
            uid = uid_b.decode("ascii", errors="replace")
            payloads.append(_message_payload(username, uid, fetched[0][1]))
            uids.append(uid_b)
        ingest = _submit_messages(payloads)
        for uid_b in uids:
            imap.uid("store", uid_b, "+FLAGS.SILENT", "\\Seen")
        imap.logout()

    return StudioMailPollResult(
        enabled=True,
        scanned=len(payloads),
        submitted=len(payloads),
        stored=int(ingest.get("stored_count", 0) or 0),
        owner_commands=int(ingest.get("owner_command_count", 0) or 0),
        marked_seen=len(uids),
    ).__dict__
