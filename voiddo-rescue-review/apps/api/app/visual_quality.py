from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


REQUIRED_REPORTS = [
    "visual_qa_desktop.png",
    "visual_qa_mobile.png",
    "visual_qa_report.md",
]


@dataclass
class VisualQualityResult:
    passed: bool
    issues: list[str] = field(default_factory=list)


def check_visual_publish_gate(artifact_dir: str) -> VisualQualityResult:
    path = Path(artifact_dir)
    issues: list[str] = []
    if not path.exists():
        issues.append("artifact_dir_missing")
    for name in REQUIRED_REPORTS:
        if not (path / name).exists():
            issues.append(f"missing_{name}")
    report = path / "visual_qa_report.md"
    if report.exists():
        text = report.read_text(encoding="utf-8", errors="replace").lower()
        for required in ["huashu", "desktop", "mobile", "no overlap", "no horizontal overflow"]:
            if required not in text:
                issues.append(f"report_missing:{required}")
    return VisualQualityResult(passed=not issues, issues=issues)
