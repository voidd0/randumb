from __future__ import annotations

from pathlib import Path
from .outreach import now_utc_iso


def create_task(root: str, task_type: str, priority: str, title: str, context: str, evidence: str) -> Path:
    directory = Path(root)
    directory.mkdir(parents=True, exist_ok=True)
    safe = title.lower().replace(" ", "-").replace("/", "-")[:60]
    path = directory / f"{now_utc_iso().replace(':', '').replace('+', 'Z')}-{task_type}-{safe}.md"
    path.write_text(
        f"""# {title}

- type: `{task_type}`
- priority: `{priority}`
- status: `open`
- created_at: `{now_utc_iso()}`

## Context

{context}

## Evidence

{evidence}

## Files Involved

- To be determined by Codex during implementation.

## Constraints

- Do not deploy risky fixes without tests and review gate.
- Do not touch existing vøiddo projects unless the task explicitly scopes them.
- Preserve outreach suppression, unsubscribe, and rate-limit rules.

## Expected Output

- Root cause summary.
- Patch or operational correction.
- Test evidence.
- Rollback note.

## Tests Required

- Focused regression test for the failing case.
- Smoke test for adjacent workflow.

## Rollback Note

Revert only files changed for this task, or disable the specific Rescue worker lane.
""",
        encoding="utf-8",
    )
    return path
