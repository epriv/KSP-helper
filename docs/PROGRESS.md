# Build progress

> Resumable status snapshot. Paired with [01-phases.md](01-phases.md) (the plan) and [02-data-sources.md](02-data-sources.md) (the data provenance).

**Last updated:** 2026-04-21
**Tests:** 127 passing · **Lint:** clean · **Coverage:** 98% overall, 100% on `orbital.py` and `db.py`.

---

## Phases

| # | Phase | Status | Notes |
|---|-------|--------|-------|
| 0 | Scaffolding (pyproject, Makefile, src-layout, pytest, ruff) | ✅ done | `uv` toolchain; `ksp` entry point registered |
| 1 | Data foundation (schema, seed, db helpers, seed tests) | ✅ done | KSPTOT `bodies.ini` bundled at `seeds/data/bodies.ini`; 45 seed tests |
| 2 | Orbital mechanics core (`orbital.py`) | ✅ done | Pure functions + hypothesis property tests; 100% coverage |
| 3 | Comm network calculator (`comms.py`) | ✅ done | Canonical worked example is the integration test |
| 4 | CLI shell (Typer + Rich) | ✅ done | Subcommands: `body`, `bodies`, `antennas`, `dsn`, `comms`, `hohmann`, `twr`, `dv-budget`, `plan {list,show,run,delete}` |
| 5 | Hohmann / TWR / Tsiolkovsky | ✅ done | Kerbin→Duna matches canonical 1060 m/s ejection |
| 6 | Mission plan persistence | ✅ done | All four calculators support `--save NAME`; `ksp plan {list,show,run,delete}` covers round-trip |
| 7 | Δv planner (tree model, margin, stops) | ⬜ not started | Design locked in [features/dv-planner.md](features/dv-planner.md) |
| 8 | Web UI + prod1 deploy (FastAPI + systemd + nginx) | ⬜ not started | |
| 9 | Mod packs / KSP2 seeds | ⬜ not started | |

### Phase 6 completion log

Shipped in three passes, each with a reset point between:

- **6a — `plans.py` round-trip tests.** 13 tests in `tests/test_plans.py` (round-trip, duplicate-name updates in place, kind-change on update, `created_at` preserved / `updated_at` advances, `delete` returns `True`/`False`, unknown-name `KeyError`, invalid-kind / empty-name `ValueError`, `list_all` empty + sorted). Added `writable_db` fixture (`shutil.copy` of session `seed_db`) so mutating tests don't pollute shared state. Mutation-verified two tests genuinely catch regressions.
- **6b — `ksp plan` subcommand group.** `plan list` / `show` / `run` / `delete` via `plan_app = typer.Typer()` + `app.add_typer`. `run` dispatches on `kind` through `_PLAN_RUNNERS` dict. Split `_open` into `_require_db` + `_open` since list/show/delete don't need an open connection. Added `plans_table` + `plan_detail_panel` to `formatting.py`. 9 CLI tests written RED-first.
- **6c — `--save` on `twr` and `dv-budget`.** Extracted `_do_twr(conn, cfg)` / `_do_dv_budget(conn, cfg)` helpers; CLI commands delegate to them. `dv-budget` gained `--db` (opened lazily only when `--save` is set, so pure-math use still works without a DB). Both runners registered in `_PLAN_RUNNERS` so `ksp plan run` dispatches all four kinds. 5 RED→GREEN tests.

### Phase 7 resume point

Design locked in [features/dv-planner.md](features/dv-planner.md). The spec splits into five sub-phases (7a–7e) — each ships independently with its own acceptance test. **Recommend stopping between sub-phases** for context reset, same cadence as Phase 6.

**7a — first concrete next step:**

1. Add `dv_nodes` + `dv_edges` tables to `seeds/schema.sql` (columns already documented in [03-schema.md](03-schema.md); tables don't exist in `schema.sql` yet — confirm before editing).
2. Seed canonical chart values. Source: community Δv map. One row per reachable state (`kerbin_surface`, `mun_low_orbit`, `jool_transfer`, etc.); two `dv_edges` rows per adjacency (ascent and descent are asymmetric).
3. Create `src/ksp_planner/dv_map.py` with `path_dv(from_slug, to_slug)` (LCA tree-walk) and `plan_trip(stops, margin_pct=5.0)` (default 5%).
4. Cross-check test: compute Hohmann Δv via `orbital.py` and assert within 5% of each seeded inter-body transfer edge. Fails loudly on chart typos or orbital math bugs.
5. CLI: `ksp dv <from> <to> [--margin 5]`.

**Done when:** `ksp dv kerbin_surface mun_surface` matches the chart total within ±50 m/s.

TDD order: seed schema → write failing `path_dv` unit tests with a tiny hand-built tree fixture → implement tree walk → seed canonical values → add cross-check test → wire CLI.

---

## Repo map

```
KSP App/
├── README.md                           Project overview
├── Makefile                            make install|test|lint|seed|run
├── pyproject.toml                      uv / hatch project config, deps, ruff, pytest
├── KSP_Planner_PlanningDoc.docx        Original planning doc — historical only
├── docs/
│   ├── 00-architecture.md              Module layout + responsibilities
│   ├── 01-phases.md                    The plan (acceptance criteria per phase)
│   ├── 02-data-sources.md              KSPTOT/Kerbalism/CustomBarnKit provenance + cross-check findings
│   ├── 03-schema.md                    SQLite tables (bodies, orbits, antennas, dsn_levels, plans, + planned dv_nodes/dv_edges)
│   ├── 04-testing.md                   TDD approach + known-value canon
│   ├── PROGRESS.md                     (this file)
│   └── features/
│       ├── comm-network.md             Phase 3 spec + worked example
│       └── dv-planner.md               Phase 7 design (tree + LCA + 5% margin)
├── seeds/
│   ├── __init__.py
│   ├── schema.sql                      All tables (includes `plans` from Phase 6)
│   ├── seed_stock.py                   Parses bodies.ini, inlines antennas/DSN
│   └── data/
│       ├── README.md                   Attribution
│       └── bodies.ini                  KSPTOT verbatim (commit c2dd927)
├── src/ksp_planner/
│   ├── __init__.py                     __version__
│   ├── db.py                           connect() + get_body/list_bodies/get_antenna/get_dsn
│   ├── orbital.py                      period, vis-viva, escape, sync, hohmann, hill, Tsiolkovsky, TWR, interbody_hohmann
│   ├── comms.py                        comm_network_report + primitives
│   ├── plans.py                        save/load/list/delete
│   ├── formatting.py                   Rich tables, panels, fmt_dist, fmt_time
│   └── cli.py                          Typer app, entry point `ksp`
└── tests/
    ├── conftest.py                     seed_db (session, RO), db (per-test RO), writable_db (per-test RW copy)
    ├── test_smoke.py                   1 test
    ├── test_seed.py                    45 tests — body/antenna/DSN/hierarchy/SOI/oxygen
    ├── test_orbital.py                 18 tests — known values + hypothesis properties
    ├── test_comms.py                   16 tests — worked example + edge cases
    ├── test_plans.py                   13 tests — save/load/delete round-trip, update semantics, validation
    └── test_cli.py                     34 tests — all CLI subcommands incl. `plan {list,show,run,delete}` + `--save`
```

---

## Key decisions (non-obvious)

1. **μ, antenna, DSN values in the original `.docx` are wrong.** The memory file `project_data_sources.md` has the details. Authoritative sources: KSPTOT (bodies), Kerbalism patch comment table (antennas), CustomBarnKit `default.cfg` (DSN). Do not seed from the docx.
2. **"antenna power" is a misnomer** — KSP's `antennaPower` field is a **range in metres**, not watts. The schema column is `range_m`. `comm_range(P_A, P_B) = sqrt(P_A × P_B)` yields metres.
3. **SI throughout the code, user-facing km in the CLI.** All internal functions take metres, seconds, m³/s². Rich formatters convert for display.
4. **SOI is computed at seed time** from μ + SMA via the Laplace formula (a × (μ/μ_parent)^(2/5)). Matches published KSP values to ~0.5%.
5. **Kerbol has NULL SOI, NULL orbit fields.** `parent_id IS NULL` is how we identify it. DB test `test_kerbol_has_no_orbit_or_soi` pins this.
6. **Plans store inputs, not outputs** so formula changes propagate when a plan is reloaded and re-run.
7. **Stdlib-only constraint from the docx is dropped** — dev and web deps are fine (memory: `project_deps_policy.md`).
8. **Tree model for Phase 7 Δv planner** (seeded canonical chart values + flat 5% margin default). Graph upgrade is Phase 7e.

---

## Running the app

```bash
make install     # uv sync --group dev
make seed        # regenerate ksp.db from KSPTOT + inline antenna/DSN tables
make test        # pytest (all 127 tests)
make lint        # ruff check

uv run ksp body kerbin
uv run ksp bodies --type moon
uv run ksp antennas
uv run ksp comms kerbin --sats 3 --antenna "RA-15 Relay Antenna" --dsn 2
uv run ksp hohmann kerbin duna
uv run ksp twr --thrust 200000 --mass 10000
uv run ksp dv-budget --isp 345 --wet 10000 --dry 5000 --thrust 200000
uv run ksp comms kerbin --save my-kerbin-relay          # Phase 6
uv run ksp twr --thrust 200000 --mass 10000 --save liftoff
uv run ksp dv-budget --isp 345 --wet 10000 --dry 5000 --thrust 200000 --save stage-1
uv run ksp plan list
uv run ksp plan show my-kerbin-relay
uv run ksp plan run my-kerbin-relay
uv run ksp plan delete my-kerbin-relay
```

---

## Known gotchas

- **Mun's sync orbit altitude exceeds its SOI.** This is correct KSP physics (Mun rotates very slowly). `ksp body mun` correctly reports it.
- **Typer `--db` is per-command.** Every CLI command now accepts `--db` (since `dv-budget` picked it up in Phase 6c to support `--save`). `dv-budget` only opens the DB when `--save` is given — pure-math invocations still work without a seeded DB.
- **`conftest.py` imports `seeds`** from the project root. `pyproject.toml` has `pythonpath = ["src", "."]` to make this work under pytest.
- **KSPTOT's `[Sun]` section** maps to display name `Kerbol` (see `KSPTOT_NAME_MAP` in `seeds/seed_stock.py`).
- **Ruff `SIM300` (Yoda conditions) is disabled globally** — false-positives on the `actual == pytest.approx(expected)` idiom.

---

## Memory files (persist across sessions)

- `project_deps_policy.md` — external deps are fine at every layer
- `project_data_sources.md` — KSPTOT / Kerbalism / CustomBarnKit as canonical sources
