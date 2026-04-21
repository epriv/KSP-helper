# KSP Mission Planner

A Python + SQLite mission planner for Kerbal Space Program. Starts as a console CLI against a local SQLite database of every stock body, antenna, and DSN level. Grows into a web app deployable to a home server (prod1).

## Stack

- **Python 3.12+**
- **SQLite** — raw `sqlite3` from stdlib (no ORM; dataset is small and read-mostly)
- **Typer** — CLI framework
- **Rich** — formatted console output (tables, boxed reports)
- **pytest** + **hypothesis** — tests
- **Ruff** — lint + format
- **FastAPI** + **uvicorn** — web layer (Phase 8)

## Start here

- [docs/PROGRESS.md](docs/PROGRESS.md) — **current status, where to resume, what's done vs next**
- [docs/00-architecture.md](docs/00-architecture.md) — module layout and responsibilities
- [docs/01-phases.md](docs/01-phases.md) — phased build plan with acceptance criteria
- [docs/02-data-sources.md](docs/02-data-sources.md) — where the body/antenna data comes from
- [docs/03-schema.md](docs/03-schema.md) — SQLite schema
- [docs/04-testing.md](docs/04-testing.md) — TDD approach

## Features

- [Comm Network Calculator](docs/features/comm-network.md) — Phase 3, first calculator
- [Δv Planner](docs/features/dv-planner.md) — Phase 7, trip planner built on canonical chart values

## Quickstart

Not yet implemented — project is in the planning phase. First milestone is Phase 0 (scaffolding).

## Original planning doc

[KSP_Planner_PlanningDoc.docx](KSP_Planner_PlanningDoc.docx) — the source material that drove the docs in this folder. Superseded for any point of disagreement by the files under `docs/`.
