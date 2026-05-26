#!/usr/bin/env python3
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import urllib.error
import urllib.parse
import urllib.request


ROOT = Path("/opt/voiddo-rescue")
ENV_PATH = ROOT / ".env"
STATE_PATH = ROOT / "reports" / "paddle_products_state.json"
REPORT_PATH = ROOT / "reports" / "paddle_setup_report.md"

EU_COUNTRIES = [
    "DE", "FR", "IT", "ES", "NL", "BE", "AT", "IE", "PT", "FI", "GR", "LU",
    "SI", "SK", "EE", "LV", "LT", "CY", "MT", "HR", "BG", "RO", "HU", "PL",
    "CZ", "DK", "SE",
]

PRODUCTS = [
    {
        "key": "monitor_monthly",
        "env": "PADDLE_PRICE_MONITOR_MONTHLY",
        "name": "Vøiddo Rescue · Website Monitor Monthly",
        "description": "Monthly public website monitoring for visible enquiry-path, uptime, HTTPS, mobile CTA, and contact-signal issues.",
        "amount": 1900,
        "billing_cycle": {"interval": "month", "frequency": 1},
    },
    {
        "key": "fix_lite_monthly",
        "env": "PADDLE_PRICE_FIX_LITE_MONTHLY",
        "name": "Vøiddo Rescue · Fix Lite Monthly",
        "description": "Monthly monitoring plus small safe website fixes, issue tracking, and customer-facing progress reports.",
        "amount": 4900,
        "billing_cycle": {"interval": "month", "frequency": 1},
    },
    {
        "key": "rescue_pro_monthly",
        "env": "PADDLE_PRICE_RESCUE_PRO_MONTHLY",
        "name": "Vøiddo Rescue · Rescue Pro Monthly",
        "description": "Priority monitoring and fix workflow for small business websites with recurring public checks and support.",
        "amount": 9900,
        "billing_cycle": {"interval": "month", "frequency": 1},
    },
    {
        "key": "audit_onetime",
        "env": "PADDLE_PRICE_AUDIT_ONETIME",
        "name": "Vøiddo Rescue · Website Rescue Audit",
        "description": "One-time public website audit with screenshots, visible issue evidence, and prioritized fix recommendations.",
        "amount": 4900,
        "billing_cycle": None,
    },
    {
        "key": "contact_form_repair",
        "env": "PADDLE_PRICE_CONTACT_FORM_REPAIR",
        "name": "Vøiddo Rescue · Contact Form Repair",
        "description": "One-time contact form or enquiry path repair workflow for small business websites after customer onboarding.",
        "amount": 9900,
        "billing_cycle": None,
    },
    {
        "key": "emergency_fix",
        "env": "PADDLE_PRICE_EMERGENCY_FIX",
        "name": "Vøiddo Rescue · Emergency Website Fix",
        "description": "One-time priority website rescue workflow for visible customer-enquiry blockers and urgent public-site issues.",
        "amount": 14900,
        "billing_cycle": None,
    },
]


def read_env() -> dict[str, str]:
    values: dict[str, str] = {}
    for line in ENV_PATH.read_text(encoding="utf-8", errors="replace").splitlines():
        if "=" in line and not line.strip().startswith("#"):
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip()
    return values


def write_env(updates: dict[str, str]) -> None:
    lines = ENV_PATH.read_text(encoding="utf-8").splitlines()
    seen: set[str] = set()
    output: list[str] = []
    for line in lines:
        if "=" not in line or line.strip().startswith("#"):
            output.append(line)
            continue
        key = line.split("=", 1)[0].strip()
        if key in updates:
            output.append(f"{key}={updates[key]}")
            seen.add(key)
        else:
            output.append(line)
    for key, value in updates.items():
        if key not in seen:
            output.append(f"{key}={value}")
    tmp = ENV_PATH.with_suffix(".tmp")
    tmp.write_text("\n".join(output) + "\n", encoding="utf-8")
    tmp.chmod(0o600)
    tmp.replace(ENV_PATH)
    ENV_PATH.chmod(0o600)


def request(api_key: str, method: str, path: str, payload: dict | None = None) -> dict[str, Any]:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        "https://api.paddle.com" + path,
        data=data,
        method=method,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=35) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[:1000]
        raise RuntimeError(f"Paddle API HTTP {exc.code}: {body}") from exc


def fetch_all(api_key: str, resource: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    after = ""
    while True:
        qs = {"per_page": "100"}
        if after:
            qs["after"] = after
        data = request(api_key, "GET", f"/{resource}?{urllib.parse.urlencode(qs)}")
        batch = data.get("data") or []
        if isinstance(batch, list):
            rows.extend([row for row in batch if isinstance(row, dict)])
        pagination = (data.get("meta") or {}).get("pagination") or {}
        if not pagination.get("has_more"):
            break
        next_value = str(pagination.get("next") or "")
        if next_value.startswith("http"):
            after = urllib.parse.parse_qs(urllib.parse.urlparse(next_value).query).get("after", [""])[0]
        else:
            after = next_value
        if not after:
            break
    return rows


def create_product(api_key: str, item: dict[str, Any]) -> dict[str, Any]:
    return request(api_key, "POST", "/products", {
        "name": item["name"],
        "description": item["description"],
        "tax_category": "standard",
        "type": "standard",
    })["data"]


def create_price(api_key: str, product_id: str, item: dict[str, Any]) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "product_id": product_id,
        "description": f"{item['name']} — ${item['amount'] // 100}{'/month' if item['billing_cycle'] else ' one-time'}",
        "unit_price": {"amount": str(item["amount"]), "currency_code": "USD"},
        "unit_price_overrides": [{"country_codes": EU_COUNTRIES, "unit_price": {"amount": str(item["amount"]), "currency_code": "EUR"}}],
        "billing_cycle": item["billing_cycle"],
        "tax_mode": "account_setting",
        "quantity": {"minimum": 1, "maximum": 1},
    }
    return request(api_key, "POST", "/prices", payload)["data"]


def main() -> int:
    env = read_env()
    api_key = env.get("PADDLE_API_KEY", "")
    if not api_key:
        raise SystemExit("PADDLE_API_KEY missing in /opt/voiddo-rescue/.env")

    products = fetch_all(api_key, "products")
    prices = fetch_all(api_key, "prices")
    by_name = {str(product.get("name")): product for product in products}
    updates: dict[str, str] = {}
    state: dict[str, Any] = {"updated_at": datetime.now(timezone.utc).isoformat(), "products": {}}

    for item in PRODUCTS:
        product = by_name.get(item["name"])
        product_status = "exists"
        if not product:
            product = create_product(api_key, item)
            by_name[item["name"]] = product
            product_status = "created"
        product_id = product["id"]
        matching_prices = [
            price for price in prices
            if price.get("product_id") == product_id
            and str(((price.get("unit_price") or {}).get("amount") or "")) == str(item["amount"])
            and (price.get("billing_cycle") or None) == item["billing_cycle"]
            and price.get("status") == "active"
        ]
        price_status = "exists"
        if matching_prices:
            price = matching_prices[0]
        else:
            price = create_price(api_key, product_id, item)
            prices.append(price)
            price_status = "created"
        updates[item["env"]] = price["id"]
        state["products"][item["key"]] = {
            "name": item["name"],
            "product_id": product_id,
            "product_status": product_status,
            "price_id": price["id"],
            "price_status": price_status,
            "amount_usd": item["amount"] / 100,
            "billing": "monthly" if item["billing_cycle"] else "one_time",
        }

    write_env(updates)
    STATE_PATH.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    lines = [
        "# Paddle Setup Report",
        "",
        f"Generated: {state['updated_at']}",
        "",
        "## Products And Prices",
        "",
    ]
    for key, row in state["products"].items():
        lines.append(f"- `{key}`: product `{row['product_status']}`, price `{row['price_status']}`, env price id set.")
    lines.extend([
        "",
        "## Secret Handling",
        "",
        "- Paddle API key was read from `/opt/voiddo-rescue/.env` and not printed.",
        "- Price IDs were written to `/opt/voiddo-rescue/.env` and redacted from chat output.",
        "- No transactions or charges were created.",
    ])
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"ok": True, "state_path": str(STATE_PATH), "report_path": str(REPORT_PATH), "products": list(state["products"].keys())}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
