# Build progress

> Resumable status snapshot. Paired with [01-phases.md](01-phases.md) (the plan) and [02-data-sources.md](02-data-sources.md) (the data provenance).

**Last updated:** 2026-04-25
**Tests:** 251 passing · **Lint:** clean · **Coverage:** 96% overall, 100% on `orbital.py` and `db.py`.

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
| 7 | Δv planner (Dijkstra graph, margin, stops, round-trip) | ✅ done | Shipped 7a–7e; design locked in [features/dv-planner.md](features/dv-planner.md); sub-phase ladder below |
| 8 | Web UI + prod1 deploy (FastAPI + systemd + nginx) | 🔄 in progress | 8a done — `/dv` page; 8b done — `/comms` page; 8c next (plans page) |
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
| 7d | *Re-scoped:* round-trip `--return` + aerobrake residual → 0% (community-chart convention). Stage-aware budget check dropped — per-edge output already supports in-game stage planning. | ✅ done | `ksp dv kerbin_surface mun_surface --return` = 10,300 raw / 6,900 aerobraked / 7,245 @ 5% |
| 7e | Dijkstra swap + double-credit fix on pre-baked capture edges (no chart-sourced shortcut edges exist) | ✅ done | Existing 201 tests stay green under Dijkstra; `kerbin_surface → duna_surface` aerobraked shifts 4,460 → 4,820 after capture-edge reclassification |

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

### Phase 7d completion log

Shipped with TDD throughout. 9 new tests; 192 → 201 total. Lint clean. Spec at [docs/superpowers/specs/2026-04-23-dv-planner-7d-design.md](superpowers/specs/2026-04-23-dv-planner-7d-design.md); executed per the plan at [docs/superpowers/plans/2026-04-23-dv-planner-7d.md](superpowers/plans/2026-04-23-dv-planner-7d.md).

- **Scope re-decision.** The original 7d (stage-aware Tsiolkovsky budget check) was dropped at the design step — per-edge output from 7a-c already supports in-game stage planning, and staging decisions live in KSP's VAB, not the planner. 7d was re-scoped to ship round-trip `--return` (deferred from 7c) plus an aerobrake-credit fix.
- **Residual → 0%.** `AEROBRAKE_RESIDUAL_PCT: 20.0 → 0.0`. Aerobrakable edges now credit 100% under `aerobrake=True`, matching community-chart convention (chart values treat aerobrake descents as free). The 5% trip margin is the safety buffer for correction burns and imperfect passes. Constant kept as a module-level lever for future tuning. 7c pins updated in lockstep (Duna aerobraked 4,822 → 4,460; Eve 6,096 → 4,480).
- **`plan_round_trip`.** Thin wrapper in `dv_map.py`: doubles the stops list (`[A, B]` → `[A, B, A]`, `[A, B, C]` → `[A, B, C, B, A]`) and delegates to `plan_trip`. `TripPlan` shape unchanged. Composes with `--via` so multi-stop round trips work for free.
- **CLI.** `ksp dv` gained `--return` (Typer boolean, default off). Python parameter is `return_` (keyword collision); flag syntax is `--return`. Dispatch: `planner = plan_round_trip if return_ else plan_trip`.
- **Renderer.** `_aero_cell` label derives from the module constant (`f"✓ −{100 - AEROBRAKE_RESIDUAL_PCT:g}%"`) so future residual tunes surface automatically. Stop annotation tightened from `— stop: <action> (<slug>) —` to `— stop: <action> —` (slug already visible in adjacent leg rows); avoids compressing the aero column on 80-col terminals under the wider round-trip table. Aero column pinned to `min_width=7` so `✓ −100%` renders in full.
- **Acceptance.** `ksp dv kerbin_surface mun_surface --return` → raw 10,300 · aerobraked 6,900 (−3,400 Kerbin return descent) · planned @ 5% 7,245. `--no-aerobrake` round-trip → 10,300 / 10,815. Multi-stop round-trip composes: `--via mun:orbit --return` yields 4-leg itinerary.

**Known follow-ups** (none block 7d):

- **Turnaround annotation action mismatch.** When the end Stop uses the default `action="orbit"` but its slug is a surface (e.g. `mun_surface`), the turnaround annotation reads `— stop: orbit —` and the title reads `mun_surface(orbit)`. Cosmetic; fix by inferring action from slug suffix at the renderer or at Stop construction.
- **Round-trip recomputes outbound edge lookups on the return leg.** Negligible at <200 graph nodes; could be cached if 7e's graph grows.

### Phase 7e completion log

Shipped with TDD throughout. 6 net new tests (4 Dijkstra synthetic + 3 parametrized capture-edge siblings − 1 renamed/merged); 201 → 207 total. Lint clean. Spec at [docs/superpowers/specs/2026-04-23-dv-planner-7e-design.md](superpowers/specs/2026-04-23-dv-planner-7e-design.md); executed per the plan at [docs/superpowers/plans/2026-04-23-dv-planner-7e.md](superpowers/plans/2026-04-23-dv-planner-7e.md).

- **Scope redirection.** The planned 7e acceptance gate (`ksp dv laythe_low_orbit vall_low_orbit picks the direct route`) was reframed after a research pass audited the canonical Cuky subway chart (Kowgan SVG + KSP forum thread + SpaceDock) and found **zero** published inter-moon or cross-branch edges. Per the "don't invent values" project rule, no new adjacencies were seeded. The phase still shipped the algorithm generalisation (Dijkstra) and the long-deferred double-credit fix.
- **Dijkstra over LCA walk.** `src/ksp_planner/dv_map.py::path_dv` now uses stdlib `heapq` for shortest-path search. Public API unchanged — `plan_trip` and `plan_round_trip` compose through untouched. `DvGraph.neighbors_of(slug)` added with an adjacency list built at init. Private `_ancestors` / `_lowest_common_ancestor` helpers removed. The existing 201 tests stay green as the tree-equivalence regression guard. One legacy test renamed (`test_missing_edge_raises` → `test_missing_edge_makes_node_unreachable`) because a missing edge now surfaces as `ValueError("no path")` rather than `KeyError` — Dijkstra treats reachability as a graph property, not a schema violation.
- **Double-credit fix.** Three pre-baked capture edges reclassified `can_aerobrake=False`: `eve_capture → eve_low_orbit` (80 m/s), `duna_capture → duna_low_orbit` (360 m/s), `kerbin_capture → kerbin_low_orbit` (0 m/s). The chart values already encode aerobrake, so crediting them again under `aerobrake=True` was double-counting. Arithmetic impact:
  - `kerbin_surface → duna_surface` aerobraked: **4,460 → 4,820 m/s** (only the 1,450 Duna descent now credits — Duna savings are correctly 1,450 m/s).
  - `kerbin_surface → eve_surface` aerobraked: **4,480 → 4,560 m/s** (only the 8,000 Eve descent credits — Eve savings are correctly 8,000 m/s).
  - `kerbin_surface → mun_surface --return` unchanged (path doesn't traverse these edges).
  - `kerbin_capture → kerbin_low_orbit` is 0 m/s, so arithmetic is unchanged; flag flipped for consistency with Eve/Duna siblings.
- **Acceptance.** Full suite green under Dijkstra (207 tests). Synthetic `test_dijkstra_picks_cheapest_edge_when_shortcut_exists` proves future shortcut edges will be honored (a graph with both tree path 30 and cross-branch shortcut 17 → Dijkstra picks 17). Unreachable-node, self-loop, and unknown-slug behaviour covered by three sibling tests.
- **Docs.** `docs/02-data-sources.md` now documents that the community chart has no inter-moon shortcut edges. `docs/features/dv-planner.md` §7e updated to reflect shipped scope.

### Phase 7 closed

Phase 7 ships as a complete Δv planner: tree + graph model, LCA-equivalent Dijkstra, five-leg plan formatting, per-stop actions (`land`/`orbit`/`flyby`), aerobrake-credit toggle, round-trip `--return`, and a margin multiplier. CLI surface is stable. Next up: **Phase 8 — Web UI + prod1 deploy (FastAPI + systemd + nginx)**. See [01-phases.md](01-phases.md) for the Phase 8 scope.

### Phase 8a completion log

Shipped with TDD throughout. 28 new tests; 207 → 235 total. Lint clean. Design from Claude Design session 2026-04-25 — "Engineer's Workbench" aesthetic adopted verbatim.

- **FastAPI skeleton.** `src/ksp_planner/web/app.py`: `serve()` reads `KSP_HOST`/`KSP_PORT`/`KSP_RELOAD` env vars and delegates to `uvicorn.run`; `StaticFiles` mount at `/static`; `GET /` redirects to `/dv`; Jinja2Templates at `web/templates/`; router for `routes.dv`.
- **Schema layer.** `src/ksp_planner/web/schemas.py`: `DvRequest` (Pydantic; `from_stop`, `to_stop`, `via_stops`, `round_trip`, `aerobrake`, `margin_pct`); `DvResponse.from_trip()` adapter (flat legs, slug-based) for JSON API; `_FormState` namespace preserving raw body+action values for template repopulation.
- **Deps.** `src/ksp_planner/web/deps.py`: `get_conn()` FastAPI dependency yields a read-only DB connection.
- **`/dv` route.** `src/ksp_planner/web/routes/dv.py`:
  - `_ctx(**extra)` builds base template context (`active_nav`, `version`, `bodies`, `subway_rows`).
  - `_subway_rows(conn)` groups dv_map nodes into a system × state grid for the sidebar.
  - `DV_BODIES` list of 17 bodies with slug/name/system for grouped `<select>` options.
  - `GET /dv` — accepts optional `from_body`, `from_action`, `to_body`, `to_action`, etc. as query params; computes trip when both endpoints present (shareable URLs).
  - `POST /dv` — converts body+action pairs to slugs via `resolve_stop`; handles `ValidationError`/`KeyError`/`ValueError` as 400 with flash; branches on `HX-Request` header (HTMX partial), `Accept: application/json` (JSON), or full-page Jinja render. `hx-push-url="true"` makes every POST result a shareable GET URL.
  - `GET /dv/stop-row` — returns a via-stop partial for HTMX injection (add/remove via stops).
- **Design tokens.** `static/css/theme.css` fully rewritten to "Engineer's Workbench" palette: `--bg #0a0e0f`, `--accent #6ee7b7` (mint), fonts Inter Tight / JetBrains Mono / Source Serif 4. Naming scheme `--bg`, `--accent`, `--surface`, `--line`, `--text-*` (matches the Claude Design session CSS vars exactly).
- **Component library.** `static/css/components.css` fully rewritten with workbench classes: `.wb-top`/`.wb-chip`/`.wb-grid-dv`; `.ksp-panel`/`.ksp-legs`/`.ksp-leg`; `.ksp-stop-row`/`.ksp-select`/`.ksp-toggle`/`.ksp-margin`; `.ksp-total` 3-box layout (primary mint, gold, muted ballistic); `.wb-subway-grid` sidebar.
- **Templates.**
  - `templates/base.html`: workbench shell with 2×2 brand mark, chip nav, meta strip.
  - `templates/macros/forms.html`: `body_select` macro with `<optgroup>` by system; `action_select` (land/orbit/flyby).
  - `templates/macros/panels.html`: `error_flash`, `empty_state`.
  - `templates/pages/dv.html`: full planner page — FROM/TO body+action selects, `#via-stops` HTMX target, controls row (add stop, round-trip toggle, aerobrake toggle, margin input, submit), `#result` HTMX target, subway sidebar.
  - `templates/partials/dv_result.html`: 3-box totals, flat leg list (Jinja2 `stops_by_idx.update()` trick for stop annotations between legs), CLI hint.
  - `templates/partials/stop_row.html`: via-stop row with VIA tag, body+action selects, remove button.
  - `templates/partials/error_flash.html`: thin error wrapper for HTMX swaps.
- **Tests.** `test_web_smoke.py` (7 tests: health, serve, htmx.js, theme.css tokens, components.css, root redirect, env-var forwarding); `test_web_schemas.py` (DvRequest/DvResponse schema tests); `test_web_dv.py` (10 tests: form rendered, body options, canonical numbers 10,300/6,900/7,245, HTMX partial, JSON response, stop-row partial, unknown body 400, negative margin 400, GET querystring canonical numbers, GET no-params empty state).
- **Form UX decision.** Form uses body + action selects (e.g. `body="kerbin"`, `action="land"`) rather than raw slugs — more user-friendly. Handler converts via `resolve_stop(graph, body, action)`. DvRequest schema keeps slugs internally (clean programmatic API). Shareable GET URLs use `from_body`/`from_action` params.

**Acceptance** (8a gate):

```
GET  /dv                               → Workbench page, empty state
POST /dv  from=kerbin/land to=mun/land --return  → raw 10,300 · aerobraked 6,900 · @5% 7,245
GET  /dv?from_body=kerbin&from_action=land&to_body=mun&to_action=land&round_trip=true
                                       → same numbers (shareable URL)
HX-Request: POST /dv                  → partial only, no chrome
Accept: application/json: POST /dv    → DvResponse JSON
```

### Phase 8b completion log

Shipped with TDD throughout. 16 new tests; 235 → 251 total. Lint clean. Spec at [docs/superpowers/specs/2026-04-25-comms-web-8b-design.md](superpowers/specs/2026-04-25-comms-web-8b-design.md); plan at [docs/superpowers/plans/2026-04-25-comms-web-8b.md](superpowers/plans/2026-04-25-comms-web-8b.md).

- **`resonant_deploy()`.** New pure function in `comms.py` — computes the retrograde parking orbit (period ratio `(N-1)/N`) for deploying N evenly-spaced satellites from a single launch. Kerbin 3-sat canonical: resonant altitude ≈ 479 km, period ratio 2/3.
- **Pydantic schemas.** `CommsRequest` validates the five inputs (body, n_sats ≥ 2, antenna, dsn_level 1–3, min_elev_deg 0–89). `CommsResponse.from_report()` adapts the `comm_network_report()` dict + `resonant_deploy()` dict to a typed response with all distances in km (SI internally, km at the edge).
- **`routes/comms.py`.** GET + POST `/comms` following the identical pattern as `/dv`: `_compute()` helper centralises DB resolution + calculator calls; POST branches on `HX-Request` / `Accept: application/json` headers; GET accepts full querystring for shareable URLs.
- **Templates.** `pages/comms.html` — two-column layout (form + sidebar); `partials/comms_result.html` — coverage indicator (green/red dot + margin), orbit totals, link-budget rows, gold resonant-deployment box, CLI hint. Sidebar has antenna range table + DSN level table, both loaded from DB.
- **Nav chip enabled.** `base.html` "Comm Net" chip changed from `<span class="is-disabled">` to `<a href="/comms">` with `is-active` when on that route.

### Phase 8c resume notes

**Goal:** `/plans` page — list + run saved plans from the web, equivalent to `ksp plan list` / `show` / `run`.

**Before starting:** brainstorm or write a plan for 8c before coding. The plans layer (`plans.py`) and DB are already complete from Phase 6; this is purely a web layer addition.

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
│   ├── dv_map.py                       Δv graph + Dijkstra path_dv + plan_trip + plan_round_trip + resolve_stop (Phase 7a–7e)
│   ├── formatting.py                   Rich tables, panels, fmt_dist, fmt_time, dv_trip_panel (with per-stop annotations)
│   ├── cli.py                          Typer app, entry point `ksp` (incl. `dv` with `--via body[:action]`)
│   └── web/                            FastAPI web layer (Phase 8a)
│       ├── app.py                      FastAPI app, serve(), redirect / → /dv
│       ├── deps.py                     get_conn() FastAPI dependency
│       ├── schemas.py                  DvRequest / DvResponse / CommsRequest / CommsResponse Pydantic models
│       ├── routes/dv.py                GET+POST /dv, GET /dv/stop-row
│       ├── routes/comms.py             GET+POST /comms
│       ├── templates/base.html         Workbench shell (chip nav, brand, meta)
│       ├── templates/pages/dv.html     Δv planner page
│       ├── templates/pages/comms.html  Comm network planner page
│       ├── templates/macros/           body_select, action_select, error_flash, empty_state
│       ├── templates/partials/         dv_result, comms_result, stop_row, error_flash HTMX partials
│       └── static/                     htmx.min.js, theme.css (tokens), components.css
└── tests/
    ├── conftest.py                     seed_db (session, RO), db (per-test RO), writable_db (per-test RW copy), client (TestClient)
    ├── test_smoke.py                   1 test
    ├── test_seed.py                    45 tests — body/antenna/DSN/hierarchy/SOI/oxygen
    ├── test_orbital.py                 18 tests — known values + hypothesis properties
    ├── test_comms.py                   16 tests — worked example + edge cases
    ├── test_plans.py                   13 tests — save/load/delete round-trip, update semantics, validation
    ├── test_dv_map.py                  56 tests — hand-built tree + Dijkstra synthetic graphs + load_dv_graph + Hohmann cross-check + resolver + 7b/7c/7d/7e acceptance
    ├── test_cli.py                     58 tests — all CLI subcommands incl. `plan {list,show,run,delete}` + `--save` + `dv` + `--via` + `--return`
    ├── test_web_smoke.py               7 tests — health, serve(), static assets, root redirect, env vars
    ├── test_web_schemas.py             DvRequest/DvResponse/CommsRequest/CommsResponse schema tests
    ├── test_web_dv.py                  10 tests — /dv GET/POST canonical numbers, HTMX partial, JSON, stop-row, 400 errors, shareable GET URL
    └── test_web_comms.py               9 tests — /comms GET/POST canonical numbers, HTMX partial, JSON, 400 errors, shareable GET URL
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
8. **Graph model for Phase 7 Δv planner** (seeded canonical chart values + flat 5% margin default). Shipped 7a as strict tree + LCA walk; 7e generalised to Dijkstra shortest-path so non-tree edges can be added without algorithm changes. `dv_map.py` is pure (no DB import); DB loader lives in `db.py`.
9. **Δv chart attribution** *(Phase 7a)*: Kerbin trunk between `kerbin_low_orbit` and `kerbol_orbit` is all 0 because LKO is the implicit baseline parking orbit for every "LKO → X" chart number. Ejection burns live on `(planet_transfer ↔ planet_capture)`; capture burns on `(planet_capture ↔ planet_LO)`. Trips from Kerbin match the chart exactly; trips originating elsewhere (e.g., Duna→Eve) are roughly correct but not chart-tuned — documented limitation, addressed in 7e graph upgrade.
10. **`flyby` resolves to `_transfer`, not `_capture`** *(Phase 7b)*: the design-doc mapping `flyby → _capture` was self-contradictory — `_capture` is the state *after* the capture burn, which by definition isn't a flyby. `_transfer` (approach trajectory, no burn to stay) is consistent across planets and moons. Flyby is pure tree itinerary, not a gravity-assist model; the community chart doesn't encode slingshot savings.
11. **`can_aerobrake` credits 100% of ballistic dv** *(Phase 7c → 7d → 7e)*: `AEROBRAKE_RESIDUAL_PCT = 0.0` (shipped 7c at 20%; flipped to 0% in 7d to match community-chart convention — chart values treat aerobrake descents as free). The 5% trip margin is the safety buffer for correction burns and imperfect passes. Constant kept as a module lever for future tuning. `total_raw` stays ballistic regardless of the flag — aerobrake only affects `total_aerobraked` and `total_aerobraked_planned`. *7e fix:* the three pre-baked capture edges (Eve 80, Duna 360, Kerbin 0) now carry `can_aerobrake=False` — their chart values already encode aerobrake, so crediting them again was double-counting. Only real aerobraking venues (Eve 8000 descent, Duna 1450 descent, Kerbin 3400 descent) keep the credit.
12. **Phase 7e scope redirection** *(2026-04-23)*: the original 7e plan called for inter-moon shortcut edges (Laythe↔Vall, Mun↔Minmus, etc.). Research confirmed the canonical community subway chart publishes zero such edges. Per the "don't invent values" project rule, no shortcuts were seeded. 7e shipped the algorithm generalisation (Dijkstra) and the double-credit fix instead. Future shortcut edges would need a second numerical source (e.g. KSPTOT-derived) with distinct provenance; the graph now accommodates them without another algorithm swap.

---

## Running the app

```bash
make install     # uv sync --group dev
make seed        # regenerate ksp.db from KSPTOT + inline antenna/DSN tables
make test        # pytest (251 tests)
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
uv run ksp dv kerbin_surface mun_surface --return                        # Phase 7d (round-trip)
uv run ksp dv kerbin_surface minmus_surface --via mun:orbit --return     # Phase 7d (multi-stop round-trip)

# Phase 8a — web server
uv run python -m ksp_planner.web.app   # starts uvicorn on localhost:8000
KSP_PORT=9090 KSP_RELOAD=1 uv run python -m ksp_planner.web.app
# then open http://localhost:8000/dv
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
