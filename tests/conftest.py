"""앱은 import할 때 DATABASE_URL로 DB에 연결하므로, 시험용 SQLite 주소를 먼저 정한다."""
import os
import tempfile
from pathlib import Path

_directory = tempfile.mkdtemp(prefix="todo-test-")
os.environ["DATABASE_URL"] = f"sqlite:///{(Path(_directory) / 'test.db').as_posix()}"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.db import Base, engine  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture
def client():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with TestClient(app) as test_client:
        yield test_client
