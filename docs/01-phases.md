# Build phases

Each phase has a clear **deliverable** and **done-when** criteria. Phases build on each other — do not start phase N+1 until phase N is green.

TDD applies from Phase 0. Every calculator function has a test before the implementation.

---

## Phase 0 — Scaffolding

**Deliverable:** A repo you can `git clone && pytest` against.

- `pyproject.toml` with deps (Typer, Rich, pytest, hypothesis, ruff, FastAPI for later)
- `src/ksp_planner/` layout (src-layout, not flat)
- `tests/` with one trivial `test_smoke.py` that imports the package
- `Makefile` targets: `make test`, `make lint`, `make fmt`, `make seed`, `make run`
- `.gitignore` (add `ksp.db`, `__pycache__`, `.venv`, `.pytest_cache`)
- `ruff.toml` or `pyproject.toml` `[tool.ruff]` block
- `conftest.py` fixture stub for the test DB

**Done when:** `make test` runs zero real tests but reports green. `make lint` is clean.

---

## Phase 1 — Data foundation

**Deliverable:** `ksp.db` with all 17 stock bodies, antennas, DSN levels — queryable via `db.py`.

- Schema from [docs/03-schema.md](03-schema.md)
- `seeds/seed_stock.py` populates `bodies`, `orbits`, `antennas`, `dsn_levels`
- `db.py` with `get_body`, `list_bodies`, `get_antenna`, `get_dsn`
- Tests: assert known μ / radius / SOI for every body. Catches seed typos, which are the likeliest bug here.
- Tests: assert `parent_id` hierarchy is consistent (every body's parent exists; no cycles).

**Done when:** `make seed && pytest tests/test_seed.py` passes. Running `ksp body kerbin` (stub) prints the row.

---

## Phase 2 — Orbital mechanics core

**Deliverable:** `orbital.py` with pure-function implementations of every formula the later calculators need.

- Functions: `orbital_period`, `vis_viva`, `escape_velocity`, `hohmann_dv`, `surface_gravity`, `sync_orbit_radius`, `hill_sphere`
- Unit tests pin against canonical KSP values:
  - Kerbin synchronous altitude ≈ **2,863.33 km**
  - Mun escape velocity at surface ≈ **807 m/s**
  - Kerbin surface gravity ≈ **9.81 m/s²**
  - Kerbin → Duna Hohmann total Δv ≈ **1,060 m/s** from a 100 km parking orbit
- Property-based tests via `hypothesis`:
  - `orbital_period` is monotonic in sma
  - `vis_viva(r=sma, …) == sqrt(mu / sma)` (circular-orbit identity)
  - `hohmann_dv` is symmetric in cost between r1→r2 and r2→r1

**Done when:** all tests pass, coverage on `orbital.py` is 100%.

---

## Phase 3 — Comm network calculator

**Deliverable:** `comms.py` with a working `comm_network_report()` that matches the planning doc's worked example.

- Functions: `comm_range`, `min_sats_for_coverage`, `orbit_for_coverage`, `sat_separation`, `comm_network_report`
- Integration test: **3 sats at Kerbin with RA-15 and DSN Lvl 2** must reproduce the boxed output in [docs/features/comm-network.md](features/comm-network.md) within rounding tolerance.
- Edge-case tests: 2-sat constellation (should be flagged invalid or very high orbit), coverage failure at 0° elevation, Jool (big SOI), Gilly (tiny body).

**Done when:** worked-example test is green. A human eyeballs the report and it matches community values.

---

## Phase 4 — CLI shell

**Deliverable:** A Typer app you can actually run.

- `ksp body <slug>` — full data dump, pretty-printed via Rich
- `ksp bodies [--type planet|moon|star]` — listing
- `ksp antennas` — antenna table
- `ksp comms <body> --sats N --antenna <name> --dsn N` — runs the Phase 3 calculator
- `ksp` alone → interactive menu loop (fallback for users who don't want subcommands)
- Tests via Typer's `CliRunner` against each subcommand

**Done when:** `pipx install -e .` (or `uv tool install`) gives you a working `ksp` binary. All subcommands covered by tests.

---

## Phase 5 — More calculators

**Deliverable:** Hohmann transfer + TWR/Tsiolkovsky reachable from the CLI.

- `ksp hohmann <from-body> <to-body> [--from-alt 100 --to-alt 100]` — ejection + insertion Δv, transfer time
- `ksp twr --thrust <N> --isp <s> --mass <kg> [--body kerbin]` — TWR + burn time
- `ksp dv-budget --isp <s> --wet <kg> --dry <kg>` — Tsiolkovsky solve-for-Δv
- Tests against community numbers for each.

**Done when:** all three subcommands work end-to-end and have tests.

---

## Phase 6 — Mission plan persistence

**Deliverable:** A `plans` table and CLI commands to save/load named plans.

- Schema: `plans(id, name UNIQUE, kind, config_json, created_at, updated_at)`
  - `kind`: `'comms' | 'hohmann' | 'dv_trip' | 'twr'`
  - `config_json`: the inputs to the calculator (not the computed outputs)
- `plans.py` module with `save(name, kind, config)`, `load(name)`, `list_all()`, `delete(name)`
- CLI: `ksp plan save kerbin-relay-v2 comms …`, `ksp plan load kerbin-relay-v2`, `ksp plan list`, `ksp plan delete …`
- On load, recompute from current code — this way, if formulas change, saved plans pick up the new values.

**Done when:** round-trip save/load works for every calculator kind.

---

## Phase 7 — Δv planner

**Deliverable:** A trip planner over the full KSP delta-v chart. See [docs/features/dv-planner.md](features/dv-planner.md) for the full design.

Ladder:
- **7a** — Total Δv between two nodes. Seeded canonical chart values + flat 5% margin.
- **7b** — Intermediate stops with `land | orbit | flyby` per stop.
- **7c** — Return-trip toggle + per-edge `can_aerobrake` flag.
- **7d** — Stage-aware budget check (pairs with Phase 5 TWR/Tsiolkovsky).
- **7e** — Graph upgrade (Dijkstra) for non-tree routes like moon-to-moon direct transfers.

**Done when:** each sub-phase's acceptance test passes. Start with 7a and ship.

---

## Phase 8 — Web UI + prod1 deploy

**Deliverable:** A FastAPI app, same calculators, reachable at `https://ksp.<your-domain>`.

- `src/ksp_planner/web/` with endpoints mirroring the CLI subcommands
- Pydantic request/response schemas
- Minimal HTML templates (Jinja) or a single-page static frontend — decide once we see Phase 4's Rich output
- `systemd` unit file in `deploy/ksp-planner.service`
- nginx reverse-proxy config in `deploy/nginx.conf`
- Deploy runbook in `deploy/README.md`

**Done when:** app responds to external HTTPS requests on prod1 and survives a reboot.

---

## Phase 9 — Mod packs & KSP2 (stretch)

**Deliverable:** Alternate seed files; `--db` flag to pick which DB the app loads.

- `seeds/seed_rss.py` — Real Solar System values
- `seeds/seed_opm.py` — Outer Planets Mod extras
- `seeds/seed_ksp2.py` — KSP2 bodies (data model may need tweaks)
- Schema unchanged where possible.

**Done when:** `ksp --db ksp_rss.db body earth` works.

---

## Transfer window finder (deferred)

Not yet scheduled. Requires integrating a Kerbin-time ephemeris and iterating phase angles. Revisit after Phase 8.
