# Data sources

Before writing any code, a search was done for existing machine-readable data on KSP bodies, antennas, and Δv values. This document records what was evaluated, what we use, and what we ruled out.

## Primary source — KSPTOT `bodies.ini`

**Repo:** [github.com/Arrowstar/ksptot](https://github.com/Arrowstar/ksptot)

The KSP Trajectory Optimization Tool ships a machine-readable INI file with every stock body's full orbital elements (sma, ecc, inc, argp, raan, mean anomaly at epoch), GM, radius, and detailed atmospheric pressure/temperature profiles at multiple altitudes. Units are **km** and **km³/s²** (we convert to SI at seed time).

Why this is the primary source:
- Community-verified — used in serious astrodynamics tooling for years
- Complete — every stock body, every field we need
- Stable — project also ships `KSPTOTConnect` which can regenerate `bodies.ini` from a running KSP install, so values stay aligned with stock across KSP patches

**Seed pipeline:** `seeds/seed_stock.py` parses `bodies.ini`, converts units (km → m, km³/s² → m³/s²), and inserts into `bodies` and `orbits`.

## Cross-check source — `ksp-planet-data.netlify.app`

A live JSON API at that URL covers radius, SOI, surface gravity, escape velocity, and atmosphere height for roughly 10 bodies. Missing: μ, SMA, eccentricity, inclination.

**Use:** Sanity-check seeded values after import. If KSPTOT and this API disagree on overlapping fields by more than ~1%, the seed test fails and we investigate.

**Not suitable as a primary:** too shallow and missing critical orbital elements.

## Reference source — KSP Fandom wiki

**URL:** [wiki.kerbalspaceprogram.com](https://wiki.kerbalspaceprogram.com)

Canonical community reference. Every body has a full data table. **However,** the wiki is now protected by Anubis bot-mitigation, which makes automated scraping impractical.

**Use:** Manual reference when a value is ambiguous or KSPTOT and the JSON API disagree. The human checks the wiki and decides.

## Rejected — `darren-uk/KSP-data-sheet`

Small JSON file on GitHub. Field coverage is too shallow to seed from.

## Cross-check findings (2026-04)

Before Phase 1 seeding, every value from the original planning `.docx` was cross-checked against the authoritative sources listed above. Several transcription errors were found and replaced:

**Bodies μ (gravitational parameter).** 13 of 17 values in the docx were 1000× too high. The four correct ones: Kerbol, Moho, Gilly, Kerbin. Cause appears to be an erroneous `km³/s² → m³/s²` conversion factor (×10⁶ instead of ×10⁹) on most entries. Verified against KSPTOT `bodies.ini` and a `g = μ/r²` sanity check (Mun surface gravity with the docx value would be ~1,629 m/s²; the real value is 1.63 m/s²).

**Antenna power ratings.** 6 of 8 docx values were off by 10×–1000×. Additionally, the unit label "Power (W)" is incorrect — KSP's `antennaPower` field is a **range in metres** (the reference range when paired with an identical antenna), not watts. Verified against the Kerbalism patch comment table (`Patches-Antennas.cfg`). The schema column is accordingly named `range_m`, not `power_w`.

**DSN Level 3 range.** Docx value `2.5×10¹² W` is 10× too high. Stock value `2.5×10¹¹ m` verified against CustomBarnKit `default.cfg` (which mirrors KSP's `TRACKING.DSNRange`).

**Missing antenna.** The docx table omits the Communotron 88-88 (direct antenna, range 1×10¹¹ m). Added in seeds.

**Section 7 worked example** is therefore also inconsistent with real KSP physics — its numbers derive from the erroneous antenna/DSN values and don't match the stated formula. It has been regenerated from correct values in [docs/features/comm-network.md](features/comm-network.md).

**Net effect on docs:** the original docx is kept at the repo root as a historical planning artifact. For any point of disagreement, `docs/` and the `seeds/` scripts are authoritative.

## Δv chart values

**Source:** the canonical KSP community Δv map (variants on the wiki, Reddit `/r/KerbalSpaceProgram`, and in-game mods). Community consensus has converged on a standard set of values; different chart versions agree within ~2-3%.

We seed these canonical values directly — see [docs/features/dv-planner.md](features/dv-planner.md) for the rationale. A cross-check test computes Hohmann Δv from `orbital.py` and fails if the result diverges from the seeded chart value by more than 5%.

## What does NOT exist

- **No ready-made SQLite dump.** Nobody has published a KSP bodies DB; we build our own from KSPTOT.
- **No official API.** KSP doesn't ship with a data export tool. KSPTOTConnect is the closest thing.
- **No structured KSP2 dataset yet.** KSP2's physical constants differ from KSP1 and have shifted between patches. KSP2 support is deferred to Phase 9.

## Notes on specific bodies

- **Gilly's radius:** KSPTOT lists 13 km (equatorial). The wiki lists 26 km in some places — that's the mean radius including terrain deformity. We use 13 km (equatorial) to match the in-game SOI calculation inputs.
- **Kerbol SOI:** stored as `NULL` (infinite) rather than a magic large number. All SOI-based calculations handle `NULL` explicitly.
- **Eeloo's orbit crosses Jool's** at periapsis but they never collide due to their 3:2 resonance and differing inclinations. Mentioned here because it trips up naive "do these orbits cross" checks — we don't do that check anywhere, but if we did, that's the gotcha.

## Mod packs (Phase 9 future)

Alternate seed scripts slot into `seeds/` without schema changes:
- `seed_rss.py` — Real Solar System (real scale; needs different canonical Δv chart)
- `seed_opm.py` — Outer Planets Mod (Sarnus, Urlum, Neidon, Plock)
- `seed_ksp2.py` — KSP2 bodies (data model may need minor tweaks)

CLI flag `--db <path>` picks which DB the app loads.
