import os
import tempfile

import pytest
from fastapi.testclient import TestClient

# PostgreSQL can be selected with RG_TEST_DATABASE_URL. Never reset the app DB.
os.environ["DATABASE_URL"] = os.getenv(
    "RG_TEST_DATABASE_URL",
    "sqlite:///" + tempfile.mktemp(prefix="rg-tests-", suffix=".db"),
)
os.environ["RG_DATA_DIR"] = tempfile.mkdtemp(prefix="rg-test-sources-")

from app.db import Base, engine
from app.main import app


@pytest.fixture
def client():
    Base.metadata.drop_all(engine)
    with TestClient(app) as client:
        yield client
    Base.metadata.drop_all(engine)
