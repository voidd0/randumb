from __future__ import annotations

from dataclasses import dataclass
from email import message_from_bytes
from email.header import decode_header, make_header
from email.message import EmailMessage
from email.utils import parseaddr
import httpx
import imaplib
import os
import re
import smtplib
import ssl

from .inbox_store import persist_message


SAFE_AUTO_REPLY = {"ask_price", "ask_details", "wrong_person", "out_of_office", "unsubscribe"}
UNSAFE = {"angry", "legal_threat", "security_accusation", "custom_technical_request", "paid", "wants_call"}


@dataclass
class InboxMessage:
    mailbox: str
    uid: str
    sender: str
    reply_to: str
    message_id: str
    subject: str
    body: str
    authentication_results: str
    classification: str
    human_review_required: bool
    auto_reply_allowed: bool


def tls_context():
    if os.environ.get("MAIL_TLS_VERIFY", "false").lower() == "true":
        return ssl.create_default_context()
    return ssl._create_unverified_context()


def _has(text: str, terms: list[str]) -> bool:
    for term in terms:
        pattern = r"(?<![a-z0-9])" + re.escape(term) + r"(?![a-z0-9])"
        if re.search(pattern, text):
            return True
    return False


def classify(subject: str, body: str) -> tuple[str, bool, bool]:
    text = f"{subject}\n{body}".lower()
    if _has(text, ["unsubscribe", "remove me", "stop emailing"]):
        label = "unsubscribe"
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
    return label, label in UNSAFE or label == "human_review_required", label in SAFE_AUTO_REPLY


def owner_emails() -> set[str]:
    raw = ",".join([os.environ.get("OWNER_COMMAND_EMAIL", ""), os.environ.get("STUDIO_OWNER_COMMAND_EMAILS", "")])
    return {item.strip().lower() for item in raw.split(",") if item.strip()}


def is_owner_sender(sender: str, reply_to: str = "") -> bool:
    owners = owner_emails()
    sender_email = parseaddr(sender or "")[1].lower()
    reply_email = parseaddr(reply_to or "")[1].lower() if reply_to else sender_email
    return bool(owners) and sender_email in owners and reply_email in owners | {sender_email}


def submit_owner_command(item: InboxMessage) -> dict:
    token = os.environ.get("ADMIN_AUTH_TOKEN", "")
    if not token:
        raise RuntimeError("admin_auth_token_missing")
    api_base = os.environ.get("API_INTERNAL_BASE_URL", "http://api:8080").rstrip("/")
    payload = {
        "mailbox": item.mailbox,
        "uid": item.uid,
        "message_id": item.message_id or item.uid,
        "sender": item.sender,
        "reply_to": item.reply_to,
        "subject": item.subject,
        "body": item.body,
        "authentication_results": item.authentication_results,
    }
    with httpx.Client(timeout=20.0) as client:
        response = client.post(f"{api_base}/owner/commands", headers={"X-Admin-Token": token}, json=payload)
        response.raise_for_status()
        return response.json().get("command", {})


def extract_text(msg) -> str:
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                payload = part.get_payload(decode=True) or b""
                return payload.decode(part.get_content_charset() or "utf-8", errors="replace")
        return ""
    payload = msg.get_payload(decode=True) or b""
    return payload.decode(msg.get_content_charset() or "utf-8", errors="replace")


def decode_header_value(value: str) -> str:
    try:
        return str(make_header(decode_header(value or "")))
    except Exception:
        return value or ""


def read_unseen(mailbox: str, username: str, password: str, limit: int = 20) -> list[InboxMessage]:
    host = os.environ.get("IMAP_HOST", "mail.voiddorescue.com")
    port = int(os.environ.get("IMAP_PORT", "993"))
    messages: list[InboxMessage] = []
    with imaplib.IMAP4_SSL(host, port, ssl_context=tls_context(), timeout=30) as imap:
        imap.login(username, password)
        imap.select("INBOX")
        status, data = imap.uid("search", None, "UNSEEN")
        if status != "OK":
            return messages
        for uid_b in (data[0].split() or [])[:limit]:
            uid = uid_b.decode("ascii", errors="replace")
            status, fetched = imap.uid("fetch", uid, "(RFC822)")
            if status != "OK" or not fetched:
                continue
            raw = fetched[0][1]
            msg = message_from_bytes(raw)
            subject = decode_header_value(str(msg.get("Subject", "")))
            sender = parseaddr(decode_header_value(str(msg.get("From", ""))))[1]
            reply_to = parseaddr(decode_header_value(str(msg.get("Reply-To", ""))))[1]
            message_id = str(msg.get("Message-ID", "")) or uid
            authentication_results = str(msg.get("Authentication-Results", ""))
            body = extract_text(msg)
            if is_owner_sender(sender, reply_to):
                label, human, auto = "owner_command", False, False
            else:
                label, human, auto = classify(subject, body)
            messages.append(InboxMessage(mailbox, uid, sender, reply_to, message_id, subject, body[:4000], authentication_results, label, human, auto))
        imap.logout()
    return messages


def render_auto_reply(classification: str) -> tuple[str, str]:
    if classification == "unsubscribe":
        return "Re: unsubscribe confirmed", "You are unsubscribed from Vøiddo Rescue outreach. No further action is needed.\n\nVøiddo Rescue"
    if classification == "ask_price":
        return "Re: Vøiddo Rescue pricing", "Pricing starts at $49 for a one-time audit, $99 for contact form repair, and $19/month for monitoring.\n\nVøiddo Rescue"
    if classification == "ask_details":
        return "Re: website check details", "The audit page shows the public browser-session evidence, screenshots, and recommended next steps. Reply with the site URL if you want us to re-check after a change.\n\nVøiddo Rescue"
    if classification == "wrong_person":
        return "Re: thanks", "Thanks for letting us know. We will stop this thread unless someone else from the business contacts us.\n\nVøiddo Rescue"
    return "Re: thanks", "Thanks. We will keep the thread noted and avoid duplicate follow-up.\n\nVøiddo Rescue"


def send_auto_reply(to_addr: str, classification: str) -> str:
    if os.environ.get("AUTO_REPLIES_PAUSED", "true").lower() == "true":
        return "paused"
    subject, body = render_auto_reply(classification)
    msg = EmailMessage()
    msg["From"] = os.environ.get("SMTP_FROM_DEFAULT", "audit@voiddorescue.com")
    msg["To"] = to_addr
    msg["Subject"] = subject
    msg.set_content(body)
    host = os.environ.get("SMTP_HOST", "mail.voiddorescue.com")
    port = int(os.environ.get("SMTP_PORT", "587"))
    with smtplib.SMTP(host, port, timeout=30) as smtp:
        smtp.ehlo()
        smtp.starttls(context=tls_context())
        smtp.ehlo()
        smtp.login(os.environ.get("SMTP_USERNAME", ""), os.environ.get("SMTP_PASSWORD", ""))
        smtp.send_message(msg)
    return "sent"


def poll_all() -> list[InboxMessage]:
    configs = [
        ("audit", os.environ.get("IMAP_USERNAME_AUDIT", ""), os.environ.get("IMAP_PASSWORD_AUDIT", "")),
        ("fix", os.environ.get("IMAP_USERNAME_FIX", ""), os.environ.get("IMAP_PASSWORD_FIX", "")),
        ("support", os.environ.get("IMAP_USERNAME_SUPPORT", ""), os.environ.get("IMAP_PASSWORD_SUPPORT", "")),
    ]
    all_messages: list[InboxMessage] = []
    for mailbox, username, password in configs:
        if not username or not password:
            continue
        all_messages.extend(read_unseen(mailbox, username, password))
    for item in all_messages:
        if item.classification == "owner_command":
            try:
                submit_owner_command(item)
            except Exception:
                item.classification = "owner_command_api_failed"
                item.human_review_required = False
                item.auto_reply_allowed = False
                persist_message(item)
            continue
        persist_message(item)
        if item.auto_reply_allowed and not item.human_review_required:
            send_auto_reply(item.sender, item.classification)
        # Unsafe/human-review messages are intentionally not auto-replied.
    return all_messages
