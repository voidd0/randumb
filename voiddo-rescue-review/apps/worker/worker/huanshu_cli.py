#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import tempfile
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


def _check_png_dir(path: Path) -> dict[str, Any]:
    issues: list[str] = []
    artifacts: list[str] = []
    pngs = sorted(path.rglob("*.png"))
    if not pngs:
        issues.append("huanshu_no_png_artifacts")
    for png in pngs:
        artifacts.append(str(png))
        try:
            size = png.stat().st_size
        except OSError:
            issues.append("huanshu_unreadable_png")
            continue
        if size < 1000:
            issues.append("huanshu_empty_or_tiny_png")
    return _result(str(path), issues, artifacts, "screenshot-artifact-check")


def _target_to_url(target: str) -> str:
    if target.startswith(("http://", "https://", "file://", "data:")):
        return target
    return Path(target).resolve().as_uri()


def _browser_check(target: str, output: Path | None) -> dict[str, Any]:
    try:
        from playwright.sync_api import sync_playwright
    except Exception:
        return _result(target, ["huanshu_playwright_unavailable"], [], "browser-check")

    issues: list[str] = []
    artifacts: list[str] = []
    console_errors: list[str] = []
    page_errors: list[str] = []
    outdir = output or Path(tempfile.mkdtemp(prefix="huanshu-"))
    outdir.mkdir(parents=True, exist_ok=True)
    url = _target_to_url(target)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            for name, viewport in {"desktop": {"width": 1440, "height": 1000}, "mobile": {"width": 390, "height": 844}}.items():
                page = browser.new_page(viewport=viewport, is_mobile=name == "mobile")
                page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)
                page.on("pageerror", lambda err: page_errors.append(str(err)))
                page.goto(url, wait_until="networkidle", timeout=20000)
                body_text = page.locator("body").inner_text(timeout=3000)
                if "{{" in body_text or "}}" in body_text:
                    issues.append("unresolved_template_vars")
                lowered = body_text.lower()
                if "lorem ipsum" in lowered or "placeholder" in lowered:
                    issues.append("placeholder_text")
                if body_text.lstrip().startswith("{") and body_text.rstrip().endswith("}"):
                    issues.append("raw_json_visible")
                if page.evaluate("() => document.documentElement.scrollWidth > document.documentElement.clientWidth + 2"):
                    issues.append("horizontal_overflow")
                if page.evaluate("() => Array.from(document.images).filter(img => img.complete && img.naturalWidth === 0).length"):
                    issues.append("broken_images")
                cta_visible = page.evaluate(
                    """
                    () => Array.from(document.querySelectorAll('a,button'))
                      .some(el => /fix this issue|start monitoring|open pipeline|view audit|support|unsubscribe|checkout/i.test(el.textContent || '')
                        && el.getBoundingClientRect().top < window.innerHeight)
                    """
                )
                if not cta_visible:
                    issues.append("cta_not_visible_above_fold")
                shot = outdir / f"huanshu-{name}.png"
                page.screenshot(path=str(shot), full_page=True)
                artifacts.append(str(shot))
                page.close()
        finally:
            browser.close()

    if console_errors:
        issues.append("console_errors")
    if page_errors:
        issues.append("page_errors")
    return _result(target, issues, artifacts, "browser-check")


def inspect(target: str, output: Path | None = None) -> dict[str, Any]:
    path = Path(target)
    if path.exists() and path.is_dir():
        return _check_png_dir(path)
    if path.exists() and path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}:
        return _result(str(path), [] if path.stat().st_size >= 1000 else ["huanshu_empty_or_tiny_image"], [str(path)], "image-check")
    return _browser_check(target, output)


def main() -> int:
    parser = argparse.ArgumentParser(description="Huanshu local design QA adapter for Vøiddo Rescue.")
    parser.add_argument("target", nargs="?", help="URL, HTML file, image file, or screenshot directory to inspect")
    parser.add_argument("--version", action="store_true", help="Print adapter version")
    parser.add_argument("--json-out", help="Write JSON report to this path")
    parser.add_argument("--output", help="Screenshot output directory for URL/HTML checks")
    args = parser.parse_args()

    if args.version:
        print(VERSION)
        return 0
    if not args.target:
        parser.error("target is required unless --version is used")

    report = inspect(args.target, Path(args.output) if args.output else None)
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.json_out:
        Path(args.json_out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.json_out).write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
