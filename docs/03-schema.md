# SQLite schema

All tables live in a single file: `ksp.db`. The seed scripts in `seeds/` are the canonical source of truth — the database can always be deleted and regenerated.

SI units throughout: **metres, seconds, kilograms, watts**. Conversions from km / km³ s⁻² happen at seed time, once.

---

## `bodies`

Celestial bodies — stars, planets, moons. Self-referencing via `parent_id` to model the system hierarchy.

| Column            | Type    | Constraint  | Description                                 |
|-------------------|---------|-------------|---------------------------------------------|
| `id`              | INTEGER | PK          | Auto-increment                              |
| `name`            | TEXT    | NOT NULL    | Display name, e.g. `Kerbin`, `Mun`          |
| `slug`            | TEXT    | UNIQUE      | Lowercase key, e.g. `kerbin`                |
| `body_type`       | TEXT    |             | `star` / `planet` / `moon`                  |
| `parent_id`       | INTEGER | FK bodies   | NULL for Kerbol                             |
| `radius_m`        | REAL    | NOT NULL    | Equatorial radius                           |
| `mass_kg`         | REAL    |             | Body mass (optional; μ is authoritative)    |
| `mu_m3s2`         | REAL    | NOT NULL    | Gravitational parameter (primary)           |
| `soi_m`           | REAL    |             | SOI radius; NULL = infinite (Kerbol only)   |
| `atm_height_m`    | REAL    |             | Atmosphere top altitude; NULL if none       |
| `has_oxygen`      | INTEGER |             | 0 / 1 (affects jet engines)                 |
| `sidereal_day_s`  | REAL    |             | Rotation period                             |
| `sync_orbit_m`    | REAL    |             | Synchronous orbit altitude (derived)        |

---

## `orbits`

Standard Keplerian elements for every body that orbits something. Kerbol has no row here.

| Column                    | Type    | Constraint | Description                                  |
|---------------------------|---------|------------|----------------------------------------------|
| `id`                      | INTEGER | PK         |                                              |
| `body_id`                 | INTEGER | FK bodies  | One row per orbiting body                    |
| `sma_m`                   | REAL    |            | Semi-major axis                              |
| `eccentricity`            | REAL    |            | 0 = circular                                 |
| `inclination_deg`         | REAL    |            | Degrees from parent equator                  |
| `arg_periapsis_deg`       | REAL    |            | Argument of periapsis                        |
| `lan_deg`                 | REAL    |            | Longitude of ascending node                  |
| `mean_anomaly_epoch_deg`  | REAL    |            | Mean anomaly at epoch                        |
| `epoch_s`                 | REAL    |            | Epoch time in game seconds (usually 0)       |

---

## `antennas`

| Column       | Type    | Constraint | Description                                           |
|--------------|---------|------------|-------------------------------------------------------|
| `id`         | INTEGER | PK         |                                                       |
| `name`       | TEXT    | NOT NULL   | e.g. `RA-100 Relay Antenna`                           |
| `range_m`    | REAL    | NOT NULL   | Reference range in metres (KSP `antennaPower`)        |
| `is_relay`   | INTEGER |            | 0 / 1                                                 |
| `combinable` | INTEGER |            | 1 if multiple of this antenna stack                   |

The `range_m` column stores KSP's `antennaPower` field, whose in-game unit is **metres** (the range between two identical antennas, computed as `sqrt(P_A × P_B)`). The original planning docx labelled this column "Power (W)" — that's a misnomer; see [02-data-sources.md](02-data-sources.md).

Seeded set (9 antennas): Communotron 16-S, Communotron 16, Communotron DTS-M1, Communotron HG-55, Communotron 88-88, HG-5 High Gain Antenna, RA-2, RA-15, RA-100.

---

## `dsn_levels`

| Column    | Type    | Constraint | Description                                        |
|-----------|---------|------------|----------------------------------------------------|
| `level`   | INTEGER | PK         | 1, 2, or 3                                         |
| `range_m` | REAL    | NOT NULL   | DSN tracking station reference range in metres     |

Seeded (from CustomBarnKit `TRACKING.DSNRange`):
- Level 1 → 2 × 10⁹ m
- Level 2 → 5 × 10¹⁰ m
- Level 3 → 2.5 × 10¹¹ m

---

## `dv_nodes` *(Phase 7)*

Nodes in the Δv chart tree. One row per reachable "state" for a body.

| Column    | Type    | Constraint | Description                                                       |
|-----------|---------|------------|-------------------------------------------------------------------|
| `id`      | INTEGER | PK         |                                                                   |
| `body_id` | INTEGER | FK bodies  | NULL for abstract nodes like `kerbol_orbit`                       |
| `state`   | TEXT    | NOT NULL   | `surface` / `low_orbit` / `capture` / `transfer` / `sun_orbit`    |
| `slug`    | TEXT    | UNIQUE     | e.g. `kerbin_surface`, `mun_low_orbit`, `jool_transfer`           |
| `parent_slug` | TEXT |            | FK to `dv_nodes(slug)`; NULL for the root (`kerbol_orbit`)        |

The parent pointer defines the tree shape. Path finding between two slugs is a walk up to the LCA and back down.

---

## `dv_edges` *(Phase 7)*

Δv cost between adjacent nodes. Directed, because descent/ascent are asymmetric for atmospheric bodies.

| Column          | Type    | Constraint     | Description                                       |
|-----------------|---------|----------------|---------------------------------------------------|
| `id`            | INTEGER | PK             |                                                   |
| `from_slug`     | TEXT    | FK dv_nodes    |                                                   |
| `to_slug`       | TEXT    | FK dv_nodes    |                                                   |
| `dv_m_s`        | REAL    | NOT NULL       | Canonical chart value                             |
| `can_aerobrake` | INTEGER |                | 1 if descent can skip powered braking             |
| `notes`         | TEXT    |                | e.g. "requires correct ejection angle"            |

For each pair of adjacent nodes we insert **two rows** (one per direction), so ascent and descent costs can differ.

Phase 7e may add an `edge_type` column (`ascent` / `transfer` / `capture` / `landing` / …) to support per-edge-type margins.

---

## `plans` *(Phase 6)*

Saved mission plans. Stores the **inputs** to a calculator, not the computed outputs, so formula changes propagate to saved plans on reload.

| Column        | Type    | Constraint        | Description                                           |
|---------------|---------|-------------------|-------------------------------------------------------|
| `id`          | INTEGER | PK                |                                                       |
| `name`        | TEXT    | UNIQUE NOT NULL   | User-chosen, e.g. `kerbin-relay-v2`                   |
| `kind`        | TEXT    | NOT NULL          | `comms` / `hohmann` / `dv_trip` / `twr`               |
| `config_json` | TEXT    | NOT NULL          | JSON blob of the calculator inputs                    |
| `created_at`  | TEXT    | NOT NULL          | ISO 8601                                              |
| `updated_at`  | TEXT    | NOT NULL          | ISO 8601                                              |

Kept deliberately generic — each calculator validates its own `config_json` against a Pydantic model on load.

---

## Foreign key integrity

SQLite does not enforce FKs by default. `db.py` runs `PRAGMA foreign_keys = ON` on every new connection. Seed tests also assert:
- Every `bodies.parent_id` points to an existing `bodies.id` (or is NULL only for Kerbol)
- Every `dv_nodes.parent_slug` points to an existing `dv_nodes.slug` (or is NULL only for the root)
- No cycles in either hierarchy

---

## Why no migrations framework

- Schema is small and mostly reference data
- No user data lives in the DB before Phase 6
- The `plans` table is simple enough that any future change = one hand-written `ALTER`
- Resetting the DB from seeds is cheap (seconds)

If this stops being true later, `alembic` drops in cleanly.
