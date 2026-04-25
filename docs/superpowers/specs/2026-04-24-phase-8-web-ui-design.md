# Phase 8 — Web UI design

> **Last updated:** 2026-04-24

---

## What we're building

A web view over the existing pure-calculator core (`orbital.py`, `comms.py`, `dv_map.py`, `plans.py`). The CLI is *also* a view over those calculators; the web layer is its sibling, not its replacement. The Phase 0 architecture bet — calculators are pure, DB is read-only at runtime, presentation layers are dumb — is what makes Phase 8 small.

Phase 8 ends with `https://ksp.<domain>` (or a homelab-LAN URL) responding to external HTTPS, surviving a reboot, and returning the same numbers as the CLI for every calculator.

---

## Stack

**FastAPI + Jinja2 + HTMX + plain CSS.** Server-rendered HTML; HTMX swaps result panels; no build step; no npm; `htmx.min.js` vendored (~14 KB) under `static/js/`.

Rejected:

- **Django** — calculators are pure, sqlite3 is raw, no users/auth/admin. Django optimises for problems we don't have. Worth learning, wrong app.
- **React** — overkill for the current "form-in / result-out" shape. Held in reserve for any one page that grows interactive needs (drag-and-drop deploy timeline, live-recompute sliders, canvas with orbit visualisation). When that day comes, drop React into one page only — don't rewrite the rest.
- **Vanilla JS** — viable but boring; you'd hand-write what HTMX does in 14 KB.

---

## Audience

Just-you-for-now. No auth in Phase 8. The schema does not preclude a future `user_id` column on `plans`. If multi-user comes later, front the app with reverse-proxy basic-auth before considering sessions.

---

## Aesthetic — "space terminal refined" (direction C)

Picked from the brainstorm visual companion. Live mockup at the time of writing was the Δv planner page in this style.

### Palette

```
--color-bg:          #0c1020   /* dark navy main */
--color-surface:     #0e1530   /* surface cards */
--color-surface-alt: #080c1a   /* nested code blocks, header */
--color-border:      rgba(142, 212, 168, 0.18)
--color-border-alt:  rgba(142, 212, 168, 0.30)
--color-accent:      #8ed4a8   /* single accent — affordances, ticks, primary action */
--color-text:        #e7ecf3
--color-text-muted:  #8a94a6
--color-text-dim:    #5a6880
```

### Typography

| Use | Family |
|-----|--------|
| Prose, page titles, stop markers, editorial labels | IBM Plex Serif |
| Numeric data, slugs, code, CLI hints | JetBrains Mono |
| Form checkboxes only | system-ui |

### Visual rules

- ASCII box-drawing **not** used. Borders are `1px solid rgba(green, 0.18–0.3)`. Keeps the terminal feel without breaking responsive/accessibility.
- One accent colour, used sparingly: the green. Reserved for affordances, active nav, aerobrake ticks, primary submit button.
- Follow-up: palette flagged as "a little harsh"; one-line tweak on `--color-bg` / `--color-accent` later.

---

## Sub-phase ladder

Same cadence as Phase 7: each sub-phase ships independently with a reset point; PROGRESS.md is the handoff doc.

| # | Scope | Acceptance |
|---|-------|------------|
| **8a** | FastAPI skeleton + component library + `/dv` (Δv planner). No save, no plans nav. | POST `/dv` (kerbin_surface→mun_surface, round-trip, aerobrake on, margin 5) returns 8 leg rows, raw 10,300 m/s, aerobrake 6,900 m/s (−3,400), planned 7,245 m/s. Same numbers via JSON, HTMX partial, and shareable GET URL. |
| **8b** | New: `resonant_deploy()` in `orbital.py` (TDD, pure math, ~20 LOC). Web: `/comms` page chaining network-coverage report and deployment plan. | Worked example: 3-sat Kerbin coverage at min altitude → resonant deploy plan with deploy orbit periapsis altitude + per-burn Δv. Numbers match `comm_network_report` for the network half; resonant-deploy half cross-checks against community formulas. |
| **8c** | `/plans` browser (list / show / run / delete) + "save as plan" wired into `/dv`. | Round-trip: save `/dv` result as a plan → list shows it → run reproduces same numbers → delete removes it. |
| **8d** | `/hohmann`, `/twr`, `/dv-budget` pages. | Each form returns CLI-equivalent panel + JSON. |
| **8e** | `/refs/bodies`, `/refs/antennas`, `/refs/dsn` (read-only browse). | All seed data reachable via the web. |
| **8f** | Deploy to homelab LXC (systemd unit + reverse proxy + runbook). | App responds to external requests on the homelab host (and via Cloudflare A record if configured) and survives a reboot. |

Deploy is the *last* sub-phase on purpose — local dev (just `uv run ksp-web`) carries 8a–8e, which keeps iteration fast.

---

## File layout

```
src/ksp_planner/web/
├── __init__.py
├── app.py                      # FastAPI instance, static mount, Jinja setup, lifespan
├── deps.py                     # get_db() dependency wrapper
├── routes/
│   ├── __init__.py
│   ├── dv.py                   # 8a
│   ├── plans.py                # 8c
│   ├── comms.py                # 8b
│   ├── hohmann.py              # 8d
│   ├── twr.py                  # 8d
│   ├── dv_budget.py            # 8d
│   └── refs.py                 # 8e (bodies/antennas/dsn)
├── schemas.py                  # Pydantic request/response models
├── templates/
│   ├── base.html               # header, nav, footer, <link> to CSS, <script src="htmx.min.js">
│   ├── macros/
│   │   ├── forms.html          # {body_picker}, {number_input}, {toggle}, {submit_button}
│   │   ├── panels.html         # {result_panel}, {empty_state}, {error_flash}
│   │   └── tables.html         # {leg_table}, {data_table}
│   ├── partials/
│   │   └── dv_result.html      # returned on HTMX POST to /dv
│   └── pages/
│       └── dv.html             # extends base; initial GET returns full page
└── static/
    ├── css/
    │   ├── theme.css            # design tokens (CSS custom properties)
    │   └── components.css       # .panel, .form-grid, .leg-table, .nav, etc.
    └── js/
        └── htmx.min.js          # vendored, no CDN
```

### Module responsibility (reinforces the calculator-is-pure rule)

- **`web/routes/*.py`** — parse inputs (Pydantic), call pure calculators, render a template. Zero business logic.
- **`web/templates/`** — presentation only. No inline Python branching beyond `{% if %}` on presentation state.
- **`web/schemas.py`** — Pydantic models. Same model validates form data and JSON requests.
- **Calculators stay untouched.** Phase 8a–8e add **zero lines** to `orbital.py`, `comms.py`, `dv_map.py`, `plans.py`. Phase 8b adds one new function (`resonant_deploy`) to `orbital.py` — that's the only calculator-layer change in the entire phase.

---

## Dual response pattern

Every form endpoint returns three shapes from one function:

```python
@router.post("/dv")
def plan(req: DvRequest, hx_request: bool = Header(False), accept: str = Header("text/html")):
    trip = dv_map.plan_trip(...)               # pure calc
    if "application/json" in accept:
        return DvResponse.from_trip(trip)      # JSON for scripting
    if hx_request:
        return templates.TemplateResponse(
            "partials/dv_result.html", {"trip": trip})
    return templates.TemplateResponse(
        "pages/dv.html", {"trip": trip})        # full page (shareable URL)
```

Forms use `hx-post="/dv"` + `hx-target="#result"` + `hx-push-url="true"` → submitting swaps just the result panel **and** updates the URL bar to the GET equivalent. Every result is a shareable link.

---

## 8a feature scope (the hero page)

### URL structure

- `GET /` — redirects to `/dv`
- `GET /dv` — full page, form prepopulated from querystring; result rendered if querystring is complete enough
- `POST /dv` — three responses (HTMX / JSON / full page), per the dual-response pattern

### Pydantic request model

```python
class StopInput(BaseModel):
    body: str
    action: Literal["land", "orbit", "flyby"] = "orbit"

class DvRequest(BaseModel):
    from_: str               # slug, e.g. "kerbin_surface"
    to: str                  # slug
    via: list[StopInput] = []
    round_trip: bool = False
    aerobrake: bool = True
    margin_pct: float = 5.0
```

### JSON response model

```python
class DvResponse(BaseModel):
    from_slug: str
    to_slug: str
    round_trip: bool
    legs: list[LegOut]              # slug-from, slug-to, dv_m_s, can_aerobrake
    stops: list[StopOut]            # slug, action, after_leg_idx
    total_raw: float
    total_aerobraked: float | None
    total_planned: float
    margin_pct: float
    aerobrake: bool
    equivalent_cli: str             # "ksp dv kerbin_surface mun_surface --return"
```

### Form UX

- **From / To**: one `<select>` each, listing all 58 Δv nodes, grouped `<optgroup>` by body.
- **Via stops**: body `<select>` (17 bodies) + action `<select>` (land / orbit / flyby). Add/remove rows; no reordering in 8a.
- **Round-trip / aerobrake**: checkboxes (aerobrake default on, matching CLI).
- **Margin**: numeric input, default 5, validated 0–100 server-side.
- **Submit**: green `plan trip →`; HTMX shows loading indicator while in-flight.

### Out of scope for 8a

- Save-as-plan (returns 8c)
- Plans nav item (greyed out until 8c)
- Satellite network / resonant deploy (8b)
- All other calculators (8d, 8e)

### 8a acceptance test set

```
GET /dv                                                  → 200, form rendered, no result block
POST /dv  form: from=kerbin_surface, to=mun_surface,
          round_trip=on, aerobrake=on, margin_pct=5      → 200, result contains:
  - leg table with 8 rows (outbound 4 + return 4)
  - "10,300 m/s" (raw)
  - "6,900 m/s" (aerobrake, with "−3,400" delta)
  - "7,245 m/s" (planned)
  - "uv run ksp dv kerbin_surface mun_surface --return"
GET /dv?from_=kerbin_surface&to=mun_surface&round_trip=1 → 200, same numbers, form prepopulated
POST /dv  Accept: application/json, same body            → 200, DvResponse JSON, same numbers
POST /dv  HX-Request: true, same body                    → 200, only result partial returned
POST /dv  from=garbage                                   → 400, error flash, form preserved
POST /dv  unreachable contrived slug pair                → 400, "no path" flash
```

These reuse the exact Phase 7d canonical numbers — the web layer is verifiably a view.

---

## Testing approach

TDD throughout, using FastAPI `TestClient` (which is httpx under the hood). Same RED→GREEN cadence as Phases 1–7.

- One test file per sub-phase: `tests/test_web_dv.py`, `tests/test_web_comms.py`, etc.
- Shared `app` fixture in `conftest.py` overrides `deps.get_db()` to the session-scoped seeded DB.
- Per page (~8–10 tests):
  1. Happy-path HTML — POST returns 200, result contains canonical numbers.
  2. Happy-path JSON — POST with `Accept: application/json` returns the Pydantic model.
  3. HTMX partial — POST with `HX-Request: true` returns just the partial (no `<html>` wrapper).
  4. Shareable URL — GET with querystring returns same numbers as POST.
  5. Error cases — malformed input, unreachable path, missing fields. Each returns 4xx + structural `.error-flash` marker.
- Assertions on **structural markers** (`"7,245 m/s" in response.text`, `soup.select(".leg-table tr")`), not full HTML strings.
- Trajectory: 207 → ~217 (after 8a) → ~225 (8b) → ~250 (by 8f).
- Playwright / E2E **deferred** — overkill for a personal-scale tool, revisit if multi-user comes later.

---

## Deploy story

The eventual host (`prod1`) is an Ubuntu LXC container on the user's homelab. A Cloudflare A record will point `ksp.<domain>` at it once 8f ships. The non-negotiable design constraint is **portability** — the app must run locally on *any* machine; the homelab is one hosting target among many, not a special case in the code.

### Portability principle (drives 8f design)

Anyone with the repo + `uv` should be able to:

```bash
git clone … && cd ksp-app
uv sync
make seed
uv run ksp-web         # → http://127.0.0.1:8080
```

…and have a working app on localhost in under a minute. Deploy artefacts (systemd unit, Caddy config) live in `deploy/` as **references**, not requirements.

### Entry point

```toml
# pyproject.toml
[project.scripts]
ksp = "ksp_planner.cli:app"
ksp-web = "ksp_planner.web.app:serve"   # new
```

`ksp-web` wraps uvicorn with sane defaults (host 127.0.0.1, port 8080, reload in dev). Production overrides via env vars (`KSP_HOST`, `KSP_PORT`, `KSP_DB_PATH`, `KSP_RELOAD`).

### 8f shape (details still open)

- **systemd unit** `deploy/ksp-planner.service`: runs `uvicorn` as a dedicated user, `WorkingDirectory` on the deploy path, env-var configured, `Restart=always`. Runs on the LXC.
- **Reverse proxy** in `deploy/<proxy>.conf`: terminates HTTPS, proxies to uvicorn on 127.0.0.1, serves static files directly.
- **Cloudflare A record** points `ksp.<domain>` at the homelab WAN IP (or via Cloudflare Tunnel — TBD).
- **Runbook** in `deploy/README.md`: clone → `uv sync` → `make seed` → install unit → enable + start → verify.

Open in 8f:

- nginx vs Caddy — Caddy preferred for one-line auto-HTTPS, but nginx is fine if the homelab already has it in use.
- Cloudflare A record direct vs Cloudflare Tunnel — Tunnel avoids opening homelab ports, but adds a dependency on Cloudflare being up.

### Dependencies (added to `pyproject.toml`)

```
fastapi >= 0.115
uvicorn[standard] >= 0.32
jinja2 >= 3.1
python-multipart >= 0.0.18    # form parsing
httpx >= 0.27                 # TestClient (dev group only)
```

No npm. `htmx.min.js` vendored.
