from __future__ import annotations

from urllib.parse import urlencode


PRODUCTS = {
    "monitor_monthly": {"name": "Website Monitor Monthly", "amount": 19, "currency": "USD", "mode": "subscription"},
    "fix_lite_monthly": {"name": "Fix Lite Monthly", "amount": 49, "currency": "USD", "mode": "subscription"},
    "rescue_pro_monthly": {"name": "Rescue Pro Monthly", "amount": 99, "currency": "USD", "mode": "subscription"},
    "audit_onetime": {"name": "Website Rescue Audit", "amount": 49, "currency": "USD", "mode": "one_time"},
    "contact_form_repair": {"name": "Contact Form Repair", "amount": 99, "currency": "USD", "mode": "one_time"},
    "emergency_fix": {"name": "Emergency Website Fix", "amount": 149, "currency": "USD", "mode": "one_time"},
}


def price_id_for(settings, product_key: str) -> str:
    mapping = {
        "monitor_monthly": settings.paddle_price_monitor_monthly,
        "fix_lite_monthly": settings.paddle_price_fix_lite_monthly,
        "rescue_pro_monthly": settings.paddle_price_rescue_pro_monthly,
        "audit_onetime": settings.paddle_price_audit_onetime,
        "contact_form_repair": settings.paddle_price_contact_form_repair,
        "emergency_fix": settings.paddle_price_emergency_fix,
    }
    return mapping.get(product_key, "")


def checkout_config_status(settings) -> dict[str, object]:
    missing = [key for key in PRODUCTS if not price_id_for(settings, key)]
    return {
        "environment": settings.paddle_environment,
        "api_key_configured": bool(settings.paddle_api_key),
        "webhook_secret_configured": bool(settings.paddle_webhook_secret),
        "missing_price_keys": missing,
        "ready": bool(settings.paddle_api_key and settings.paddle_webhook_secret and not missing),
    }


def hosted_checkout_url(settings, product_key: str, audit_slug: str = "", email: str = "") -> str:
    price_id = price_id_for(settings, product_key)
    base = settings.paddle_hosted_checkout_base_url.rstrip("?&")
    if not base or not price_id:
        return ""
    params = {"price_id": price_id}
    if audit_slug:
        params["utm_content"] = audit_slug
    if email:
        params["user_email"] = email
    separator = "&" if "?" in base else "?"
    return f"{base}{separator}{urlencode(params)}"
