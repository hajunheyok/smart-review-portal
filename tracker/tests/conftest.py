import os
import sys
import tempfile
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import models


@pytest.fixture
def db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    models.init_db(path)
    # Pre-seed an admin so subsequent create_user calls are not "first user"
    models.create_user(path, "__admin__", "admin_seed", "System Admin")
    yield path
    os.unlink(path)


@pytest.fixture
def empty_db():
    """A truly empty DB with no pre-seeded users, for first-user tests."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    models.init_db(path)
    yield path
    os.unlink(path)
