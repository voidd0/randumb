from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from playwright.sync_api import sync_playwright
from psycopg.types.json import Jsonb

from .db import connect
from .huanshu_adapter import run_huanshu


AGENTS = {
    "audit_page_visual_agent",
    "landing_visual_agent",
    "app_visual_agent",
    "email_visual_agent",
    "screenshot_evidence_agent",
}


def _check_page(page) -> list[str]:
    issues: list[str] = []
    body_text = page.locator("body").inner_text(timeout=3000)
    if "{{" in body_text or "}}" in body_text:
        issues.append("unresolved_template_vars")
    if "placeholder" in body_text.lower() or "lorem ipsum" in body_text.lower():
        issues.append("placeholder_text")
    if body_text.lstrip().startswith("{") and body_text.rstrip().endswith("}"):
        issues.append("raw_json_visible")
    overflow = page.evaluate("() => document.documentElement.scrollWidth > document.documentElement.clientWidth + 2")
    if overflow:
        issues.append("horizontal_overflow")
    broken_images = page.evaluate(
        "() => Array.from(document.images).filter(img => img.complete && img.naturalWidth === 0).length"
    )
    if broken_images:
        issues.append("broken_images")
    cta_visible = page.evaluate(
        """
        () => Array.from(document.querySelectorAll('a,button'))
          .some(el => /fix this issue|start monitoring|open pipeline|view audit/i.test(el.textContent || '')
            && el.getBoundingClientRect().top < window.innerHeight)
        """
    )
    if not cta_visible:
        issues.append("cta_not_visible_above_fold")
    overlap_count = page.evaluate(
        """
        () => {
          const els = Array.from(document.querySelectorAll('a,button,.metric,.row,.issue,h1,h2,p'))
            .map(el => ({el, r: el.getBoundingClientRect()}))
            .filter(item => item.r.width > 0 && item.r.height > 0);
          let overlaps = 0;
          for (let i = 0; i < els.length; i++) {
            for (let j = i + 1; j < els.length; j++) {
              if (els[i].el.contains(els[j].el) || els[j].el.contains(els[i].el)) continue;
              const a = els[i].r, b = els[j].r;
              const x = Math.max(0, Math.min(a.right, b.right) - Math.max(a.left, b.left));
              const y = Math.max(0, Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top));
              if (x * y > 120 && x > 8 && y > 8) overlaps++;
            }
          }
          return overlaps;
        }
        """
    )
    if overlap_count > 0:
        issues.append("possible_text_overlap")
    return issues


def run_visual_agent(agent: str, target_url: str) -> dict[str, Any]:
    if agent not in AGENTS:
        raise ValueError(f"unknown visual agent: {agent}")
    storage = Path(os.environ.get("STORAGE_ROOT", "/app/storage")) / "visual_qa" / agent
    storage.mkdir(parents=True, exist_ok=True)
    screenshots: list[dict[str, str]] = []
    issues: list[str] = []
    console_errors: list[str] = []

    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            for name, viewport in {"desktop": {"width": 1440, "height": 1000}, "mobile": {"width": 390, "height": 844}}.items():
                page = browser.new_page(viewport=viewport, is_mobile=name == "mobile")
                page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)
                page.goto(target_url, wait_until="networkidle", timeout=20000)
                shot = storage / f"{name}.png"
                page.screenshot(path=str(shot), full_page=True)
                screenshots.append({"type": name, "file_path": str(shot), "viewport": f"{viewport['width']}x{viewport['height']}"})
                issues.extend(_check_page(page))
                page.close()
        finally:
            browser.close()

    if console_errors:
        issues.append("console_errors")
    huanshu = run_huanshu(str(storage))
    if not huanshu.get("passed"):
        issues.append(huanshu["status"])
    issues = sorted(set(issues))
    score = max(0, 100 - 15 * len(issues))
    hard_blockers = {"unresolved_template_vars", "raw_json_visible", "broken_images", "console_errors", "page_errors", "cta_not_visible_above_fold"}
    has_hard_blocker = any(issue in hard_blockers or issue.startswith("BLOCKED_HUANSHU") for issue in issues)
    decision = "FAIL_BLOCK_LAUNCH" if has_hard_blocker or not huanshu.get("passed") else ("PASS" if score >= 90 else "PASS_WITH_WARNINGS")
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO visual_qa_runs(agent, target_url, status, huanshu_status, score, decision, issues_json, screenshots_json, completed_at)
                VALUES (%s, %s, 'completed', %s, %s, %s, %s, %s, now())
                RETURNING id, agent, target_url, huanshu_status, score, decision, issues_json, screenshots_json
                """,
                (agent, target_url, huanshu["status"], score, decision, Jsonb(issues), Jsonb(screenshots)),
            )
            row = cur.fetchone()
        conn.commit()
    return dict(row)
