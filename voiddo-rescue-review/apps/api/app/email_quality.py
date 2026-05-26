from __future__ import annotations

from dataclasses import dataclass, field
import re


REQUIRED_FOOTER = "Public non-invasive website check."
REQUIRED_UNSUBSCRIBE = "Unsubscribe:"
SIGNATURE = "Vøiddo Rescue"
RISKY_PHRASES = [
    "security vulnerability",
    "you are hacked",
    "urgent",
    "act now",
    "last chance",
    "we exploited",
    "guaranteed",
    "lawsuit",
]


@dataclass
class EmailQualityResult:
    passed: bool
    score: int
    issues: list[str] = field(default_factory=list)


def check_email_quality(subject: str, body: str) -> EmailQualityResult:
    issues: list[str] = []
    if not subject.strip():
        issues.append("missing_subject")
    if len(subject) > 90:
        issues.append("subject_too_long")
    if len(body.strip()) < 120:
        issues.append("body_too_short")
    if REQUIRED_FOOTER not in body:
        issues.append("missing_public_check_footer")
    if REQUIRED_UNSUBSCRIBE not in body:
        issues.append("missing_unsubscribe")
    if SIGNATURE not in body:
        issues.append("missing_signature")
    if re.search(r"https?://", body) is None:
        issues.append("missing_proof_link")
    lower = body.lower()
    for phrase in RISKY_PHRASES:
        if phrase in lower:
            issues.append(f"risky_phrase:{phrase}")
    if "possible issue" not in subject.lower() and "בעיה אפשרית" not in subject and "võimalik probleem" not in subject.lower():
        issues.append("subject_not_softened")
    if "may affect" not in lower and "עלולה" not in body and "võib mõjutada" not in lower:
        issues.append("impact_not_softened")
    score = max(0, 100 - len(issues) * 12)
    return EmailQualityResult(passed=not issues and score >= 90, score=score, issues=issues)


def beautiful_signature(language: str = "en") -> str:
    if language == "he":
        return (
            "בברכה,\n"
            "Vøiddo Rescue\n"
            "Public non-invasive website checks · monitoring · small site fixes\n"
            "support@voiddorescue.com"
        )
    if language == "et":
        return (
            "Parimat,\n"
            "Vøiddo Rescue\n"
            "Avalikud mitteinvasiivsed veebikontrollid · jälgimine · väikesed parandused\n"
            "support@voiddorescue.com"
        )
    return (
        "Best,\n"
        "Vøiddo Rescue\n"
        "Public non-invasive website checks · monitoring · small site fixes\n"
        "support@voiddorescue.com"
    )
