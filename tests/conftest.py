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
