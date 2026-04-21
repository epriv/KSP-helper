PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS bodies (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT    NOT NULL,
    slug            TEXT    NOT NULL UNIQUE,
    body_type       TEXT    NOT NULL CHECK (body_type IN ('star', 'planet', 'moon')),
    parent_id       INTEGER REFERENCES bodies(id),
    radius_m        REAL    NOT NULL,
    mass_kg         REAL,
    mu_m3s2         REAL    NOT NULL,
    soi_m           REAL,
    atm_height_m    REAL,
    has_oxygen      INTEGER,
    sidereal_day_s  REAL,
    sync_orbit_m    REAL
);

CREATE TABLE IF NOT EXISTS orbits (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    body_id                 INTEGER NOT NULL REFERENCES bodies(id),
    sma_m                   REAL    NOT NULL,
    eccentricity            REAL    NOT NULL,
    inclination_deg         REAL    NOT NULL,
    arg_periapsis_deg       REAL,
    lan_deg                 REAL,
    mean_anomaly_epoch_deg  REAL,
    epoch_s                 REAL
);

CREATE TABLE IF NOT EXISTS antennas (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT    NOT NULL UNIQUE,
    range_m     REAL    NOT NULL,
    is_relay    INTEGER NOT NULL DEFAULT 0,
    combinable  INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS dsn_levels (
    level    INTEGER PRIMARY KEY,
    range_m  REAL    NOT NULL
);

CREATE TABLE IF NOT EXISTS plans (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    name         TEXT    NOT NULL UNIQUE,
    kind         TEXT    NOT NULL CHECK (kind IN ('comms', 'hohmann', 'twr', 'dv_budget')),
    config_json  TEXT    NOT NULL,
    created_at   TEXT    NOT NULL,
    updated_at   TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_bodies_parent ON bodies(parent_id);
CREATE INDEX IF NOT EXISTS idx_orbits_body   ON orbits(body_id);
