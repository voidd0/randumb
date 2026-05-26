from __future__ import annotations

from pydantic import BaseModel, EmailStr, Field, HttpUrl


class ScanRequest(BaseModel):
    url: HttpUrl
    business_name: str | None = None
    dry_run: bool = True


class Issue(BaseModel):
    issue_type: str
    severity: str
    title: str
    public_text: str
    recommendation: str
    evidence_json: dict = Field(default_factory=dict)


class ScanResult(BaseModel):
    domain: str
    url: str
    score: int
    status: str
    summary: str
    public_slug: str
    issues: list[Issue]
    screenshots: list[dict] = Field(default_factory=list)


class OutreachPreviewRequest(BaseModel):
    business_name: str
    domain: str
    contact_name: str | None = None
    email: EmailStr
    language: str = "en"
    main_issue_short: str
    audit_url: str
    unsubscribe_url: str


class SuppressionRequest(BaseModel):
    email: EmailStr | None = None
    domain: str | None = None
    reason: str = "manual"
    source: str = "api"
