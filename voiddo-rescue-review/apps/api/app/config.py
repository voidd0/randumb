from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql://voiddo_rescue:change-me@postgres:5432/voiddo_rescue"
    redis_url: str = "redis://redis:6379/0"
    storage_root: str = "/app/storage"

    app_base_url: str = "https://app.rescue.voiddo.com"
    product_base_url: str = "https://rescue.voiddo.com"
    api_base_url: str = "https://api.rescue.voiddo.com"
    audit_base_url: str = "https://audit.rescue.voiddo.com"
    go_base_url: str = "https://go.rescue.voiddo.com"
    status_base_url: str = "https://status.rescue.voiddo.com"

    global_kill_switch: bool = False
    scanning_paused: bool = True
    outreach_dry_run: bool = True
    outreach_paused: bool = True
    auto_replies_paused: bool = True
    customer_mail_sending_enabled: bool = False
    customer_mail_real_send_enabled: bool = False
    paddle_provisioning_paused: bool = True
    first_live_send_flag: bool = False

    smtp_host: str = "mail.voiddo.com"
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from_default: str = "audit@voiddorescue.com"
    imap_host: str = "mail.voiddo.com"
    imap_port: int = 993
    imap_username_audit: str = ""
    imap_password_audit: str = ""
    imap_username_fix: str = ""
    imap_password_fix: str = ""
    imap_username_support: str = ""
    imap_password_support: str = ""
    mail_tls_verify: bool = True

    paddle_api_key: str = ""
    paddle_environment: str = "sandbox"
    paddle_webhook_secret: str = ""
    paddle_price_monitor_monthly: str = ""
    paddle_price_fix_lite_monthly: str = ""
    paddle_price_rescue_pro_monthly: str = ""
    paddle_price_audit_onetime: str = ""
    paddle_price_contact_form_repair: str = ""
    paddle_price_emergency_fix: str = ""
    paddle_hosted_checkout_base_url: str = ""
    paddle_client_token: str = ""

    daily_send_limit: int = 20
    hourly_domain_send_limit: int = 5
    max_bounce_rate: float = 0.05
    email_qa_required: bool = True
    visual_qa_required: bool = True
    admin_auth_token: str = ""
    owner_command_email: str = ""
    studio_owner_command_emails: str = ""
    studio_mail_monitor_enabled: bool = False
    studio_mail_imap_host: str = "127.0.0.1"
    studio_mail_imap_port: int = 993
    studio_mail_username: str = ""
    test_inboxes: str = ""
    test_inbox_pool: str = ""
    warmup_recipient_pool: str = ""
    huanshu_cli: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()
