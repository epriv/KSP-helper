# CLAUDE.md

> Project conventions for the KSP Planner. Terse on purpose — detail lives in `docs/`.

## Start every session here

1. **[docs/PROGRESS.md](docs/PROGRESS.md)** — current status, where to resume, what's done vs next. This is the authoritative build log; read it before proposing work.
2. **[docs/01-phases.md](docs/01-phases.md)** — the phased plan with acceptance criteria.
3. **[docs/00-architecture.md](docs/00-architecture.md)** — module responsibilities and guiding principles.

## Claude tooling

The phase cadence assumes these plugins/skills are enabled in your Claude Code config. If a referenced slash-command isn't available in a fresh session, install via `/plugin` before resuming work.

- **`superpowers`** — `/brainstorm`, `/write-plan`, `/execute-plan`, plus the TDD / debugging / code-review meta-skills. Specs and plans land in `docs/superpowers/specs/` and `docs/superpowers/plans/`.
- **`/simplify`** — invoked at every phase-close per the ritual below.
- **`/review`** (or `/code-review:code-review`) — pre-merge sanity check.
- **`/frontend-design`** *(Phase 8 onward)* — web UI design iteration.
- **`context7` MCP** — preferred over web search for library docs (FastAPI, HTMX, Jinja, etc.).

## Authoritative data sources (not the docx)

`KSP_Planner_PlanningDoc.docx` has systematic transcription errors (bodies μ, antenna power, DSN Lvl 3). **Do not seed from it.** Canonical sources:

- **Bodies** — `seeds/data/bodies.ini` (KSPTOT verbatim)
- **Antennas** — inlined from Kerbalism `Patches-Antennas.cfg`. Units are **metres** (range), not watts.
- **DSN** — CustomBarnKit `default.cfg` (mirrors stock)
- **Δv chart** — Cuky's community chart (see Phase 7a completion log for attribution rules)

Full provenance + gotchas: [docs/02-data-sources.md](docs/02-data-sources.md).

## Architecture rules (do not violate)

- **Calculators are pure.** `orbital.py`, `comms.py`, `dv_map.py` take numbers in, return numbers out. No DB, no I/O, no printing. This is what keeps the same code usable from CLI + web.
- **DB is read-only at runtime.** Only `seeds/*` and `plans.py` write. Delete + re-seed should reproduce identical state.
- **CLI is a view.** It formats data; it does not compute. Same rule for Phase 8 web layer.
- **SI internally, friendly units at the edge.** Metres / seconds / m³/s² in code; km / hh:mm in Rich output.
- **Plans store inputs, not outputs.** Formula changes propagate on reload.

## Dependency policy

The docx "zero external deps" constraint **is dropped**. Pull the right tool at every layer (Typer, Rich, pytest, hypothesis, FastAPI, Pydantic). Prefer lightweight when equivalent — but stdlib isn't a rule.

## Workflow conventions

### Phase-boundary reset cadence

Multi-sub-phase work (6a/6b/6c, 7a/7b/7c/...) stops between sub-phases for a context reset. Each sub-phase ships with: RED tests → implementation → GREEN → update `docs/PROGRESS.md` → stop. **Don't auto-continue to the next sub-phase** — wait for confirmation. `docs/PROGRESS.md` is the handoff document; a fresh session should be able to resume from it alone.

### TDD

RED → GREEN → refactor, per function. Canonical values pinned against community data so a bad formula can't slip in. Detail: [docs/04-testing.md](docs/04-testing.md).

### Liberal subagent usage

Delegate research, exploration, and parallel analysis to subagents — one focused task each. Keep the main context for synthesis and code edits. For multi-step codebase searches or "find all usages" tasks, spawn an `Explore` agent rather than greping inline.

### Phase-close ritual

At the end of a sub-phase:

1. `make test` (full suite, currently 179 passing) + `make lint` must be green.
2. Run `/simplify` on changed files for reuse/quality review.
3. Update `docs/PROGRESS.md`: completion log for the sub-phase just shipped + resume notes for the next.
4. Commit with a scoped message (e.g. `feat(7b): --via stop resolution`). Log style: see recent commits.
5. Stop and announce the reset point.

## Common commands

```bash
make install          # uv sync --group dev
make seed             # regenerate ksp.db
make test             # pytest (full suite)
make test-cov         # with coverage
make lint             # ruff check
make fmt              # ruff format

uv run ksp <subcommand>   # CLI entry point; see docs/PROGRESS.md "Running the app"
```

## Gotchas

- **"antenna power" is metres, not watts.** Schema column is `range_m`. `comm_range(A, B) = sqrt(A × B)` metres.
- **Mun's sync orbit altitude exceeds its SOI.** Correct KSP physics; don't "fix" it.
- **Ruff `SIM300` is disabled** (false-positives on `actual == pytest.approx(expected)`).
- **`conftest.py` imports `seeds/` from project root** — `pyproject.toml` sets `pythonpath = ["src", "."]`.
- **Kerbol has NULL SOI and NULL orbit fields.** `parent_id IS NULL` identifies it.
- **`flyby` resolves to `_transfer`, not `_capture`** (7b). Flyby is tree itinerary only — no gravity-assist model.

## When you correct me

If I make the same mistake twice, append the rule to this file so the next session doesn't repeat it.
