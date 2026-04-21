# Seed data files

## `bodies.ini`

Verbatim copy of [KSPTOT `bodies.ini`](https://github.com/Arrowstar/ksptot/blob/master/bodies.ini)
at commit `c2dd927ff9dceef4ae30a0a552e1c02023227f00`.

Used as the authoritative source for every stock KSP1 body's mass (`gm`), radius,
atmosphere height, rotation period, and full six-element orbital state. Units in this
file are **km** and **km³/s²** — `seeds/seed_stock.py` converts to SI at seed time.

Reproduction is permitted under the terms described in the KSPTOT repository; the file
is bundled here solely as interoperability data for seeding a local SQLite database.
KSPTOT author: Arrowstar.

## Antennas & DSN

Not stored as external files. See inline tables in `seeds/seed_stock.py` with their
own source citations (Kerbalism patch comments for antennas, CustomBarnKit `default.cfg`
for DSN tracking station levels).
