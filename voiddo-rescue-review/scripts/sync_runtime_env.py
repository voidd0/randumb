#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import secrets


ROOT = Path("/opt/voiddo-rescue")
ENV_PATH = ROOT / ".env"
EXAMPLE_PATH = ROOT / ".env.example"
PADDLE_ENV = Path("/root/.voiddo-secrets/paddle-live.env")
MAILBOX_ENV = Path("/root/.voiddo-secrets/voiddorescue-mailboxes.env")
VOIDDO_MAILER_ENV = Path("/root/projects/voiddo-mailer/.env")
SCRB_ENV = Path("/root/scrb/backend/.env")


def read_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def write_env(path: Path, values: dict[str, str]) -> None:
    template_lines = EXAMPLE_PATH.read_text(encoding="utf-8").splitlines()
    output: list[str] = []
    used: set[str] = set()
    for line in template_lines:
        if "=" not in line or line.strip().startswith("#"):
            output.append(line)
            continue
        key = line.split("=", 1)[0]
        if key in values:
            output.append(f"{key}={values[key]}")
            used.add(key)
        else:
            output.append(line)
    extras = [(key, value) for key, value in sorted(values.items()) if key not in used]
    if extras:
        output.append("")
        output.append("# Synced optional API credentials; values are local-only and must not be committed.")
        for key, value in extras:
            output.append(f"{key}={value}")
    tmp = path.with_suffix(".tmp")
    tmp.write_text("\n".join(output) + "\n", encoding="utf-8")
    tmp.chmod(0o600)
    tmp.replace(path)
    path.chmod(0o600)


def main() -> int:
    current = read_env(ENV_PATH) or read_env(EXAMPLE_PATH)
    paddle = read_env(PADDLE_ENV)
    mailboxes = read_env(MAILBOX_ENV)
    mailer = read_env(VOIDDO_MAILER_ENV)
    scrb = read_env(SCRB_ENV)

    current["PADDLE_API_KEY"] = paddle.get("PADDLE_API_KEY") or paddle.get("PADDLE_SECRET_API_KEY") or current.get("PADDLE_API_KEY", "")
    current["PADDLE_ENVIRONMENT"] = paddle.get("PADDLE_ENVIRONMENT", current.get("PADDLE_ENVIRONMENT", "live"))
    if not current.get("PADDLE_WEBHOOK_SECRET"):
        current["PADDLE_WEBHOOK_SECRET"] = "vdr_" + secrets.token_urlsafe(32)

    current["SMTP_HOST"] = "mail.voiddo.com"
    current["SMTP_PORT"] = "587"
    current["SMTP_USERNAME"] = "audit@voiddorescue.com"
    current["SMTP_PASSWORD"] = mailboxes.get("MAILBOX_AUDIT_PASSWORD", current.get("SMTP_PASSWORD", ""))
    current["SMTP_FROM_DEFAULT"] = "audit@voiddorescue.com"
    current["IMAP_HOST"] = "mail.voiddo.com"
    current["IMAP_PORT"] = "993"
    current["IMAP_USERNAME_AUDIT"] = "audit@voiddorescue.com"
    current["IMAP_PASSWORD_AUDIT"] = mailboxes.get("MAILBOX_AUDIT_PASSWORD", current.get("IMAP_PASSWORD_AUDIT", ""))
    current["IMAP_USERNAME_FIX"] = "fix@voiddorescue.com"
    current["IMAP_PASSWORD_FIX"] = mailboxes.get("MAILBOX_FIX_PASSWORD", current.get("IMAP_PASSWORD_FIX", ""))
    current["IMAP_USERNAME_SUPPORT"] = "support@voiddorescue.com"
    current["IMAP_PASSWORD_SUPPORT"] = mailboxes.get("MAILBOX_SUPPORT_PASSWORD", current.get("IMAP_PASSWORD_SUPPORT", ""))
    current["MAIL_TLS_VERIFY"] = "true"

    # Optional money-pipeline APIs. Do not enable paid calls by default; code must opt in per gate.
    for key in ["GEMINI_API_KEY", "HUNTER_API_KEY", "APOLLO_API_KEY", "PSI_KEY", "RESEND_API_KEY", "SENTRY_DSN"]:
        value = mailer.get(key) or scrb.get(key)
        if value and not current.get(key):
            current[key] = value

    current["OUTREACH_DRY_RUN"] = "true"
    current["OUTREACH_PAUSED"] = "true"
    current["AUTO_REPLIES_PAUSED"] = "true"
    current["FIRST_LIVE_SEND_FLAG"] = "false"
    current["EMAIL_QA_REQUIRED"] = "true"
    current["VISUAL_QA_REQUIRED"] = "true"

    write_env(ENV_PATH, current)

    redacted = {
        "env_path": str(ENV_PATH),
        "synced_keys": sorted(k for k in current if current.get(k)),
        "not_copied_by_design": [
            "MAILCOW_API_KEY (too broad; can affect existing voiddo.com mail)",
            "Git credentials (operator/CI concern, not Rescue runtime)",
            "NPM token (publish concern, not Rescue runtime)",
        ],
    }
    print(redacted)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
