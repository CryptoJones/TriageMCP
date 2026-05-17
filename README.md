<div align="center">

```
╔══════════════════════════════════════════════════════════════╗
║                                                              ║
║                T  R  I  A  G  E  M  C  P                     ║
║                                                              ║
║    expose Triage's priority queue as MCP tools for agents    ║
║                                                              ║
╚══════════════════════════════════════════════════════════════╝
```

**An MCP server that turns
[Triage](https://github.com/CryptoJones/Triage) into a set of tools an
AI agent can call directly.** Add tasks, recompute priorities, explain
why a task ranks where it does — all from inside a Claude Code (or
any MCP-compatible) session.

[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg?logo=apache)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![MCP](https://img.shields.io/badge/MCP-server-D97757?logo=anthropic&logoColor=white)](https://modelcontextprotocol.io/)
[![Triage](https://img.shields.io/badge/wraps-CryptoJones%2FTriage-4f46e5)](https://github.com/CryptoJones/Triage)
[![Codeberg](https://img.shields.io/badge/Codeberg-CryptoJones%2FTriageMCP-2185D0?logo=codeberg&logoColor=white)](https://codeberg.org/CryptoJones/TriageMCP)
[![GitHub](https://img.shields.io/badge/GitHub-CryptoJones%2FTriageMCP-181717?logo=github&logoColor=white)](https://github.com/CryptoJones/TriageMCP)

</div>

> Mirrored on both [GitHub](https://github.com/CryptoJones/TriageMCP)
> and [Codeberg](https://codeberg.org/CryptoJones/TriageMCP). Issues
> on either forge are welcome; commits land on both.

---

## What is Triage?

[**Triage**](https://github.com/CryptoJones/Triage) is a meta-scheduler:
a self-aware priority queue. Signals push facts about the world; rules
turn facts into priority deltas; the queue reorders itself on every
tick. The human sets the goals — Triage decides the order, and tells
you exactly why.

It already has a clean Python API + a CLI (`triage list`, `triage why`,
`triage tick`). **TriageMCP is the bridge that makes that API
addressable from inside an agent's tool-use loop.**

If you're new to Triage, read its
[README](https://github.com/CryptoJones/Triage/blob/main/README.md)
first — TriageMCP is a thin wrapper, not a re-implementation.

---

## Tools exposed

Every tool maps to a method already available on `triage` directly,
returning structured data (not stringified CLI output) so the agent
can reason about it:

| MCP tool | Read/Write | Mirrors CLI | Returns |
|----------|------------|-------------|---------|
| `list_tasks` | read | `triage list` | priority-ordered task list with full rule contributions |
| `get_task` | read | `triage show` | one task's full record |
| `why_task` | read | `triage why` | rule-by-rule contribution deltas explaining a task's priority |
| `status` | read | `triage status` | top-3 + tag counts + active-signal counts |
| `add_task` | write | `triage add` | the new task + its assigned id |
| `remove_task` | write | `triage rm` | confirms removal |
| `tick` | write | `triage tick` | recomputes priorities; returns new top-3 + signal counts |
| `inject_signal` | write | `triage signal manual` | writes a manual signal that `rule_manual_bump` picks up |
| `doctor` | read | `triage doctor` | env diagnostics dict (version, python, locale + source signal, store path, drift count) |
| `lang_check` | read | `triage lang --check` | `{clean, drift_count, report}` — empty `report` means all locales match the English baseline |

The agent works on the same `~/.triage` store the
[Triage CLI](https://github.com/CryptoJones/Triage) does — so anything
you add via `triage add` from the terminal is visible to the agent on
the next call, and vice versa.

---

## Install

```bash
# 1. Install Triage (TriageMCP imports from it directly — no subprocess shell-out)
pip install git+https://github.com/CryptoJones/Triage.git
# or, for an editable clone:
git clone https://github.com/CryptoJones/Triage.git && pip install -e ./Triage

# 2. Install TriageMCP
git clone https://github.com/CryptoJones/TriageMCP.git
cd TriageMCP
pip install -e .
```

Once a Triage release is on PyPI, this collapses to a single
`pip install triagemcp`.

### Wire into Claude Code

Edit (or create) `~/.claude/mcp.json`:

```json
{
  "mcpServers": {
    "triagemcp": {
      "command": "triagemcp"
    }
  }
}
```

Restart Claude Code. The eight tools above will be available to the
agent. Ask it to **"what should I do next?"** and it can call
`list_tasks` + `why_task` to give you a real answer.

### Override the store location

By default TriageMCP uses Triage's own resolution: `$TRIAGE_HOME` →
`~/.triage`. To point an agent at a different store (e.g. one task
queue per agent), set `TRIAGEMCP_HOME`:

```json
{
  "mcpServers": {
    "triagemcp": {
      "command": "triagemcp",
      "env": { "TRIAGEMCP_HOME": "/home/you/.triage-agent-A" }
    }
  }
}
```

---

## Why direct import, not subprocess

Some MCP servers (including [KaliMCP](https://github.com/CryptoJones/KaliMCP),
its security-tooling sibling) shell out to wrapped binaries. TriageMCP
does **not**:

- **Speed** — no fork/exec overhead per tool call.
- **Fidelity** — results come back as typed structures with full rule
  contribution arrays, not text that the agent (or this server) has
  to parse.
- **Determinism** — both this server and the `triage` CLI use the same
  scheduler module, so what the agent sees is exactly what the CLI
  would compute, no more and no less.

The cost: TriageMCP requires Triage as a Python dependency. That's
why the install step has two commands. Once a PyPI release of Triage
exists this collapses to one.

---

## Sample agent transcript

```
USER: I just merged the linter fix PR. What's next?

AGENT: [calls tick()] OK, recomputed priorities.
       [calls list_tasks(limit=5)] Your top 5 are:
         1. Fix the auth bug             [120]
         2. Rotate the staging cert       [85]
         3. Reply to legal about contract [50]
         4. Open release PR               [12]
         5. Update README badges           [3]

       [calls why_task(top.id)] Auth bug is at 120 because:
         + base_score: +10
         + manual_bump: +100 (from runpodboss signal — pod is idle)
         + deadline_decay: +10 (deadline in 3 days)
```

Every priority is explainable end-to-end via the rule-contribution
arrays the tools return. No black box.

---

## Status

| Version | Feature | Status |
|---------|---------|--------|
| v0.1 | eight tools (list / get / why / status / add / remove / tick / inject_signal); direct in-process import of `triage`; matching tests for each | shipped |
| v0.2 | two new read tools mirroring Triage v0.11's CLI surface: `doctor` (env diagnostics) + `lang_check` (locale-catalog audit) | shipped |
| v0.2 | streaming watch via `triage watch` mode once Triage ships that (v0.10 milestone) | planned |
| v0.3 | per-task `update_task` partial-edit tool (description / base_score / tags only — id stays stable) | planned |
| v0.4 | Dockerfile parity with [KaliMCP](https://github.com/CryptoJones/KaliMCP) so the server can run in a sealed image | planned |

---

## Related projects

- [**Triage**](https://github.com/CryptoJones/Triage) — the meta-scheduler this server wraps.
- [**claude_skill-Triage**](https://github.com/CryptoJones/claude_skill-Triage) — Claude Code skill repository: `TaskPriorityReorder` (manual override) + forthcoming `triage` skill (signal-driven recommender).
- [**KaliMCP**](https://github.com/CryptoJones/KaliMCP) — sibling MCP server; same authorial conventions, different tool surface (Kali security tools).
- [**RunPodBoss**](https://github.com/CryptoJones/RunPodBoss) — RunPod credit guardrail with a documented integration recipe into Triage via `extra_notify_command`.

---

## License

Apache 2.0. See [LICENSE](LICENSE).

Proudly Made in Nebraska. Go Big Red! 🌽 https://xkcd.com/2347/
