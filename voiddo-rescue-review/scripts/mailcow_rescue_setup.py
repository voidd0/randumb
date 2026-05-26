#!/usr/bin/env python3
from __future__ import annotations

import argparse
import imaplib
import json
import os
from pathlib import Path
import secrets
import smtplib
import ssl
import string
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request


DOMAIN = "voiddorescue.com"
MAILCOW_CONF = Path("/opt/mailcow-dockerized/mailcow.conf")
VAULT_FILE = Path("/root/.voiddo-secrets/voiddorescue-mailboxes.env")
API_BASE = "http://127.0.0.1:8080/api/v1"
MAILBOXES = ["hello", "audit", "fix", "support", "alerts", "billing", "dmarc", "unsubscribe"]


def read_mailcow_api_key() -> str:
    for line in MAILCOW_CONF.read_text(encoding="utf-8").splitlines():
        if line.startswith("API_KEY="):
            return line.split("=", 1)[1].strip()
    raise RuntimeError("API_KEY not found in Mailcow config")


def api_request(method: str, path: str, payload: dict | None = None):
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        f"{API_BASE}{path}",
        data=data,
        method=method,
        headers={"X-API-Key": read_mailcow_api_key(), "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Mailcow API HTTP {exc.code} for {path}: {body[:300]}") from exc
    return json.loads(raw) if raw else None


def password() -> str:
    alphabet = string.ascii_letters + string.digits + "-_@#%+=."
    return "".join(secrets.choice(alphabet) for _ in range(28))


def read_vault() -> dict[str, str]:
    if not VAULT_FILE.exists():
        return {}
    result: dict[str, str] = {}
    for line in VAULT_FILE.read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.startswith("#"):
            key, value = line.split("=", 1)
            result[key.strip()] = value.strip()
    return result


def write_vault(values: dict[str, str]) -> None:
    VAULT_FILE.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    tmp = VAULT_FILE.with_suffix(".tmp")
    lines = [
        "# Vøiddo Rescue Mailcow mailbox credentials",
        "# Values are secret. Do not commit or print.",
        f"DOMAIN={DOMAIN}",
    ]
    for local in MAILBOXES:
        key = f"MAILBOX_{local.upper()}_PASSWORD"
        lines.append(f"{key}={values[key]}")
    tmp.write_text("\n".join(lines) + "\n", encoding="utf-8")
    os.chmod(tmp, 0o600)
    tmp.replace(VAULT_FILE)
    os.chmod(VAULT_FILE, 0o600)


def ensure_passwords() -> dict[str, str]:
    values = read_vault()
    changed = False
    for local in MAILBOXES:
        key = f"MAILBOX_{local.upper()}_PASSWORD"
        if not values.get(key):
            values[key] = password()
            changed = True
    if changed or not VAULT_FILE.exists():
        write_vault(values)
    return values


def response_ok(response) -> bool:
    items = response if isinstance(response, list) else [response]
    for item in items:
        if isinstance(item, dict) and item.get("type") in {"success", "warning"}:
            return True
        if isinstance(item, dict) and item.get("type") == "danger":
            msg = " ".join(str(part) for part in item.get("msg", []))
            if "exists" in msg.lower() or "duplicate" in msg.lower():
                return True
    return False


def get_domains() -> list[dict]:
    response = api_request("GET", "/get/domain/all")
    return response if isinstance(response, list) else []


def get_mailboxes() -> list[dict]:
    response = api_request("GET", f"/get/mailbox/all/{DOMAIN}")
    return response if isinstance(response, list) else []


def ensure_domain() -> str:
    domains = get_domains()
    if any(item.get("domain_name") == DOMAIN for item in domains):
        return "exists"
    payload = {
        "domain": DOMAIN,
        "description": "Vøiddo Rescue outreach and customer support mail",
        "aliases": "100",
        "mailboxes": "20",
        "defquota": "1024",
        "maxquota": "2048",
        "quota": "20480",
        "active": "1",
        "backupmx": "0",
        "relay_all_recipients": "0",
        "gal": "0",
        "rl_value": "5",
        "rl_frame": "m",
        "tags": ["voiddo-rescue"],
    }
    response = api_request("POST", "/add/domain", payload)
    if not response_ok(response):
        raise RuntimeError(f"domain add failed: {redact_response(response)}")
    return "created"


def ensure_mailboxes(passwords: dict[str, str]) -> dict[str, str]:
    existing = {item.get("username") or f"{item.get('local_part')}@{item.get('domain')}" for item in get_mailboxes()}
    statuses: dict[str, str] = {}
    for local in MAILBOXES:
        address = f"{local}@{DOMAIN}"
        if address in existing:
            statuses[address] = "exists"
            continue
        payload = {
            "local_part": local,
            "domain": DOMAIN,
            "name": f"Vøiddo Rescue {local}",
            "authsource": "mailcow",
            "password": passwords[f"MAILBOX_{local.upper()}_PASSWORD"],
            "password2": passwords[f"MAILBOX_{local.upper()}_PASSWORD"],
            "quota": "1024",
            "active": "1",
            "force_pw_update": "0",
            "tls_enforce_in": "0",
            "tls_enforce_out": "0",
            "tags": ["voiddo-rescue"],
        }
        response = api_request("POST", "/add/mailbox", payload)
        if not response_ok(response):
            raise RuntimeError(f"mailbox add failed for {address}: {redact_response(response)}")
        statuses[address] = "created"
    return statuses


def ensure_dkim() -> dict:
    current = get_dkim(allow_missing=True)
    if current.get("dkim_txt"):
        current["status"] = "exists"
        return current
    response = api_request("POST", "/add/dkim", {"dkim_selector": "dkim", "domains": DOMAIN, "key_size": "2048"})
    if not response_ok(response):
        raise RuntimeError(f"DKIM add failed: {redact_response(response)}")
    result = get_dkim(allow_missing=False)
    result["status"] = "created"
    return result


def get_dkim(allow_missing: bool) -> dict:
    try:
        response = api_request("GET", f"/get/dkim/{urllib.parse.quote(DOMAIN)}")
    except RuntimeError:
        if allow_missing:
            return {}
        raise
    return response if isinstance(response, dict) else {}


def redact_response(response) -> str:
    text = json.dumps(response, ensure_ascii=False)
    for key in read_vault().values():
        if key:
            text = text.replace(key, "[REDACTED]")
    return text


def dns_value(args: list[str]) -> str:
    try:
        return subprocess.check_output(["dig", "+short", *args], text=True, timeout=10).strip()
    except Exception as exc:
        return f"ERROR: {exc}"


def verify_dns() -> dict[str, str]:
    return {
        "A @": dns_value(["A", DOMAIN]),
        "A mail": dns_value(["A", f"mail.{DOMAIN}"]),
        "A go": dns_value(["A", f"go.{DOMAIN}"]),
        "A track": dns_value(["A", f"track.{DOMAIN}"]),
        "CNAME www": dns_value(["CNAME", f"www.{DOMAIN}"]),
        "CNAME autoconfig": dns_value(["CNAME", f"autoconfig.{DOMAIN}"]),
        "CNAME autodiscover": dns_value(["CNAME", f"autodiscover.{DOMAIN}"]),
        "MX @": dns_value(["MX", DOMAIN]),
        "TXT @": dns_value(["TXT", DOMAIN]),
        "TXT _dmarc": dns_value(["TXT", f"_dmarc.{DOMAIN}"]),
        "TXT dkim._domainkey": dns_value(["TXT", f"dkim._domainkey.{DOMAIN}"]),
    }


def test_smtp_imap(passwords: dict[str, str], insecure_tls: bool = False) -> dict[str, str]:
    results: dict[str, str] = {}
    context = ssl._create_unverified_context() if insecure_tls else ssl.create_default_context()
    for local in ["audit", "support"]:
        address = f"{local}@{DOMAIN}"
        pw = passwords[f"MAILBOX_{local.upper()}_PASSWORD"]
        try:
            with smtplib.SMTP(f"mail.{DOMAIN}", 587, timeout=20) as smtp:
                smtp.ehlo()
                smtp.starttls(context=context)
                smtp.ehlo()
                smtp.login(address, pw)
            results[f"smtp:{address}"] = "ok_insecure_tls" if insecure_tls else "ok"
        except Exception as exc:
            results[f"smtp:{address}"] = f"failed:{type(exc).__name__}"
        try:
            with imaplib.IMAP4_SSL(f"mail.{DOMAIN}", 993, ssl_context=context, timeout=20) as imap:
                imap.login(address, pw)
                imap.logout()
            results[f"imap:{address}"] = "ok_insecure_tls" if insecure_tls else "ok"
        except Exception as exc:
            results[f"imap:{address}"] = f"failed:{type(exc).__name__}"
    return results


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Create domain/mailboxes/DKIM if missing")
    parser.add_argument("--test-logins", action="store_true", help="Run SMTP/IMAP login tests for audit/support")
    parser.add_argument("--insecure-tls", action="store_true", help="Disable cert verification for diagnosis only")
    args = parser.parse_args()

    summary: dict[str, object] = {
        "domain": DOMAIN,
        "api_reachable": False,
        "domain_status": "not_checked",
        "mailboxes": {},
        "dkim": {},
        "dns": verify_dns(),
        "smtp_imap": {},
        "vault_file": str(VAULT_FILE),
    }

    get_domains()
    summary["api_reachable"] = True

    if args.apply:
        passwords = ensure_passwords()
        summary["domain_status"] = ensure_domain()
        summary["mailboxes"] = ensure_mailboxes(passwords)
        dkim = ensure_dkim()
        summary["dkim"] = {
            "status": dkim.get("status"),
            "selector": dkim.get("dkim_selector", "dkim"),
            "txt_name": f"dkim._domainkey.{DOMAIN}",
            "txt_value": dkim.get("dkim_txt", ""),
            "length": dkim.get("length", ""),
        }
        summary["dns"] = verify_dns()
        if args.test_logins:
            summary["smtp_imap"] = test_smtp_imap(passwords, insecure_tls=args.insecure_tls)
    else:
        summary["domain_status"] = "exists" if any(item.get("domain_name") == DOMAIN for item in get_domains()) else "missing"
        summary["mailboxes"] = {item.get("username", ""): "exists" for item in get_mailboxes()} if summary["domain_status"] == "exists" else {}
        dkim = get_dkim(allow_missing=True)
        summary["dkim"] = {
            "status": "exists" if dkim.get("dkim_txt") else "missing",
            "selector": dkim.get("dkim_selector", "dkim"),
            "txt_name": f"dkim._domainkey.{DOMAIN}",
            "txt_value": dkim.get("dkim_txt", ""),
            "length": dkim.get("length", ""),
        }

    print(json.dumps(summary, indent=2, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
