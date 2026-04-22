# Build progress

> Resumable status snapshot. Paired with [01-phases.md](01-phases.md) (the plan) and [02-data-sources.md](02-data-sources.md) (the data provenance).

**Last updated:** 2026-04-22
**Tests:** 192 passing · **Lint:** clean · **Coverage:** 98% overall, 100% on `orbital.py` and `db.py`.

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
| 7 | Δv planner (tree model, margin, stops) | 🟡 in progress (7a ✅; 7b ✅; 7c ✅; 7d next) | Design locked in [features/dv-planner.md](features/dv-planner.md); sub-phase ladder below |
| 8 | Web UI + prod1 deploy (FastAPI + systemd + nginx) | ⬜ not started | |
| 9 | Mod packs / KSP2 seeds | ⬜ not started | |

### Phase 6 completion log

Shipped in three passes, each with a reset point between:

- **6a — `plans.py` round-trip tests.** 13 tests in `tests/test_plans.py` (round-trip, duplicate-name updates in place, kind-change on update, `created_at` preserved / `updated_at` advances, `delete` returns `True`/`False`, unknown-name `KeyError`, invalid-kind / empty-name `ValueError`, `list_all` empty + sorted). Added `writable_db` fixture (`shutil.copy` of session `seed_db`) so mutating tests don't pollute shared state. Mutation-verified two tests genuinely catch regressions.
- **6b — `ksp plan` subcommand group.** `plan list` / `show` / `run` / `delete` via `plan_app = typer.Typer()` + `app.add_typer`. `run` dispatches on `kind` through `_PLAN_RUNNERS` dict. Split `_open` into `_require_db` + `_open` since list/show/delete don't need an open connection. Added `plans_table` + `plan_detail_panel` to `formatting.py`. 9 CLI tests written RED-first.
- **6c — `--save` on `twr` and `dv-budget`.** Extracted `_do_twr(conn, cfg)` / `_do_dv_budget(conn, cfg)` helpers; CLI commands delegate to them. `dv-budget` gained `--db` (opened lazily only when `--save` is set, so pure-math use still works without a DB). Both runners registered in `_PLAN_RUNNERS` so `ksp plan run` dispatches all four kinds. 5 RED→GREEN tests.

### Phase 7 breakdown

Design locked in [features/dv-planner.md](features/dv-planner.md). The spec splits into five sub-phases — each ships independently with its own acceptance test. Same cadence as Phase 6: **stop between sub-phases for context reset**, with this file as the handoff document.

| Sub-phase | Scope | Status | Acceptance test |
|-----------|-------|--------|-----------------|
| 7a | Total Δv, two points: schema + seed + `path_dv` (LCA tree walk) + `plan_trip` (flat 5% margin) + `ksp dv <from> <to>` CLI + Hohmann cross-check | ✅ done | `ksp dv kerbin_surface mun_surface` = 5,150 m/s raw / 5,408 m/s @ 5% margin (chart 5,150 ✅) |
| 7b | Intermediate stops with per-stop `action` (`land` / `orbit` / `flyby`); `--via body[:action]` repeatable on CLI | ✅ done | `kerbin_surface → minmus (orbit) → mun_surface` = 7,330 m/s raw / 7,696 @ 5% |
| 7c | Aerobraking credit on one-way trips: `aerobrake` kwarg on `plan_trip`, `--no-aerobrake` CLI flag, tri-state aero column + dual totals. Round-trip `--return` deferred. | ✅ done | `ksp dv kerbin_surface duna_surface` shows raw 6,270 · with aerobrake 4,822 (−1,448 m/s Duna savings) |
| 7d | Stage-aware budget check: ship as `[(wet_kg, dry_kg, isp_s), …]`; verify Δv coverage; report which leg runs dry. Shares Tsiolkovsky module with Phase 5 | ⬜ not started | Canned Mun lander stage sheet confirms reach-and-return |
| 7e | Optional graph upgrade: Dijkstra + inter-moon edges; public API unchanged | ⬜ not started | `ksp dv laythe_low_orbit vall_low_orbit` picks the direct route |

**Reset points:** between every sub-phase. After 7a passes, this file gets a 7a completion log + 7b resume notes, then we stop.

### Phase 7a completion log

Shipped end-to-end with TDD throughout. 28 new tests; 127 → 155 total. Lint clean.

- **Schema.** `seeds/schema.sql` gained `dv_nodes` (with self-FK `parent_slug`, CHECK on `state`) and `dv_edges` (UNIQUE on `(from_slug, to_slug)`) plus three covering indices. Existing 127 tests stayed green after re-seed.
- **Pure path-finding.** `src/ksp_planner/dv_map.py`: `DvNode`/`Edge`/`Stop`/`TripPlan` dataclasses + `DvGraph` (O(1) node + edge lookup) + `path_dv` (LCA walk) + `plan_trip` (flat margin, default 5%). Zero DB import — keeps the math pure and testable. 13 hand-built tree tests cover identity, same-branch up/down, cross-LCA shallow + deep, unknown slug, missing edge; 5 trip-plan tests cover two/three stops + custom/zero margin + single-stop validation.
- **Canonical seed.** `seeds/seed_stock.py` gained `DV_NODES` (58 nodes for Kerbol + 16 bodies, full tree per design doc art) and `DV_ADJACENCIES` (62 adjacencies → 124 directed `dv_edges` rows). Source: Cuky's community Δv map. Attribution rule: Kerbin trunk (`kerbol_orbit ↔ kerbin_LO`) all zero since LKO is the chart's baseline; ejection burns live on `(planet_transfer ↔ planet_capture)`, capture burns on `(planet_capture ↔ planet_LO)`.
- **DB loader.** `db.py` gained `load_dv_graph(conn) → DvGraph`. Three integration tests: round-trip load, acceptance probe (kerbin_surface→mun_surface), Eve aerobrake assertion.
- **Hohmann cross-check.** 5-planet parametrised test compares the seeded LKO→planet_LO total against `orbital.interbody_hohmann().dv_total` within 30%. Tolerance is loose because the chart bakes Oberth/inclination/aerobrake corrections that pure circular-coplanar Hohmann doesn't model — still trips loudly on actual typos (10× errors push values 2-10× off). Observed spread: Jool ±2.4%, Duna -15%, Dres -16%, Moho +18%, Eeloo -23%. Eve excluded (-52%, aerobrake-dominated).
- **CLI.** `ksp dv <from> <to> [--margin 5]` added to `cli.py`; `dv_trip_panel` added to `formatting.py` (per-leg arrow table + aero flag column + raw + margin-padded totals). 7 CLI tests written RED→GREEN.

**Acceptance** (the 7a gate):

```
$ uv run ksp dv kerbin_surface mun_surface
  kerbin_surface → kerbin_low_orbit  3,400 m/s
  kerbin_low_orbit → mun_transfer      860 m/s
  mun_transfer → mun_low_orbit         310 m/s
  mun_low_orbit → mun_surface          580 m/s
  Raw total              5,150 m/s
  Planned (+5% margin)   5,408 m/s   ← target was ±50 m/s of chart 5,150 ✅
```

Other sanity probes (all match chart exactly): `kerbin_surface→minmus_surface` 4,670 · `kerbin_surface→duna_low_orbit` 4,820 · `kerbin_surface→duna_surface` 6,270 · `kerbin_low_orbit→laythe_surface` 9,000 · `mun_surface→minmus_surface` 3,020 (cross-LCA at kerbin_low_orbit).

### Phase 7b completion log

Shipped with TDD throughout. 24 new tests; 155 → 179 total. Lint clean. Spec at [docs/superpowers/specs/2026-04-21-dv-planner-7b-design.md](superpowers/specs/2026-04-21-dv-planner-7b-design.md); executed per the plan at [docs/superpowers/plans/2026-04-21-dv-planner-7b.md](superpowers/plans/2026-04-21-dv-planner-7b.md).

- **Action resolver.** `src/ksp_planner/dv_map.py` gained `ACTION_SUFFIXES = {land→_surface, orbit→_low_orbit, flyby→_transfer}` and `resolve_stop(graph, body, action) → Stop`. Pure function, no DB import. Flyby resolves to `_transfer` for all bodies (revised from the feature doc's `_capture` mapping, which was contradictory — `_capture` is the state *after* the capture burn).
- **TripPlan.stops.** Added `stops: list[Stop]` field to `TripPlan`; `plan_trip` threads the input list through. Existing tests updated to assert the field round-trips.
- **CLI.** `dv` command gained `--via body[:action]` (repeatable). `_parse_via` helper splits on `:`, defaults action to `orbit` when omitted. Resolver errors (unknown action/body, malformed syntax) exit 1 with red messages — same pattern as existing `dv_budget` error paths.
- **Renderer.** `dv_trip_panel` walks `trip.stops[1:-1]` and emits a dim-italic annotation row between legs at each intermediate stop, in the leftmost column as `— stop: <action> (<slug>) —`. Title uses `body(action)` form (e.g. `minmus(orbit)`) when vias are present. Two-point trips render identically to 7a; aero column clips slightly on narrow terminals under `--via` due to the expanded From-column min-width — acceptable for 7b since aero handling is 7c territory.
- **Acceptance.** `kerbin_surface → minmus (orbit) → mun_surface` = 7,330 raw / 7,696 @ 5% (traced by hand through the seed: leg1 3400 + 930 + 160 = 4,490; leg2 160 + 930 + 860 + 310 + 580 = 2,840). 8-way parametric resolver check across minmus/duna/jool/mun covers all three actions.

**Known follow-ups** (none block 7b acceptance):

- `TripPlan.stops` and `TripPlan.legs` are declared as `list[...]` on a frozen dataclass — mutation-through-reference still works. Consistent with pre-existing `legs` field; revisit as a broader refactor to `tuple[...]` if mutation ever actually bites.
- `dv_trip_panel` inflates the From column to fit the annotation text on a single line, which clips the "aero" header on 80-char terminals when `--via` is used. Could be addressed with a separate-tables + Rule layout in 7c when aero becomes user-facing.

### Phase 7c completion log

Shipped with TDD throughout. 13 new tests; 179 → 192 total. Lint clean. Spec at [docs/superpowers/specs/2026-04-22-dv-planner-7c-design.md](superpowers/specs/2026-04-22-dv-planner-7c-design.md); executed per the plan at [docs/superpowers/plans/2026-04-22-dv-planner-7c.md](superpowers/plans/2026-04-22-dv-planner-7c.md).

- **Scope decision.** Dropped round-trip `--return` from 7c at the design step. Aerobrake on one-way trips ships as 7c; round-trip + return-leg aerobrake is deferred to a later sub-phase (`plan_round_trip` helper per feature-doc §API).
- **Core.** `dv_map.py` gained `AEROBRAKE_RESIDUAL_PCT = 20.0`. `TripPlan` grew three fields: `total_aerobraked`, `aerobrake`, `total_aerobraked_planned`. `plan_trip(..., aerobrake=True)` computes `total_aerobraked` by summing each edge's contribution — `can_aerobrake=True` edges contribute 20% of their `dv_m_s`, others contribute full. `total_raw` never changes with the flag — it's always the ballistic sum.
- **CLI.** `ksp dv` gained `--aerobrake/--no-aerobrake` (Typer boolean, default on). No change to `--via` / `--margin` behavior.
- **Renderer.** `dv_trip_panel` aero column is tri-state: `✓ −80%` when credited, `✓ off` when aerobrake is disabled, blank otherwise. Totals block adds a `With aerobrake` row with savings delta when `trip.aerobrake` is True, even if savings are zero (consistent output shape).
- **Acceptance.** `kerbin_surface → duna_surface` shows raw 6,270, aerobraked 4,822 (−1,448 Duna savings), planned 5,063 @ 5%. `kerbin→eve_surface` shows raw 12,560, aerobraked 6,096 (−6,464). `kerbin→mun_surface` is correctly a no-op (no creditable edges on the path).

**Known limitations** (documented as follow-ups, not blocking 7c):

- **Double-credit on pre-baked capture edges.** `eve_capture→eve_low_orbit` (80), `duna_capture→duna_low_orbit` (360), and `kerbin_capture→kerbin_low_orbit` (0) store chart values that already reflect aerobraking; crediting them again over-discounts by ≤ ~350 m/s across a full Eve+Duna+Kerbin outbound. Dominant savings (Kerbin/Duna/Eve/Laythe descents) are modeled correctly. Fix deferred to 7e when the graph model is revisited.
- **Configurable residual.** 20% is a module constant (`AEROBRAKE_RESIDUAL_PCT`). Can be promoted to a CLI flag (`--aerobrake-residual`) later if real usage shows the value should vary.
- **Round-trip / return-leg aerobrake** deferred. API sketched in feature doc: `plan_round_trip(stops, margin_pct, aerobrake)`.

### 7d resume point — Stage-aware budget check

Spec lives in [features/dv-planner.md §7d](features/dv-planner.md#7d--stage-aware-budget-check). Inputs: staged ship as `list[(wet_kg, dry_kg, isp_s)]` + target trip. Use Tsiolkovsky (already in `orbital.py`) to compute available Δv per stage; verify coverage against planned legs; report which leg runs dry. Pairs with the Phase 5 TWR/Tsiolkovsky calculator — shared module.

**First concrete next step** for a fresh session:

1. Decide the data model: a new `Stage` dataclass in `dv_map.py` (or a new `budget.py` module), `list[Stage]` as the ship.
2. RED: `test_budget_covers_kerbin_to_mun_round_trip` — canned 3-stage Mun lander (ascent + transfer + lander) against a kerbin_surface → mun_surface → kerbin_surface trip; assert the budget report confirms coverage.
3. Decide the budget report shape. Suggested: `BudgetReport(legs: list[LegBudget], ok: bool, runs_dry_on: int | None)` where `LegBudget` tracks `required_dv`, `available_dv`, `remaining_after`.
4. Wire stage accounting: which stage serves which leg? Simplest v1 is "consume stages in order; a stage is used until exhausted, then drop to next". Per-leg stage assignment is a v2 concern.
5. CLI: `ksp dv-check <from> <to> --stage 9000,3000,345 --stage ... [--via ...] [--margin ...] [--no-aerobrake]`. Repeatable `--stage` with `wet,dry,isp` triple.
6. Acceptance gate: feature-doc §7d — canned Mun lander sheet confirms reach-and-return.

Files likely to change: `src/ksp_planner/dv_map.py` (or a new `budget.py`), `src/ksp_planner/cli.py`, plus tests.

Round-trip `--return` and `plan_round_trip` are still deferred — consider threading them in alongside 7d if the Mun-lander acceptance test needs round-trip semantics, otherwise defer further.

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
│   ├── db.py                           connect() + get_body/list_bodies/get_antenna/get_dsn + load_dv_graph (Phase 7a)
│   ├── orbital.py                      period, vis-viva, escape, sync, hohmann, hill, Tsiolkovsky, TWR, interbody_hohmann
│   ├── comms.py                        comm_network_report + primitives
│   ├── plans.py                        save/load/list/delete
│   ├── dv_map.py                       Δv tree + LCA path_dv + plan_trip + resolve_stop (Phase 7a/7b)
│   ├── formatting.py                   Rich tables, panels, fmt_dist, fmt_time, dv_trip_panel (with per-stop annotations)
│   └── cli.py                          Typer app, entry point `ksp` (incl. `dv` with `--via body[:action]`)
└── tests/
    ├── conftest.py                     seed_db (session, RO), db (per-test RO), writable_db (per-test RW copy)
    ├── test_smoke.py                   1 test
    ├── test_seed.py                    45 tests — body/antenna/DSN/hierarchy/SOI/oxygen
    ├── test_orbital.py                 18 tests — known values + hypothesis properties
    ├── test_comms.py                   16 tests — worked example + edge cases
    ├── test_plans.py                   13 tests — save/load/delete round-trip, update semantics, validation
    ├── test_dv_map.py                  36 tests — hand-built tree LCA + load_dv_graph + Hohmann cross-check + resolver + 7b acceptance
    └── test_cli.py                     50 tests — all CLI subcommands incl. `plan {list,show,run,delete}` + `--save` + `dv` + `--via`
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
8. **Tree model for Phase 7 Δv planner** (seeded canonical chart values + flat 5% margin default). Graph upgrade is Phase 7e. *7a shipped 2026-04-21 — `dv_map.py` is pure (no DB import), DB loader lives in `db.py`.*
9. **Δv chart attribution** *(Phase 7a)*: Kerbin trunk between `kerbin_low_orbit` and `kerbol_orbit` is all 0 because LKO is the implicit baseline parking orbit for every "LKO → X" chart number. Ejection burns live on `(planet_transfer ↔ planet_capture)`; capture burns on `(planet_capture ↔ planet_LO)`. Trips from Kerbin match the chart exactly; trips originating elsewhere (e.g., Duna→Eve) are roughly correct but not chart-tuned — documented limitation, addressed in 7e graph upgrade.
10. **`flyby` resolves to `_transfer`, not `_capture`** *(Phase 7b)*: the design-doc mapping `flyby → _capture` was self-contradictory — `_capture` is the state *after* the capture burn, which by definition isn't a flyby. `_transfer` (approach trajectory, no burn to stay) is consistent across planets and moons. Flyby is pure tree itinerary, not a gravity-assist model; the community chart doesn't encode slingshot savings.
11. **`can_aerobrake` credits 80% of ballistic dv** *(Phase 7c)*: `AEROBRAKE_RESIDUAL_PCT = 20.0` leaves a 20% residual rather than zeroing, covering correction burns, safety margin, and imperfect atmospheric passes. `total_raw` stays ballistic regardless of the flag — aerobrake only affects `total_aerobraked` and `total_aerobraked_planned`. Known quirk: the three pre-baked capture edges (Eve 80, Duna 360, Kerbin 0) are double-credited; error bounded to ≤ ~350 m/s; fix deferred to 7e.

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
uv run ksp dv kerbin_surface mun_surface                # Phase 7a
uv run ksp dv kerbin_surface duna_surface --margin 10
uv run ksp dv kerbin_surface mun_surface --via minmus:orbit              # Phase 7b
uv run ksp dv kerbin_surface jool_low_orbit --via duna:flyby --via eve:flyby
uv run ksp dv kerbin_surface duna_surface                                # Phase 7c (default: aerobrake on)
uv run ksp dv kerbin_surface duna_surface --no-aerobrake                 # Phase 7c (disable credit)
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
- `feedback_phase_reset_cadence.md` — stop between sub-phases; PROGRESS.md is the handoff doc
- `feedback_subagent_workflow.md` — delegate research/exploration to subagents, one task each

Project-level conventions are in [`CLAUDE.md`](../CLAUDE.md) at the repo root.
