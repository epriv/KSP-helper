# Phase 8b — /comms Web Page Design

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a `/comms` page to the FastAPI app that mirrors `ksp comms` CLI parity, plus a resonant deployment orbit helper not present in the CLI.

**Architecture:** New `routes/comms.py` + two templates follow the exact same GET/POST/HTMX/JSON pattern established in Phase 8a's `routes/dv.py`. One new pure function (`resonant_deploy`) lands in `comms.py`; two new Pydantic models land in `schemas.py`. No new DB tables.

**Tech Stack:** FastAPI, Jinja2, HTMX, Pydantic v2, SQLite (read-only), pytest + TestClient

---

## Scope

**In:** CLI parity (same five inputs as `ksp comms`) + resonant deployment orbit helper + shareable GET URLs + HTMX partial swap + JSON response mode.

**Out:** Minimum-sats reverse lookup, save-to-plan web button, DSN-level advisor, eclipse duration, multi-hop relay chain. All deferred post-8b.

---

## File Map

| Action   | Path |
|----------|------|
| Modify   | `src/ksp_planner/comms.py` — add `resonant_deploy()` |
| Modify   | `src/ksp_planner/web/schemas.py` — add `CommsRequest`, `CommsResponse` |
| Modify   | `src/ksp_planner/web/app.py` — include `routes.comms` router |
| Modify   | `src/ksp_planner/web/templates/base.html` — enable "Comm Net" nav chip |
| Create   | `src/ksp_planner/web/routes/comms.py` — GET + POST `/comms` |
| Create   | `src/ksp_planner/web/templates/pages/comms.html` — full page |
| Create   | `src/ksp_planner/web/templates/partials/comms_result.html` — HTMX partial |
| Modify   | `tests/test_comms.py` — add `resonant_deploy` unit tests |
| Create   | `tests/test_web_comms.py` — route + integration tests |

---

## Pure Function: `resonant_deploy()`

Added to `comms.py`. Pure — no DB, no I/O.

```python
def resonant_deploy(orbit_radius_m: float, n_sats: int, mu: float) -> dict:
    """Resonant parking orbit for deploying N evenly-spaced satellites.

    Standard technique: deploy first sat at target orbit, then fire retrograde
    into a (N-1)/N resonant orbit. After one lap, you're exactly 1/N behind
    the first sat. Repeat N-1 times.

    Returns resonant_period_s, resonant_sma_m, and ratio string "(N-1)/N".
    """
    target_period = orbital_period(orbit_radius_m, mu)
    resonant_period = target_period * (n_sats - 1) / n_sats
    resonant_sma = orbit_radius_m * ((n_sats - 1) / n_sats) ** (2 / 3)
    return {
        "resonant_period_s": resonant_period,
        "resonant_sma_m": resonant_sma,
        "ratio": f"{n_sats - 1}/{n_sats}",
    }
```

**Canonical check (Kerbin 3-sat, orbit_r = 1,414,320 m, μ = 3.5316×10¹² m³/s²):**
- Target period ≈ 5,624 s (1h 33m 44s)
- Resonant period ≈ 3,749 s (1h 2m 29s) — ratio 2/3
- Resonant SMA ≈ 1,079,328 m → altitude ≈ 479,328 m (≈ 479 km)

---

## Schema Layer

Added to `schemas.py`:

```python
class CommsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    body: str = Field(..., min_length=1)
    n_sats: int = Field(3, ge=2)
    antenna: str = Field(..., min_length=1)
    dsn_level: int = Field(2, ge=1, le=3)
    min_elev_deg: float = Field(5.0, ge=0, lt=90)


class CommsResponse(BaseModel):
    body_slug: str
    n_sats: int
    antenna_name: str
    dsn_level: int
    min_elev_deg: float
    orbit_altitude_km: float
    period_s: float
    range_sat_to_sat_km: float
    range_sat_to_dsn_km: float
    sat_separation_km: float
    coverage_ok: bool
    coverage_margin_km: float
    suggestion: str
    resonant_altitude_km: float
    resonant_period_s: float
    resonant_ratio: str           # "2/3", "3/4", etc.
    equivalent_cli: str

    @classmethod
    def from_report(
        cls,
        report: dict,
        resonant: dict,
        body_radius_m: float,
        equiv_cli: str,
    ) -> "CommsResponse":
        return cls(
            body_slug=report["body"],
            n_sats=report["n_sats"],
            antenna_name=report["antenna"],
            dsn_level=report["dsn_level"],
            min_elev_deg=report["min_elev_deg"],
            orbit_altitude_km=report["orbit_altitude_m"] / 1000,
            period_s=report["period_s"],
            range_sat_to_sat_km=report["range_sat_to_sat_m"] / 1000,
            range_sat_to_dsn_km=report["range_sat_to_dsn_m"] / 1000,
            sat_separation_km=report["sat_separation_m"] / 1000,
            coverage_ok=report["coverage_ok"],
            coverage_margin_km=report["coverage_margin_m"] / 1000,
            suggestion=report["suggestion"],
            resonant_altitude_km=(resonant["resonant_sma_m"] - body_radius_m) / 1000,
            resonant_period_s=resonant["resonant_period_s"],
            resonant_ratio=resonant["ratio"],
            equivalent_cli=equiv_cli,
        )
```

All distances converted m → km at the schema boundary (SI internally, friendly at the edge — same rule as CLI layer).

---

## Route: `routes/comms.py`

### Helpers

```python
def _comms_ctx(**extra) -> dict:
    return {"active_nav": "comms", "version": "0.8.0b", **extra}

def _sidebar_data(conn) -> dict:
    """Antenna list + DSN levels for the sidebar reference panels."""
    antennas = [dict(r) for r in conn.execute(
        "SELECT name, range_m FROM antennas ORDER BY range_m"
    )]
    dsn_levels = [dict(r) for r in conn.execute(
        "SELECT level, range_m FROM dsn_levels ORDER BY level"
    )]
    return {"antennas": antennas, "dsn_levels": dsn_levels}
```

`COMMS_BODIES` — same 17-body list as `/dv` (all bodies available as constellation targets).

### GET `/comms`

Query params mirror the five CLI inputs (all optional). When all five are present, compute and show result; otherwise show empty form.

```
GET /comms                                            → empty form
GET /comms?body=kerbin&n_sats=3&antenna=RA-15+Relay+Antenna&dsn_level=2&min_elev_deg=5
                                                      → form pre-filled + result
```

### POST `/comms`

1. Resolve body row via `db.get_body(conn, body_slug)`
2. Resolve antenna row via `db.get_antenna(conn, antenna_name)`
3. Resolve DSN row via `db.get_dsn(conn, dsn_level)`
4. Call `comm_network_report(body, n_sats, antenna, dsn, min_elev_deg)`
5. Call `resonant_deploy(report["orbit_radius_m"], n_sats, body["mu_m3s2"])`
6. Build `CommsResponse.from_report(...)`
7. Branch on `HX-Request` / `Accept: application/json` headers (same pattern as `/dv`)

### Response routing

| Condition | Template / response |
|-----------|---------------------|
| `Accept: application/json` (no `text/html`) | `CommsResponse` JSON |
| `HX-Request: true` + error | `partials/error_flash.html` (existing) |
| `HX-Request: true` + success | `partials/comms_result.html` |
| Full-page | `pages/comms.html` |

### Error handling

- `KeyError` (unknown body/antenna/DSN) → 400, red flash
- `ValueError` from `orbit_for_coverage` (geometry impossible, e.g. N=2 at elev=45°) → 400, red flash
- `ValidationError` → 400, red flash (first error message)

---

## Templates

### `pages/comms.html`

Extends `base.html`. Two-column grid `wb-grid-comms` (1fr 340px):

**Left panel** — form + `#result` div:
- Row 1: body dropdown + n_sats number input (grid 1fr 1fr)
- Row 2: antenna dropdown + DSN select (1/2/3) + min_elev number input + `°` suffix (grid 1fr 80px 80px)
- Controls row: `Calculate →` button (btn-primary, margin-left auto)
- `<div id="result">` — includes `partials/comms_result.html` on load if result present, else `empty_state()` macro

Form: `hx-post="/comms" hx-target="#result" hx-swap="innerHTML" hx-push-url="true"`

**Right column** — two stacked `.ksp-panel` cards:
1. Antennas reference: table of name + range (km), loaded from DB, sorted by range ascending
2. DSN levels reference: three rows (Level 1/2/3 + range in km)

### `partials/comms_result.html`

Rendered for both HTMX swaps and full-page includes.

1. **Coverage indicator** — `.ksp-coverage.is-ok` or `.is-bad` with glowing dot + margin text
2. **If `suggestion`** — `.ksp-flash` with the error hint ("sat separation exceeds antenna range — add sats or pick a stronger antenna")
3. **Totals row** — two `.ksp-total` boxes: orbit altitude (primary/mint) + period
4. **Legs-style stat rows** — sat↔sat range, sat↔DSN range, sat separation (chord)
5. **Resonant deployment box** — gold left-border box with eyebrow "Resonant deployment orbit", three values: altitude (km), period (hh:mm:ss), ratio string
6. **CLI hint** — `.ksp-cli` with equivalent `uv run ksp comms ...` command

### `base.html` change

```html
<!-- before -->
<span class="wb-chip is-disabled" title="ships in 8b">Comm Net</span>

<!-- after -->
<a href="/comms" class="wb-chip {{ 'is-active' if active_nav == 'comms' else '' }}">Comm Net</a>
```

---

## Acceptance Criteria

```
GET  /comms                        → 200, form, no result
POST /comms  body=kerbin n_sats=3 antenna="RA-15 Relay Antenna" dsn_level=2 min_elev_deg=5
                                   → coverage OK, altitude 814 km, resonant alt 543 km
GET  /comms?body=kerbin&n_sats=3&antenna=RA-15+Relay+Antenna&dsn_level=2&min_elev_deg=5
                                   → same numbers (shareable URL)
HX-Request POST /comms             → partial only, no <html>
Accept: application/json POST      → CommsResponse JSON
POST bad body slug                 → 400
POST n_sats=2 min_elev_deg=45      → 400 (geometry impossible)
```

---

## Tests

### `test_comms.py` additions (2 tests)

```python
def test_resonant_deploy_kerbin_3sat():
    orbit_r = 1_414_320.0   # from canonical worked example
    mu = 3.5316e12
    result = resonant_deploy(orbit_r, 3, mu)
    assert result["ratio"] == "2/3"
    assert result["resonant_period_s"] == pytest.approx(3749, rel=0.01)
    assert (result["resonant_sma_m"] - 600_000) / 1000 == pytest.approx(479, rel=0.01)

@pytest.mark.parametrize("n,expected", [(3,"2/3"),(4,"3/4"),(5,"4/5"),(6,"5/6")])
def test_resonant_deploy_ratio_string(n, expected):
    result = resonant_deploy(1_000_000, n, 3.5316e12)
    assert result["ratio"] == expected
```

### `test_web_comms.py` (9 tests)

```python
def test_get_comms_empty_state(client): ...           # 200, form present, no result
def test_post_comms_canonical_result(client): ...     # 814 km altitude, coverage_ok, resonant 479 km
def test_post_comms_htmx_partial(client): ...         # HX-Request → no <html> tag
def test_post_comms_json(client): ...                 # Accept: application/json → CommsResponse fields
def test_post_comms_bad_body(client): ...             # unknown slug → 400
def test_post_comms_geometry_impossible(client): ...  # n_sats=2 min_elev=45 → 400
def test_get_comms_shareable_url(client): ...         # GET with querystring → same 814 km
def test_comms_nav_chip_active(client): ...           # GET /comms → Comm Net chip has is-active class
def test_comms_sidebar_loaded(client): ...            # GET /comms → antenna names in response body
```

**Total after phase close:** 235 + 11 = **246 tests passing**
