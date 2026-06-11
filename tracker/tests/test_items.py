"""
test_items.py — API tests for category and test-item endpoints.
"""
import os
import sys
import tempfile
import importlib
import importlib.util

import pytest

TRACKER_DIR = os.path.join(os.path.dirname(__file__), "..")


def _ensure_tracker_path():
    """Ensure tracker directory is on sys.path so inner imports resolve."""
    abs_dir = os.path.abspath(TRACKER_DIR)
    if abs_dir not in sys.path:
        sys.path.insert(0, abs_dir)


def _load_tracker_app():
    """Load tracker/app.py by absolute path to avoid root app.py collision."""
    _ensure_tracker_path()
    app_path = os.path.abspath(os.path.join(TRACKER_DIR, "app.py"))
    spec = importlib.util.spec_from_file_location("tracker_app", app_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _load_models():
    """Load tracker/models.py by absolute path."""
    _ensure_tracker_path()
    models_path = os.path.abspath(os.path.join(TRACKER_DIR, "models.py"))
    spec = importlib.util.spec_from_file_location("tracker_models", models_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def client():
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.environ["TRACKER_DB"] = db_path

    # Load tracker/app.py and tracker/models.py from their absolute paths
    tracker_app = _load_tracker_app()
    models = _load_models()

    tracker_app.app.config["TESTING"] = True
    tracker_app.DB_PATH = db_path
    models.init_db(db_path)

    with tracker_app.app.test_client() as c:
        # Register first user — automatically becomes admin + approved
        c.post("/api/auth/register", json={"username": "admin", "password": "pw", "display_name": "Admin"})
        c.post("/api/auth/login", json={"username": "admin", "password": "pw"})

        # Create a session for item/category tests to use
        c.post("/api/sessions", json={"name": "Test Session"})

        yield c

    os.unlink(db_path)


def test_create_category(client):
    """POST /api/sessions/1/categories creates a category."""
    resp = client.post("/api/sessions/1/categories", json={"name": "Inspection Accuracy"})
    assert resp.status_code == 201
    data = resp.get_json()
    assert data["name"] == "Inspection Accuracy"


def test_create_item(client):
    """POST /api/categories/1/items creates an item with result='pending'."""
    # Create category first
    cat_resp = client.post("/api/sessions/1/categories", json={"name": "Test Category"})
    assert cat_resp.status_code == 201
    cat_id = cat_resp.get_json()["id"]

    # Create item under the category
    item_resp = client.post(
        f"/api/categories/{cat_id}/items",
        json={"name": "Test Item", "description": "Item description"},
    )
    assert item_resp.status_code == 201
    data = item_resp.get_json()
    assert data["result"] == "pending"
    assert data["name"] == "Test Item"


def test_update_item_result(client):
    """PUT /api/items/<id> updates result and notes."""
    # Create category + item
    cat_resp = client.post("/api/sessions/1/categories", json={"name": "Cat"})
    cat_id = cat_resp.get_json()["id"]
    item_resp = client.post(
        f"/api/categories/{cat_id}/items",
        json={"name": "Item to update", "description": ""},
    )
    item_id = item_resp.get_json()["id"]

    # Update result and notes
    update_resp = client.put(
        f"/api/items/{item_id}",
        json={"result": "pass", "notes": "OK"},
    )
    assert update_resp.status_code == 200
    data = update_resp.get_json()
    assert data["result"] == "pass"
    assert data["notes"] == "OK"


def test_delete_item(client):
    """DELETE /api/items/<id> removes the item."""
    # Create category + item
    cat_resp = client.post("/api/sessions/1/categories", json={"name": "Cat"})
    cat_id = cat_resp.get_json()["id"]
    item_resp = client.post(
        f"/api/categories/{cat_id}/items",
        json={"name": "Item to delete", "description": ""},
    )
    item_id = item_resp.get_json()["id"]

    # Delete the item
    del_resp = client.delete(f"/api/items/{item_id}")
    assert del_resp.status_code == 200
    assert del_resp.get_json()["ok"] is True


def test_delete_category_cascades(client):
    """DELETE /api/categories/<id> cascades to remove items and comments."""
    # Create category
    cat_resp = client.post("/api/sessions/1/categories", json={"name": "Cat to delete"})
    assert cat_resp.status_code == 201
    cat_id = cat_resp.get_json()["id"]

    # Create item
    item_resp = client.post(
        f"/api/categories/{cat_id}/items",
        json={"name": "Child item", "description": ""},
    )
    assert item_resp.status_code == 201
    item_id = item_resp.get_json()["id"]

    # Create a comment on the item
    comment_resp = client.post(
        f"/api/items/{item_id}/comments",
        json={"content": "A comment"},
    )
    assert comment_resp.status_code == 201

    # Delete the category
    del_resp = client.delete(f"/api/categories/{cat_id}")
    assert del_resp.status_code == 200

    # GET session and verify categories list is empty (cascade worked)
    sess_resp = client.get("/api/sessions/1")
    assert sess_resp.status_code == 200
    categories = sess_resp.get_json()["categories"]
    assert categories == []
