#!/usr/bin/env python3
from __future__ import annotations

import argparse
import imaplib
import json
import os
import ssl
from email import message_from_bytes
from email.utils import parseaddr
from pathlib import Path
from urllib.request import Request, urlopen


DEFAULT_CREDS = Path("/root/.voiddo-mailbox-creds")
DEFAULT_ENV = Path("/opt/voiddo-rescue/.env")


def load_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def load_mailbox_password(path: Path, address: str) -> str:
    if not path.exists():
        raise SystemExit("mailbox credential file missing")
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) >= 2 and parts[0].lower() == address.lower():
            return parts[1]
    raise SystemExit("mailbox credential entry missing")


def text_body(msg) -> str:
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                payload = part.get_payload(decode=True) or b""
                return payload.decode(part.get_content_charset() or "utf-8", errors="replace")
        return ""
    payload = msg.get_payload(decode=True) or b""
    return payload.decode(msg.get_content_charset() or "utf-8", errors="replace")


def fetch_unseen(host: str, port: int, username: str, password: str, limit: int) -> list[dict]:
    messages: list[dict] = []
    ctx = ssl.create_default_context()
    with imaplib.IMAP4_SSL(host, port, ssl_context=ctx, timeout=30) as imap:
        imap.login(username, password)
        imap.select("INBOX")
        status, data = imap.uid("search", None, "UNSEEN")
        if status != "OK":
            return messages
        for uid_b in (data[0].split() or [])[:limit]:
            uid = uid_b.decode("ascii", errors="replace")
            status, fetched = imap.uid("fetch", uid, "(BODY.PEEK[])")
            if status != "OK" or not fetched or not isinstance(fetched[0], tuple):
                continue
            msg = message_from_bytes(fetched[0][1])
            sender = parseaddr(str(msg.get("From", "")))[1] or str(msg.get("From", ""))
            messages.append(
                {
                    "mailbox": "studio:voiddo",
                    "uid": uid,
                    "message_id": str(msg.get("Message-ID", uid)),
                    "sender": sender,
                    "reply_to": str(msg.get("Reply-To", "")),
                    "to": str(msg.get("To", "")),
                    "delivered_to": str(msg.get("Delivered-To", "")),
                    "x_original_to": str(msg.get("X-Original-To", "")),
                    "subject": str(msg.get("Subject", "")),
                    "authentication_results": str(msg.get("Authentication-Results", "")),
                    "body": text_body(msg)[:8000],
                }
            )
        imap.logout()
    return messages


def post_ingest(api_base: str, token: str, messages: list[dict], dry_run: bool) -> dict:
    payload = json.dumps({"messages": messages, "dry_run": dry_run}).encode("utf-8")
    request = Request(
        f"{api_base.rstrip('/')}/admin/studio-mail/ingest",
        data=payload,
        headers={"Content-Type": "application/json", "X-Admin-Token": token},
        method="POST",
    )
    with urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser(description="Poll em@voiddo.com and ingest safe studio-mail metadata into Vøiddo Rescue.")
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--api-base", default="http://127.0.0.1:18082")
    parser.add_argument("--imap-host", default="127.0.0.1")
    parser.add_argument("--imap-port", type=int, default=993)
    parser.add_argument("--username", default="em@voiddo.com")
    parser.add_argument("--creds", default=str(DEFAULT_CREDS))
    parser.add_argument("--env", default=str(DEFAULT_ENV))
    args = parser.parse_args()

    env = load_env(Path(args.env))
    token = os.environ.get("ADMIN_AUTH_TOKEN") or env.get("ADMIN_AUTH_TOKEN")
    if not token:
        raise SystemExit("ADMIN_AUTH_TOKEN missing")
    password = os.environ.get("STUDIO_MAIL_PASSWORD") or load_mailbox_password(Path(args.creds), args.username)
    messages = fetch_unseen(args.imap_host, args.imap_port, args.username, password, max(1, min(args.limit, 50)))
    result = post_ingest(args.api_base, token, messages, args.dry_run)
    ingest = result.get("ingest", {})
    print(
        json.dumps(
            {
                "ok": bool(result.get("ok")),
                "dry_run": args.dry_run,
                "scanned_count": ingest.get("scanned_count", 0),
                "stored_count": ingest.get("stored_count", 0),
                "owner_command_count": ingest.get("owner_command_count", 0),
                "high_priority_count": ingest.get("high_priority_count", 0),
                "send_mail": ingest.get("send_mail", False),
                "live_outreach_allowed": ingest.get("live_outreach_allowed", False),
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
