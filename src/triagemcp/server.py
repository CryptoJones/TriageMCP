# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Aaron K. Clark
"""MCP server entry point. Exposes Triage as agent tools over stdio.

Wire into Claude Code via ~/.claude/mcp.json:

    {
      "mcpServers": {
        "triagemcp": {
          "command": "triagemcp"
        }
      }
    }

The agent then has tools to:
  - list_tasks / get_task / why_task / status — read
  - add_task / remove_task / tick / inject_signal — write

All eight tools operate on the same ~/.triage store the `triage`
CLI uses. Override via TRIAGEMCP_HOME or TRIAGE_HOME env vars.
"""

from __future__ import annotations

import sys

from mcp.server.fastmcp import FastMCP

from . import tools

mcp = FastMCP("triagemcp")


# ---------- read tools ----------

@mcp.tool()
async def list_tasks(limit: int = 50) -> dict:
    """Return the priority-ordered task list. Up to `limit` tasks (cap 500)."""
    return await tools.list_tasks(limit=limit)


@mcp.tool()
async def get_task(task_id: str) -> dict:
    """Return the full raw record for `task_id` (or an error if not found)."""
    return await tools.get_task(task_id=task_id)


@mcp.tool()
async def why_task(task_id: str) -> dict:
    """Explain `task_id`'s current priority — rule-by-rule contribution deltas."""
    return await tools.why_task(task_id=task_id)


@mcp.tool()
async def status() -> dict:
    """One-screen summary: top-3 tasks + tag counts + active-signal counts."""
    return await tools.status()


# ---------- write tools ----------

@mcp.tool()
async def add_task(
    subject: str,
    description: str | None = None,
    base_score: int = 0,
    tags: list[str] | None = None,
    deadline: str | None = None,
    blocked_by: list[str] | None = None,
    cron_window: str | None = None,
) -> dict:
    """Create a new task. Returns the assigned id + the full record.

    Args:
      subject: short title for the task (required).
      description: longer markdown body (optional).
      base_score: human-set priority baseline (default 0).
      tags: list of tag strings (e.g. ["env:prod", "vendor:aws"]).
      deadline: ISO 8601 due date (drives the `deadline_decay` rule).
      blocked_by: list of task ids this task depends on (drives
        `blocker_transitive` — blockers auto-rank above what they block).
      cron_window: five-field cron expression for active priority window
        (e.g. "* 9-17 * * 1-5" for weekday business hours).
    """
    return await tools.add_task(
        subject=subject,
        description=description,
        base_score=base_score,
        tags=tags,
        deadline=deadline,
        blocked_by=blocked_by,
        cron_window=cron_window,
    )


@mcp.tool()
async def remove_task(task_id: str) -> dict:
    """Remove a task by id. Permanent — no soft-delete in Triage's task model."""
    return await tools.remove_task(task_id=task_id)


@mcp.tool()
async def tick() -> dict:
    """Recompute priorities right now. Returns the new top-3 + emitted signal counts.

    Equivalent to running `triage tick` from the CLI. Cheap + local —
    safe to call from a polling loop.
    """
    return await tools.tick()


@mcp.tool()
async def inject_signal(
    source: str,
    bump: int,
    ttl_seconds: int = 1800,
    affects: list[str] | None = None,
    note: str | None = None,
    state: str | None = None,
) -> dict:
    """Inject a manual signal — agent equivalent of `triage signal manual`.

    Args:
      source: signal source name (free-form; e.g. "operator", "agent").
      bump: priority delta applied by `rule_manual_bump` while fresh.
      ttl_seconds: signal expiry (default 1800).
      affects: list of task ids the signal targets. Omit to target all.
      note: free-text annotation in the signal payload.
      state: optional state label (e.g. "warning", "critical").
    """
    return await tools.inject_signal(
        source=source,
        bump=bump,
        ttl_seconds=ttl_seconds,
        affects=affects,
        note=note,
        state=state,
    )


def main() -> int:
    """Console entry: launch the stdio MCP server."""
    try:
        mcp.run()
    except KeyboardInterrupt:
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
