# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Aaron K. Clark
"""Triage tool wrappers — direct in-process imports of triage's API.

We don't subprocess `triage`. Instead we import the package and call
its `Store`, `Scheduler`, etc. directly, then return structured dicts
the MCP tool functions hand back to the agent. Two reasons:

  1. **Speed.** No shell-out, no CLI parsing of pretty-printed text.
  2. **Fidelity.** Results are typed structures (counts, contributions
     with named deltas, full task records), not stringly-typed CLI
     output. The agent sees the same data the scheduler computes.

Every tool returns a dict shaped as
``{ "ok": bool, "result"|"error": ... }`` so the MCP wrapper can
serialize directly. Triage-level errors (bad ids, missing tasks)
come back as ``ok: false`` with a structured ``error`` field, not
exceptions.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

# These are imported once at module load. If `triage-scheduler` isn't
# installed, the ImportError surfaces with the operator-friendly
# pyproject hint in pip output rather than at MCP-tool-call time.
from triage import scheduler
from triage.cron import emit as cron_emit
from triage.model import Signal, Task
from triage.store import Store


def _store() -> Store:
    """Open the store from TRIAGEMCP_HOME (override) or default TRIAGE_HOME."""
    home = os.environ.get("TRIAGEMCP_HOME") or os.environ.get("TRIAGE_HOME")
    return Store(root=home) if home else Store()


def _serialize_task(t: Task) -> dict[str, Any]:
    return {
        "id": t.id,
        "subject": t.subject,
        "description": t.description,
        "created_at": t.created_at,
        "base_score": t.base_score,
        "tags": list(t.tags),
        "deadline": t.deadline,
        "blocked_by": list(t.blocked_by),
        "cron_window": t.cron_window,
    }


def _serialize_scored(s: scheduler.ScoredTask) -> dict[str, Any]:
    return {
        "id": s.task.id,
        "subject": s.task.subject,
        "priority": s.priority,
        "contributions": [
            {"name": c.name, "delta": c.delta} for c in s.contributions
        ],
    }


# ---------- read ----------

async def list_tasks(*, limit: int = 50) -> dict[str, Any]:
    """Return the current priority-ordered task list (capped at `limit`)."""
    store = _store()
    cron_emit(store)
    tasks = store.load_tasks()
    signals = store.active_signals()
    ranked, warnings = scheduler.rank_with_warnings(tasks, signals)
    limit = max(1, min(int(limit or 50), 500))
    return {
        "ok": True,
        "count": len(ranked),
        "limit": limit,
        "warnings": warnings,
        "tasks": [_serialize_scored(s) for s in ranked[:limit]],
    }


async def get_task(*, task_id: str) -> dict[str, Any]:
    """Return the raw task record for `task_id` (or an error if not found)."""
    if not task_id:
        return {"ok": False, "error": "missing task_id"}
    store = _store()
    for t in store.load_tasks():
        if t.id == task_id:
            return {"ok": True, "task": _serialize_task(t)}
    return {"ok": False, "error": f"no task with id {task_id}"}


async def why_task(*, task_id: str) -> dict[str, Any]:
    """Explain a task's current priority — rule-by-rule deltas."""
    if not task_id:
        return {"ok": False, "error": "missing task_id"}
    store = _store()
    cron_emit(store)
    tasks = store.load_tasks()
    signals = store.active_signals()
    ranked, warnings = scheduler.rank_with_warnings(tasks, signals)
    for s in ranked:
        if s.task.id == task_id:
            return {
                "ok": True,
                "warnings": warnings,
                **_serialize_scored(s),
            }
    return {"ok": False, "error": f"no task with id {task_id}"}


async def status() -> dict[str, Any]:
    """One-screen-equivalent summary: top-3, tag counts, signal counts."""
    from collections import Counter
    store = _store()
    cron_emit(store)
    tasks = store.load_tasks()
    signals = store.active_signals()
    ranked, warnings = scheduler.rank_with_warnings(tasks, signals)

    tag_counts: dict[str, int] = Counter()
    for t in tasks:
        for tag in t.tags:
            tag_counts[tag] += 1

    signal_counts: dict[str, int] = Counter()
    for sig in signals:
        signal_counts[sig.source] += 1

    return {
        "ok": True,
        "task_count": len(tasks),
        "ranked_count": len(ranked),
        "tag_counts": dict(tag_counts),
        "signal_counts": dict(signal_counts),
        "top": [_serialize_scored(s) for s in ranked[:3]],
        "warnings": warnings,
    }


# ---------- write ----------

async def add_task(
    *,
    subject: str,
    description: str | None = None,
    base_score: int = 0,
    tags: list[str] | None = None,
    deadline: str | None = None,
    blocked_by: list[str] | None = None,
    cron_window: str | None = None,
) -> dict[str, Any]:
    """Create a new task and return the assigned id + full record."""
    if not subject or not isinstance(subject, str):
        return {"ok": False, "error": "missing subject"}
    store = _store()
    tasks = store.load_tasks()
    task = Task(
        subject=subject,
        description=description or "",
        base_score=int(base_score or 0),
        tags=list(tags or []),
        deadline=deadline,
        blocked_by=list(blocked_by or []),
        cron_window=cron_window,
    )
    tasks.append(task)
    store.save_tasks(tasks)
    return {"ok": True, "task": _serialize_task(task)}


async def remove_task(*, task_id: str) -> dict[str, Any]:
    """Permanently remove a task by id."""
    if not task_id:
        return {"ok": False, "error": "missing task_id"}
    store = _store()
    tasks = store.load_tasks()
    before = len(tasks)
    tasks = [t for t in tasks if t.id != task_id]
    if len(tasks) == before:
        return {"ok": False, "error": f"no task with id {task_id}"}
    store.save_tasks(tasks)
    return {"ok": True, "removed_id": task_id}


async def tick() -> dict[str, Any]:
    """Recompute priorities. Returns top-3 + ranked count + warnings."""
    store = _store()
    emitted = cron_emit(store)
    tasks = store.load_tasks()
    signals = store.active_signals()
    ranked, warnings = scheduler.rank_with_warnings(tasks, signals)
    return {
        "ok": True,
        "emitted_cron_signals": emitted,
        "ranked_count": len(ranked),
        "top": [_serialize_scored(s) for s in ranked[:3]],
        "warnings": warnings,
    }


async def inject_signal(
    *,
    source: str,
    bump: int,
    ttl_seconds: int = 1800,
    affects: list[str] | None = None,
    note: str | None = None,
    state: str | None = None,
) -> dict[str, Any]:
    """Inject a manual signal — agent equivalent of `triage signal manual`."""
    if not source:
        return {"ok": False, "error": "missing source"}
    if not isinstance(bump, int):
        return {"ok": False, "error": "bump must be an integer"}
    store = _store()
    payload: dict[str, Any] = {"bump": bump}
    if note:
        payload["note"] = note
    if state:
        payload["state"] = state
    sig = Signal(
        source=source,
        captured_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        payload=payload,
        affects=list(affects or []),
        ttl_seconds=int(ttl_seconds or 1800),
    )
    store.append_signal(sig)
    return {
        "ok": True,
        "source": source,
        "bump": bump,
        "ttl_seconds": int(ttl_seconds or 1800),
        "affects": list(affects or []),
    }
