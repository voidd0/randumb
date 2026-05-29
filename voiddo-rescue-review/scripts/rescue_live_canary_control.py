#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen


ROOT = Path("/opt/voiddo-rescue")
ENV_PATH = ROOT / ".env"
BACKUP_DIR = ROOT / "backups" / "env"
COMPOSE_PATH = ROOT / "docker-compose.yml"
API_BASE = "http://127.0.0.1:18082"


def read_env(path: Path = ENV_PATH) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def write_env_updates(updates: dict[str, str], path: Path = ENV_PATH) -> Path:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup = BACKUP_DIR / f".env.{stamp}.bak"
    shutil.copy2(path, backup)
    backup.chmod(0o600)

    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    used: set[str] = set()
    output: list[str] = []
    for line in lines:
        if "=" not in line or line.strip().startswith("#"):
            output.append(line)
            continue
        key = line.split("=", 1)[0].strip()
        if key in updates:
            output.append(f"{key}={updates[key]}")
            used.add(key)
        else:
            output.append(line)
    for key, value in updates.items():
        if key not in used:
            output.append(f"{key}={value}")
    tmp = path.with_suffix(".tmp")
    tmp.write_text("\n".join(output) + "\n", encoding="utf-8")
    tmp.chmod(0o600)
    tmp.replace(path)
    path.chmod(0o600)
    return backup


def api_request(path: str, token: str, payload: dict | None = None, method: str = "POST", timeout: int = 180) -> dict:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = Request(
        f"{API_BASE}{path}",
        data=data,
        headers={"Content-Type": "application/json", "X-Admin-Token": token},
        method=method,
    )
    with urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def restart_services(services: list[str]) -> None:
    subprocess.run(["docker", "compose", "-f", str(COMPOSE_PATH), "up", "-d", *services], check=True, stdout=subprocess.DEVNULL)


def preflight(token: str, limit: int) -> dict:
    activation = api_request(f"/admin/launch-activation?limit={limit}", token, None, method="GET")["activation"]
    packet = api_request("/admin/outreach/live-queue/operator-packet", token, {"limit": limit, "run_checkout_simulation": True})["packet"]
    plan = api_request("/admin/outreach/live-queue/send-window-plan", token, {"limit": limit})["plan"]
    return {"activation": activation, "packet": packet, "plan": plan}


def live_queue_status(token: str, limit: int) -> dict:
    return api_request(f"/admin/outreach/live-queue?limit={limit}", token, None, method="GET")


def blockers_from_preflight(snapshot: dict) -> list[str]:
    blockers: list[str] = []
    if snapshot["activation"].get("decision") != "READY_FOR_OPERATOR_ENV_ACTIVATION":
        blockers.append("activation_not_ready")
    blockers.extend(snapshot["activation"].get("blockers") or [])
    if snapshot["packet"].get("status") != "ready":
        blockers.append("operator_packet_not_ready")
    blockers.extend(snapshot["packet"].get("blockers") or [])
    if snapshot["plan"].get("decision") != "READY_NO_SEND_CANARY_WINDOW_PLAN":
        blockers.append("send_window_plan_not_ready")
    blockers.extend(snapshot["plan"].get("blockers") or [])
    return sorted(set(str(item) for item in blockers))


def activate(args: argparse.Namespace, env: dict[str, str], token: str) -> dict:
    if args.confirm != "START LIVE OUTREACH":
        return {"status": "blocked", "blockers": ["confirmation_text_mismatch"], "applied": False}
    if env.get("ALLOW_LIVE_OUTREACH_ACTIVATION", "false").lower() != "true":
        return {"status": "blocked", "blockers": ["allow_live_outreach_activation_env_false"], "applied": False}
    if args.send_window and args.confirm_send_window != "SEND FIRST CANARY":
        return {"status": "blocked", "blockers": ["send_window_confirmation_text_mismatch"], "applied": False}

    snapshot = preflight(token, args.limit)
    blockers = blockers_from_preflight(snapshot)
    if blockers:
        return {"status": "blocked", "blockers": blockers, "applied": False, "preflight": snapshot}
    if not args.apply:
        return {"status": "dry_run", "blockers": [], "applied": False, "preflight": snapshot}

    backup = write_env_updates(
        {
            "OUTREACH_DRY_RUN": "false",
            "OUTREACH_PAUSED": "false",
            "FIRST_LIVE_SEND_FLAG": "true",
            "OUTREACH_WORKER_ENABLED": "false",
            "OUTREACH_MESSAGES_PER_TICK": "1",
        }
    )
    restart_services(["api", "worker"])
    activation = api_request(
        "/admin/launch-activation/apply",
        token,
        {"confirm_text": "START LIVE OUTREACH", "requested_by": "host_canary_control", "limit": args.limit, "dry_run": False},
    )["activation"]
    queue_before = live_queue_status(token, args.limit)
    queued_before = int((queue_before.get("history") or {}).get("queued_message_count") or 0)
    if queued_before > 0:
        staged = {
            "result": {
                "decision": "SKIPPED_EXISTING_QUEUED_CANARY",
                "staged_count": 0,
                "existing_queued_message_count": queued_before,
            }
        }
    else:
        staged = api_request(
            "/admin/outreach/live-queue/stage",
            token,
            {"limit": args.limit, "dry_run": False, "requested_by": "host_canary_control"},
        )["queue"]
    worker_enabled = False
    if args.send_window:
        backup = write_env_updates({"OUTREACH_WORKER_ENABLED": "true", "OUTREACH_MESSAGES_PER_TICK": "1"})
        restart_services(["worker"])
        worker_enabled = True
    return {
        "status": "applied",
        "applied": True,
        "env_backup_path": str(backup),
        "worker_enabled": worker_enabled,
        "activation_decision": activation.get("activation", {}).get("decision"),
        "staged_decision": staged.get("result", {}).get("decision"),
        "staged_count": staged.get("result", {}).get("staged_count"),
        "existing_queued_message_count": staged.get("result", {}).get("existing_queued_message_count", queued_before),
        "sent_count": 0,
        "secrets_included": False,
    }


def rollback(args: argparse.Namespace, token: str) -> dict:
    if args.confirm != "ROLLBACK LIVE OUTREACH":
        return {"status": "blocked", "blockers": ["confirmation_text_mismatch"], "applied": False}
    if not args.apply:
        return {"status": "dry_run", "applied": False}
    backup = write_env_updates(
        {
            "OUTREACH_DRY_RUN": "true",
            "OUTREACH_PAUSED": "true",
            "FIRST_LIVE_SEND_FLAG": "false",
            "OUTREACH_WORKER_ENABLED": "false",
        }
    )
    restart_services(["api", "worker"])
    api_result = api_request("/admin/launch-activation/rollback", token, {"reason": "host_canary_control"})
    return {"status": "rolled_back", "applied": True, "env_backup_path": str(backup), "api": api_result.get("rollback", {})}


def status(token: str, limit: int) -> dict:
    snapshot = preflight(token, limit)
    return {"status": "ready" if not blockers_from_preflight(snapshot) else "blocked", "blockers": blockers_from_preflight(snapshot), "preflight": snapshot}


def main() -> int:
    parser = argparse.ArgumentParser(description="Controlled Vøiddo Rescue live canary activation/rollback.")
    parser.add_argument("--action", choices=["status", "activate", "rollback"], default="status")
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--send-window", action="store_true", help="After staging, enable worker drain at one message per tick.")
    parser.add_argument("--confirm", default="")
    parser.add_argument("--confirm-send-window", default="")
    args = parser.parse_args()

    env = read_env()
    token = os.environ.get("ADMIN_AUTH_TOKEN") or env.get("ADMIN_AUTH_TOKEN", "")
    if not token:
        print(json.dumps({"status": "blocked", "blockers": ["admin_auth_token_missing"]}, sort_keys=True), file=sys.stderr)
        return 1
    if args.action == "status":
        result = status(token, args.limit)
    elif args.action == "rollback":
        result = rollback(args, token)
    else:
        result = activate(args, env, token)
    result.update({"send_mail": False, "live_outreach_allowed": False, "raw_recipient_addresses_included": False})
    print(json.dumps(result, sort_keys=True, default=str))
    return 0 if result.get("status") in {"ready", "dry_run", "applied", "rolled_back"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
