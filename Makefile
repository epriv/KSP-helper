.PHONY: help install test test-unit test-cov lint fmt clean seed run

help:
	@echo "Targets:"
	@echo "  install   — sync dependencies (uv sync --group dev)"
	@echo "  test      — run the full test suite"
	@echo "  test-cov  — run tests with coverage report"
	@echo "  lint      — ruff check"
	@echo "  fmt       — ruff format"
	@echo "  clean     — remove caches and build artifacts"
	@echo "  seed      — regenerate ksp.db from stock seed   (Phase 1)"
	@echo "  run       — launch the ksp CLI                  (Phase 4)"

install:
	uv sync --group dev

test:
	uv run pytest

test-cov:
	uv run pytest --cov=ksp_planner --cov-report=term-missing

lint:
	uv run ruff check .

fmt:
	uv run ruff format .

clean:
	rm -rf .pytest_cache .ruff_cache .coverage htmlcov dist build
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
	find . -type d -name "*.egg-info" -prune -exec rm -rf {} +

seed:
	uv run python -m seeds.seed_stock

run:
	uv run ksp
