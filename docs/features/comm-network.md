# Comm Network Calculator

**Phase:** 3 — first calculator to ship.

Given a target body and a constellation configuration, work out the minimum orbital geometry needed for full surface coverage and verify the chosen antennas can actually close the link.

## Inputs

| Input                 | Type   | Default | Notes                                             |
|-----------------------|--------|---------|---------------------------------------------------|
| `body`                | str    | —       | Slug, e.g. `kerbin`, `duna`                       |
| `n_sats`              | int    | —       | Number of satellites in the constellation         |
| `antenna`             | str    | —       | Antenna name, e.g. `RA-15 Relay Antenna`          |
| `dsn_level`           | int    | 2       | 1, 2, or 3                                        |
| `min_elev_deg`        | float  | 5       | Minimum elevation angle above horizon             |

## Calculated outputs

### 1. Minimum orbit radius for coverage

For *N* evenly-spaced satellites providing full coverage down to minimum elevation ε, each satellite's footprint must reach the midpoint between it and its neighbours.

```
half_angle  = π / N                                        # angular gap between adjacent sats
orbit_r     = body_radius × cos(ε) / cos(half_angle + ε)
altitude    = orbit_r - body_radius
```

### 2. Satellite separation (chord distance)

The straight-line distance between adjacent satellites — this is the range the antenna link budget is checked against.

```
separation = 2 × orbit_r × sin(π / N)
```

### 3. Antenna link ranges

KSP uses the geometric mean of both endpoints' `antennaPower` (which is already a range in metres) to determine max link distance.

```
range_sat_to_sat = sqrt(antenna_range × antenna_range) = antenna_range
range_sat_to_dsn = sqrt(antenna_range × dsn_range)
```

### 4. Coverage check

Coverage is valid if satellite separation is **less than** the sat-to-sat range. If not, the report flags the deficit and suggests either adding sats or upgrading the antenna.

### 5. Orbital period

Kepler's third law — reported so the user can plan a resonant insertion orbit.

```
period = 2π × sqrt(orbit_r³ / body_mu)
```

## Example — 3 sats at Kerbin, RA-15, DSN Lvl 2

Computed with stock KSP values (RA-15 range 1.5×10¹⁰ m, DSN Lvl 2 range 5×10¹⁰ m, Kerbin μ = 3.5316×10¹² m³/s², R = 600 km, 5° min elevation). Note that RA-15 is an interplanetary-class relay — its 15 million km reference range is vast overkill for a 2,400-km sat-to-sat gap, hence the enormous margin:

```
════════════════════════════════════════════════════════════
  COMM NETWORK — KERBIN
════════════════════════════════════════════════════════════
  Satellites      : 3
  Antenna         : RA-15 Relay Antenna  (1.50e+10 m)
  DSN level       : 2  (5.00e+10 m)
  Min elevation   : 5°
────────────────────────────────────────────────────────────
  Required orbit
    Altitude      : 814.32 km
    Orbit radius  : 1,414.32 km
    Period        : 1 h 33 m 43 s
────────────────────────────────────────────────────────────
  Comm ranges
    Sat ↔ Sat     : 15,000,000.00 km   (antenna range)
    Sat ↔ DSN     : 27,386,127.88 km
    Sat separation:      2,449.67 km   (chord distance)
────────────────────────────────────────────────────────────
  Coverage status : ✓ COVERAGE OK
    Margin        : 14,997,550.33 km to spare
════════════════════════════════════════════════════════════
```

This is the **canonical integration test** — the calculator must reproduce these numbers within rounding tolerance. Note the altitude (814 km) is the *minimum* for 5° elevation coverage; in practice many players place relay constellations at keostationary altitude (~2,863 km) for easier station-keeping.

## Planned enhancements

- **Resonant insertion orbit calculator** — parking orbit period ratio needed to deploy evenly-spaced sats in one launch.
- **Shadow / eclipse duration per orbit** — how long each sat loses solar power.
- **Multi-hop relay chain** — check whether a sat constellation at a moon can relay back to Kerbin through an intermediate relay at the parent body.
- **"What DSN level do I need?"** — given an antenna and body, output the minimum DSN level that closes the link.

## API surface (for CLI and web)

```python
# comms.py
def comm_network_report(
    body: BodyRow,
    n_sats: int,
    antenna: AntennaRow,
    dsn_level: int,
    min_elev_deg: float = 5.0,
) -> dict:
    """Returns a plain dict. Rendering is the caller's job."""
```

Returned dict keys:

| Key                    | Type  | Description                            |
|------------------------|-------|----------------------------------------|
| `body`                 | str   | Body slug                              |
| `n_sats`               | int   |                                        |
| `antenna`              | str   |                                        |
| `dsn_level`            | int   |                                        |
| `min_elev_deg`         | float |                                        |
| `orbit_altitude_m`     | float |                                        |
| `orbit_radius_m`       | float |                                        |
| `period_s`             | float |                                        |
| `range_sat_to_sat_m`   | float |                                        |
| `range_sat_to_dsn_m`   | float |                                        |
| `sat_separation_m`     | float |                                        |
| `coverage_ok`          | bool  |                                        |
| `coverage_margin_m`    | float | Positive = OK; negative = deficit      |
| `suggestion`           | str   | Empty if OK; else human-readable hint  |
