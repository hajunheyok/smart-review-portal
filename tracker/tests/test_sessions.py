"""
test_sessions.py — API tests for session-related endpoints.
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
        yield c

    os.unlink(db_path)


def test_create_session(client):
    """POST /api/sessions creates a session with name, draft status, and 10 version entries."""
    resp = client.post("/api/sessions", json={"name": "SR 2.10 Test"})
    assert resp.status_code == 201
    data = resp.get_json()
    assert data["name"] == "SR 2.10 Test"
    assert data["status"] == "draft"
    assert len(data["versions"]) == 10


def test_session_has_correct_sw_structure(client):
    """Versions are grouped correctly: Vision PC=5, Review PC=4, AI Model Management=1."""
    resp = client.post("/api/sessions", json={"name": "SW Structure Test"})
    assert resp.status_code == 201
    versions = resp.get_json()["versions"]

    groups = {}
    for v in versions:
        label = v["category_label"]
        groups[label] = groups.get(label, 0) + 1

    assert groups.get("Vision PC") == 5
    assert groups.get("Review PC") == 4
    assert groups.get("AI Model Management") == 1


def test_session_status_flow(client):
    """Session moves through: draft → in_progress → completed."""
    create_resp = client.post("/api/sessions", json={"name": "Status Flow"})
    assert create_resp.status_code == 201
    session_id = create_resp.get_json()["id"]

    # Set to in_progress
    resp = client.put(f"/api/sessions/{session_id}/status", json={"status": "in_progress"})
    assert resp.status_code == 200
    assert resp.get_json()["status"] == "in_progress"

    # Set to completed
    resp = client.put(f"/api/sessions/{session_id}/status", json={"status": "completed"})
    assert resp.status_code == 200
    assert resp.get_json()["status"] == "completed"


def test_update_version(client):
    """PUT /api/sessions/<id>/versions/<vid> updates the version value."""
    create_resp = client.post("/api/sessions", json={"name": "Version Update"})
    assert create_resp.status_code == 201
    sess_data = create_resp.get_json()
    session_id = sess_data["id"]
    first_version_id = sess_data["versions"][0]["id"]

    # Update the first version
    resp = client.put(
        f"/api/sessions/{session_id}/versions/{first_version_id}",
        json={"version_value": "KY_AOI_2.10.2.0"},
    )
    assert resp.status_code == 200

    # GET session and verify
    get_resp = client.get(f"/api/sessions/{session_id}")
    assert get_resp.status_code == 200
    versions = get_resp.get_json()["versions"]
    updated = next(v for v in versions if v["id"] == first_version_id)
    assert updated["version_value"] == "KY_AOI_2.10.2.0"


def test_template_copy(client):
    """Creating a session with template_id copies category structure."""
    # Create the original session and add a category
    orig_resp = client.post("/api/sessions", json={"name": "Original"})
    assert orig_resp.status_code == 201
    orig_id = orig_resp.get_json()["id"]

    cat_resp = client.post(f"/api/sessions/{orig_id}/categories", json={"name": "Cat1"})
    assert cat_resp.status_code == 201

    # Create copy using template_id
    copy_resp = client.post("/api/sessions", json={"name": "Copy Session", "template_id": orig_id})
    assert copy_resp.status_code == 201
    copy_id = copy_resp.get_json()["id"]

    # GET the copy and verify the category is present
    get_resp = client.get(f"/api/sessions/{copy_id}")
    assert get_resp.status_code == 200
    categories = get_resp.get_json()["categories"]
    assert len(categories) == 1
    assert categories[0]["name"] == "Cat1"
