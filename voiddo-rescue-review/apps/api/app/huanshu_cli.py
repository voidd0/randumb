#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

VERSION = "huanshu-local-adapter 0.1.0 (huashu-design verify compatible)"


def _result(target: str, issues: list[str], artifacts: list[str], mode: str) -> dict[str, Any]:
    blocking = sorted(set(issues))
    decision = "PASS" if not blocking else "FAIL_BLOCK_LAUNCH"
    return {
        "tool": "huanshu-local-adapter",
        "version": VERSION,
        "mode": mode,
        "target": target,
        "decision": decision,
        "passed": decision == "PASS",
        "issues": blocking,
        "artifacts": artifacts,
    }


def inspect(target: str) -> dict[str, Any]:
    path = Path(target)
    issues: list[str] = []
    artifacts: list[str] = []
    if path.exists() and path.is_dir():
        pngs = sorted(path.rglob("*.png"))
        if not pngs:
            issues.append("huanshu_no_png_artifacts")
        for png in pngs:
            artifacts.append(str(png))
            if png.stat().st_size < 1000:
                issues.append("huanshu_empty_or_tiny_png")
        return _result(str(path), issues, artifacts, "screenshot-artifact-check")
    if path.exists() and path.suffix.lower() in {".html", ".htm"}:
        html = path.read_text(encoding="utf-8", errors="ignore")
        if "{{" in html or "}}" in html:
            issues.append("unresolved_template_vars")
        if "placeholder" in html.lower() or "lorem ipsum" in html.lower():
            issues.append("placeholder_text")
        return _result(str(path), issues, [str(path)], "html-static-check")
    return _result(target, [], [], "availability-check")


def main() -> int:
    parser = argparse.ArgumentParser(description="Huanshu local design QA adapter for Vøiddo Rescue API.")
    parser.add_argument("target", nargs="?")
    parser.add_argument("--version", action="store_true")
    parser.add_argument("--json-out")
    parser.add_argument("--output")
    args = parser.parse_args()
    if args.version:
        print(VERSION)
        return 0
    if not args.target:
        parser.error("target is required unless --version is used")
    report = inspect(args.target)
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.json_out:
        Path(args.json_out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.json_out).write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
