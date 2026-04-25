import shutil

import pytest
from seeds import seed_stock

from ksp_planner import db as dblib


@pytest.fixture(scope="session")
def seed_db(tmp_path_factory):
    path = tmp_path_factory.mktemp("db") / "ksp.db"
    seed_stock.seed(path)
    return path


@pytest.fixture
def db(seed_db):
    conn = dblib.connect(seed_db, read_only=True)
    try:
        yield conn
    finally:
        conn.close()


@pytest.fixture
def writable_db(seed_db, tmp_path):
    """Per-test writable copy of seed_db for tests that mutate (e.g. plans)."""
    path = tmp_path / "ksp.db"
    shutil.copy(seed_db, path)
    return path


@pytest.fixture
def web_app(seed_db):
    """FastAPI app instance with deps.get_db overridden to point at seed_db."""
    from fastapi.testclient import TestClient  # noqa: F401  (verify import wires)

    from ksp_planner.web import deps
    from ksp_planner.web.app import app

    def _override_get_db():
        conn = dblib.connect(seed_db, read_only=True)
        try:
            yield conn
        finally:
            conn.close()

    app.dependency_overrides[deps.get_db] = _override_get_db
    yield app
    app.dependency_overrides.pop(deps.get_db, None)


@pytest.fixture
def client(web_app):
    from fastapi.testclient import TestClient

    return TestClient(web_app)
