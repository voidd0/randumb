from __future__ import annotations

import os
import subprocess


def run_huanshu(target_path: str) -> dict:
    candidates = [
        os.environ.get("HUANSHU_CLI", ""),
        "/usr/local/bin/huanshu",
        "/usr/bin/huanshu",
    ]
    executable = next((path for path in candidates if path and os.path.exists(path) and os.access(path, os.X_OK)), "")
    if not executable:
        return {"status": "BLOCKED_HUANSHU_NOT_AVAILABLE", "passed": False, "tool": None}
    try:
        completed = subprocess.run([executable, target_path], text=True, capture_output=True, timeout=60, check=False)
    except Exception as exc:
        return {"status": "BLOCKED_HUANSHU_ERROR", "passed": False, "tool": executable, "error": type(exc).__name__}
    return {
        "status": "PASS" if completed.returncode == 0 else "FAIL_BLOCK_LAUNCH",
        "passed": completed.returncode == 0,
        "tool": executable,
        "summary": completed.stdout[-1000:],
    }
