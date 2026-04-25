"""Shared Jinja2Templates instance.

Lives in its own module so route handlers can import it at module level
without creating a circular dependency on `app.py` (which itself imports
the routers to register them).
"""

from __future__ import annotations

from pathlib import Path

from fastapi.templating import Jinja2Templates

_TEMPLATES_DIR = Path(__file__).parent / "templates"

templates = Jinja2Templates(directory=_TEMPLATES_DIR)
