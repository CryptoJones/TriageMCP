# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Aaron K. Clark
"""Direct-call tests for triagemcp.tools.

We exercise the tool functions in-process (no MCP transport, no
network) against a fresh Triage store rooted at a tmp_path.
"""

from __future__ import annotations

import pytest

from triagemcp import tools


@pytest.fixture(autouse=True)
def _isolate_store(tmp_path, monkeypatch):
    """Every test gets a fresh Triage store under tmp_path."""
    monkeypatch.setenv("TRIAGEMCP_HOME", str(tmp_path))
    monkeypatch.delenv("TRIAGE_HOME", raising=False)
    yield


# ---------- list_tasks ----------

@pytest.mark.asyncio
async def test_list_empty_store():
    r = await tools.list_tasks()
    assert r["ok"] is True
    assert r["count"] == 0
    assert r["tasks"] == []


@pytest.mark.asyncio
async def test_list_after_adds_returns_priority_order():
    await tools.add_task(subject="low", base_score=1)
    await tools.add_task(subject="high", base_score=100)
    await tools.add_task(subject="mid", base_score=20)
    r = await tools.list_tasks()
    subjects = [t["subject"] for t in r["tasks"]]
    assert subjects == ["high", "mid", "low"]


@pytest.mark.asyncio
async def test_list_respects_limit():
    for i in range(5):
        await tools.add_task(subject=f"t{i}", base_score=i)
    r = await tools.list_tasks(limit=3)
    assert len(r["tasks"]) == 3
    assert r["limit"] == 3
    assert r["count"] == 5  # total, not page-clamped


@pytest.mark.asyncio
async def test_list_limit_capped_at_500():
    r = await tools.list_tasks(limit=10_000)
    assert r["limit"] == 500


# ---------- add_task ----------

@pytest.mark.asyncio
async def test_add_returns_task_with_id():
    r = await tools.add_task(subject="hello", base_score=5, tags=["x"])
    assert r["ok"] is True
    assert isinstance(r["task"]["id"], str)
    assert r["task"]["subject"] == "hello"
    assert r["task"]["base_score"] == 5
    assert r["task"]["tags"] == ["x"]


@pytest.mark.asyncio
async def test_add_rejects_missing_subject():
    r = await tools.add_task(subject="")
    assert r["ok"] is False
    assert "subject" in r["error"]


@pytest.mark.asyncio
async def test_add_with_deadline_and_blocked_by():
    parent = await tools.add_task(subject="blocker")
    child = await tools.add_task(
        subject="child",
        blocked_by=[parent["task"]["id"]],
        deadline="2026-12-31T00:00:00Z",
    )
    assert child["task"]["blocked_by"] == [parent["task"]["id"]]
    assert child["task"]["deadline"] == "2026-12-31T00:00:00Z"


# ---------- get_task ----------

@pytest.mark.asyncio
async def test_get_returns_full_record():
    added = await tools.add_task(subject="x", description="hello", base_score=7)
    r = await tools.get_task(task_id=added["task"]["id"])
    assert r["ok"] is True
    assert r["task"]["description"] == "hello"
    assert r["task"]["base_score"] == 7


@pytest.mark.asyncio
async def test_get_missing_id():
    r = await tools.get_task(task_id="deadbeef0000")
    assert r["ok"] is False
    assert "no task" in r["error"]


@pytest.mark.asyncio
async def test_get_empty_id():
    r = await tools.get_task(task_id="")
    assert r["ok"] is False
    assert "missing" in r["error"]


# ---------- why_task ----------

@pytest.mark.asyncio
async def test_why_returns_contributions():
    added = await tools.add_task(subject="x", base_score=10)
    r = await tools.why_task(task_id=added["task"]["id"])
    assert r["ok"] is True
    assert r["priority"] == 10
    names = [c["name"] for c in r["contributions"]]
    assert "base_score" in names


@pytest.mark.asyncio
async def test_why_blocker_propagation_visible():
    blocker = await tools.add_task(subject="block", base_score=1)
    blocked = await tools.add_task(
        subject="blocked", base_score=100, blocked_by=[blocker["task"]["id"]]
    )
    r = await tools.why_task(task_id=blocker["task"]["id"])
    # Blocker should have been auto-bumped to >= blocked.priority + 1
    assert r["priority"] >= 101
    bump = next(c for c in r["contributions"] if c["name"] == "blocker_transitive")
    assert bump["delta"] >= 100


# ---------- remove_task ----------

@pytest.mark.asyncio
async def test_remove_existing():
    added = await tools.add_task(subject="goner")
    r = await tools.remove_task(task_id=added["task"]["id"])
    assert r["ok"] is True
    assert r["removed_id"] == added["task"]["id"]
    listed = await tools.list_tasks()
    assert listed["count"] == 0


@pytest.mark.asyncio
async def test_remove_missing():
    r = await tools.remove_task(task_id="deadbeef0000")
    assert r["ok"] is False


# ---------- tick + status ----------

@pytest.mark.asyncio
async def test_tick_returns_top_3():
    for i in range(5):
        await tools.add_task(subject=f"t{i}", base_score=i * 10)
    r = await tools.tick()
    assert r["ok"] is True
    assert r["ranked_count"] == 5
    assert len(r["top"]) == 3
    # Top should be in descending priority order
    priorities = [t["priority"] for t in r["top"]]
    assert priorities == sorted(priorities, reverse=True)


@pytest.mark.asyncio
async def test_status_returns_summary():
    await tools.add_task(subject="a", tags=["env:prod", "x"])
    await tools.add_task(subject="b", tags=["env:prod"])
    r = await tools.status()
    assert r["ok"] is True
    assert r["task_count"] == 2
    assert r["tag_counts"]["env:prod"] == 2
    assert r["tag_counts"]["x"] == 1


# ---------- inject_signal ----------

@pytest.mark.asyncio
async def test_inject_signal_bumps_targeted_task():
    bumped = await tools.add_task(subject="bumped", base_score=1)
    calm = await tools.add_task(subject="calm", base_score=10)
    r = await tools.inject_signal(
        source="operator",
        bump=100,
        ttl_seconds=600,
        affects=[bumped["task"]["id"]],
    )
    assert r["ok"] is True
    # After signal, bumped (1 + 100 = 101) should outrank calm (10)
    listed = await tools.list_tasks()
    subjects = [t["subject"] for t in listed["tasks"]]
    assert subjects.index("bumped") < subjects.index("calm")


@pytest.mark.asyncio
async def test_inject_signal_rejects_missing_source():
    r = await tools.inject_signal(source="", bump=10)
    assert r["ok"] is False
    assert "source" in r["error"]


@pytest.mark.asyncio
async def test_inject_signal_rejects_non_int_bump():
    r = await tools.inject_signal(source="x", bump="not-an-int")  # type: ignore[arg-type]
    assert r["ok"] is False
    assert "integer" in r["error"]


# ---------- server module loads ----------

def test_server_module_imports():
    from triagemcp import server
    assert hasattr(server, "main")
    assert hasattr(server, "mcp")
    # Every @mcp.tool() function should be registered
    expected = {"list_tasks", "get_task", "why_task", "status",
                "add_task", "remove_task", "tick", "inject_signal"}
    declared = {name for name in dir(server) if name in expected}
    assert declared == expected
