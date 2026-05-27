#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from urllib.request import Request, urlopen


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


def main() -> None:
    parser = argparse.ArgumentParser(description="Run due Vøiddo Rescue warmup slots through API gates.")
    parser.add_argument("--api-base", default="http://127.0.0.1:18082")
    parser.add_argument("--env", default=str(DEFAULT_ENV))
    parser.add_argument("--limit", type=int, default=2)
    args = parser.parse_args()
    env = load_env(Path(args.env))
    token = os.environ.get("ADMIN_AUTH_TOKEN") or env.get("ADMIN_AUTH_TOKEN")
    if not token:
        raise SystemExit("ADMIN_AUTH_TOKEN missing")
    payload = json.dumps({"limit": max(1, min(args.limit, 2))}).encode("utf-8")
    request = Request(
        f"{args.api_base.rstrip('/')}/admin/warmup/run-due",
        data=payload,
        headers={"Content-Type": "application/json", "X-Admin-Token": token},
        method="POST",
    )
    with urlopen(request, timeout=60) as response:
        result = json.loads(response.read().decode("utf-8"))
    warmup = result.get("warmup", {})
    print(
        json.dumps(
            {
                "ok": bool(result.get("ok")),
                "status": warmup.get("status"),
                "attempted": warmup.get("attempted", 0),
                "sent": warmup.get("sent", 0),
                "blocked": warmup.get("blocked", 0),
                "send_mail": warmup.get("send_mail", False),
                "live_outreach_allowed": warmup.get("live_outreach_allowed", False),
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
