# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Two read tools mirroring Triage v0.11's CLI surface: `doctor` (env
  diagnostics — version, python, locale + winning source signal, store path,
  drift count) and `lang_check` (locale-catalog audit against the English
  baseline). (#1)
- CI now lints, type-checks, and audits dependencies on every push/PR, on
  Python 3.11 and 3.12, in both GitHub Actions and Woodpecker: `ruff check`
  (E, F, W, B, I, UP), `mypy`, and `pip-audit`. `pip` is upgraded first so
  `pip-audit` doesn't trip on stale advisories, and the `triage.*` import is
  marked `ignore_missing_imports` because the sibling package ships no
  `py.typed` marker. The mypy bar matches the KaliMCP sibling (default, not
  strict): this is a thin FastMCP shim, so strict mode would mostly flag
  decorator/`Any`-generics noise rather than real bugs.

### Fixed

- `datetime.now(timezone.utc)` modernized to `datetime.now(UTC)` (ruff UP017;
  `datetime.UTC` requires the Python 3.11 floor the package already declares).
- Dropped two unused local bindings in the test suite (ruff F841).

### Changed

- Dev dependencies now include `ruff>=0.6`, `mypy>=1.9`, and
  `pip-audit>=2.10.0` so the CI bar reproduces locally.

## [0.1.0] - 2026-05-16

Initial release. Wraps [Triage](https://github.com/CryptoJones/Triage), the
meta-scheduler, as MCP tools an agent can call directly — importing the
`triage` package in-process rather than shelling out to its CLI, so results
come back as typed structures (full rule-contribution arrays), not parsed text.

### Added

- Eight tools over stdio: `list_tasks`, `get_task`, `why_task`, `status`
  (read) and `add_task`, `remove_task`, `tick`, `inject_signal` (write). Each
  maps to a method already on `triage` and returns a structured
  `{ok, result|error}` dict.
- Store resolution honors `TRIAGEMCP_HOME` → `TRIAGE_HOME` → Triage's default
  `~/.triage`, so an agent can run against its own task queue or share the
  operator's.
- Matching pytest coverage for every tool.
