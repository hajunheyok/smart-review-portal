# Smart Review Test Tracker — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Smart Review 신규 버전 성능 풀테스트를 실시간 공유하고 피드백할 수 있는 웹 기반 도구

**Architecture:** Flask + Flask-SocketIO backend serving a single-page HTML frontend. SQLite for persistence. WebSocket for real-time bidirectional sync. All files under `tracker/` subdirectory within the existing smart-review-portal project.

**Tech Stack:** Python 3.12, Flask 3.x, Flask-SocketIO 5.x, SQLite3 (stdlib), Werkzeug (password hashing), Socket.IO JS client (CDN)

---

## File Structure

```
D:\claude\smart-review-portal\tracker\
├── app.py                 # Flask + SocketIO server, routes, socket events
├── models.py              # SQLite database schema + CRUD operations
├── requirements.txt       # Python dependencies
├── tests/
│   ├── conftest.py        # Pytest fixtures (test client, DB setup)
│   ├── test_auth.py       # Auth endpoint tests
│   ├── test_sessions.py   # Session CRUD tests
│   ├── test_items.py      # Category/item CRUD tests
│   └── test_feedback.py   # Comment + upload tests
├── templates/
│   └── index.html         # Single-page frontend (HTML + CSS + JS)
└── uploads/               # Image uploads (auto-created at runtime)
```

---

### Task 1: Database Schema & Models

**Files:**
- Create: `tracker/models.py`
- Create: `tracker/requirements.txt`
- Create: `tracker/tests/conftest.py`
- Create: `tracker/tests/test_auth.py`

- [ ] **Step 1: Create requirements.txt**

```
flask==3.1.3
flask-socketio==5.6.1
pytest==8.3.5
```

Run: `pip install -r tracker/requirements.txt`

- [ ] **Step 2: Write test fixtures**

Create `tracker/tests/conftest.py`:

```python
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
    yield path
    os.unlink(path)
```

- [ ] **Step 3: Write failing tests for user model**

Create `tracker/tests/test_auth.py`:

```python
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import models


def test_create_user(db):
    user_id = models.create_user(db, "testuser", "password123", "Test User")
    assert user_id is not None
    user = models.get_user_by_username(db, "testuser")
    assert user["username"] == "testuser"
    assert user["display_name"] == "Test User"
    assert user["status"] == "pending"
    assert user["role"] == "viewer"


def test_duplicate_username(db):
    models.create_user(db, "testuser", "pw1", "User 1")
    result = models.create_user(db, "testuser", "pw2", "User 2")
    assert result is None


def test_verify_password(db):
    models.create_user(db, "testuser", "password123", "Test User")
    assert models.verify_password(db, "testuser", "password123") is True
    assert models.verify_password(db, "testuser", "wrongpw") is False


def test_approve_user(db):
    user_id = models.create_user(db, "testuser", "pw", "Test User")
    models.approve_user(db, user_id, "tester")
    user = models.get_user_by_id(db, user_id)
    assert user["status"] == "approved"
    assert user["role"] == "tester"


def test_update_role(db):
    user_id = models.create_user(db, "testuser", "pw", "Test User")
    models.approve_user(db, user_id, "tester")
    models.update_user_role(db, user_id, "reviewer")
    user = models.get_user_by_id(db, user_id)
    assert user["role"] == "reviewer"


def test_first_user_is_admin(db):
    user_id = models.create_user(db, "admin", "pw", "Admin")
    user = models.get_user_by_id(db, user_id)
    assert user["role"] == "admin"
    assert user["status"] == "approved"
```

- [ ] **Step 4: Run tests — verify they fail**

Run: `cd D:\claude\smart-review-portal && python -m pytest tracker/tests/test_auth.py -v`
Expected: FAIL (models module has no functions yet)

- [ ] **Step 5: Implement models.py**

Create `tracker/models.py`:

```python
import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime

SW_VERSION_TEMPLATE = [
    ("Vision PC", "AOIGUI - Halcon", 1),
    ("Vision PC", "AOIGUI - FastRed", 2),
    ("Vision PC", "ONNX Model", 3),
    ("Vision PC", "Base Library", 4),
    ("Vision PC", "Graphic Driver", 5),
    ("Review PC", "Review Station 3", 1),
    ("Review PC", "AI SmartGate V2", 2),
    ("Review PC", "SROCV", 3),
    ("Review PC", "Base Library", 4),
    ("AI Model Management", "AI Model Management Tool", 1),
]

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    display_name TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'viewer',
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'draft',
    created_by INTEGER REFERENCES users(id),
    created_at TEXT NOT NULL,
    completed_at TEXT
);

CREATE TABLE IF NOT EXISTS session_versions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL REFERENCES sessions(id),
    group_name TEXT NOT NULL,
    sw_name TEXT NOT NULL,
    version_value TEXT DEFAULT '',
    sort_order INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS categories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL REFERENCES sessions(id),
    name TEXT NOT NULL,
    description TEXT DEFAULT '',
    sort_order INTEGER DEFAULT 0,
    created_by INTEGER REFERENCES users(id),
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS test_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    category_id INTEGER NOT NULL REFERENCES categories(id),
    name TEXT NOT NULL,
    description TEXT DEFAULT '',
    result TEXT NOT NULL DEFAULT 'pending',
    notes TEXT DEFAULT '',
    sort_order INTEGER DEFAULT 0,
    updated_by INTEGER REFERENCES users(id),
    updated_at TEXT,
    created_by INTEGER REFERENCES users(id),
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS attachments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id INTEGER REFERENCES test_items(id),
    comment_id INTEGER REFERENCES comments(id),
    filename TEXT NOT NULL,
    original_name TEXT NOT NULL,
    created_by INTEGER REFERENCES users(id),
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS comments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id INTEGER NOT NULL REFERENCES test_items(id),
    parent_id INTEGER REFERENCES comments(id),
    content TEXT NOT NULL,
    created_by INTEGER REFERENCES users(id),
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS notifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id),
    type TEXT NOT NULL,
    message TEXT NOT NULL,
    target_item_id INTEGER REFERENCES test_items(id),
    is_read INTEGER DEFAULT 0,
    created_at TEXT NOT NULL
);
"""


def _conn(db_path):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def init_db(db_path):
    conn = _conn(db_path)
    conn.executescript(SCHEMA)
    conn.commit()
    conn.close()


# ── Users ──

def create_user(db_path, username, password, display_name):
    conn = _conn(db_path)
    try:
        count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        role = "admin" if count == 0 else "viewer"
        status = "approved" if count == 0 else "pending"
        cur = conn.execute(
            "INSERT INTO users (username, password_hash, display_name, role, status, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (username, generate_password_hash(password), display_name, role, status, _now()),
        )
        conn.commit()
        return cur.lastrowid
    except sqlite3.IntegrityError:
        return None
    finally:
        conn.close()


def get_user_by_username(db_path, username):
    conn = _conn(db_path)
    row = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_user_by_id(db_path, user_id):
    conn = _conn(db_path)
    row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def verify_password(db_path, username, password):
    user = get_user_by_username(db_path, username)
    if not user:
        return False
    return check_password_hash(user["password_hash"], password)


def approve_user(db_path, user_id, role):
    conn = _conn(db_path)
    conn.execute("UPDATE users SET status = 'approved', role = ? WHERE id = ?", (role, user_id))
    conn.commit()
    conn.close()


def update_user_role(db_path, user_id, role):
    conn = _conn(db_path)
    conn.execute("UPDATE users SET role = ? WHERE id = ?", (role, user_id))
    conn.commit()
    conn.close()


def get_all_users(db_path):
    conn = _conn(db_path)
    rows = conn.execute("SELECT id, username, display_name, role, status, created_at FROM users ORDER BY created_at").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_pending_users(db_path):
    conn = _conn(db_path)
    rows = conn.execute("SELECT id, username, display_name, created_at FROM users WHERE status = 'pending'").fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ── Sessions ──

def create_session(db_path, name, created_by):
    conn = _conn(db_path)
    cur = conn.execute(
        "INSERT INTO sessions (name, status, created_by, created_at) VALUES (?, 'draft', ?, ?)",
        (name, created_by, _now()),
    )
    session_id = cur.lastrowid
    for group_name, sw_name, sort_order in SW_VERSION_TEMPLATE:
        conn.execute(
            "INSERT INTO session_versions (session_id, group_name, sw_name, version_value, sort_order) VALUES (?, ?, ?, '', ?)",
            (session_id, group_name, sw_name, sort_order),
        )
    conn.commit()
    conn.close()
    return session_id


def get_session(db_path, session_id):
    conn = _conn(db_path)
    row = conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
    if not row:
        conn.close()
        return None
    session = dict(row)
    versions = conn.execute(
        "SELECT id, group_name, sw_name, version_value, sort_order FROM session_versions WHERE session_id = ? ORDER BY group_name, sort_order",
        (session_id,),
    ).fetchall()
    session["versions"] = [dict(v) for v in versions]
    conn.close()
    return session


def get_sessions_by_status(db_path, statuses):
    conn = _conn(db_path)
    placeholders = ",".join("?" for _ in statuses)
    rows = conn.execute(
        f"SELECT * FROM sessions WHERE status IN ({placeholders}) ORDER BY created_at DESC",
        statuses,
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def update_session_status(db_path, session_id, status):
    conn = _conn(db_path)
    extra = ""
    params = [status, session_id]
    if status == "completed":
        extra = ", completed_at = ?"
        params = [status, _now(), session_id]
    conn.execute(f"UPDATE sessions SET status = ?{extra} WHERE id = ?", params)
    conn.commit()
    conn.close()


def update_session_version(db_path, version_id, version_value):
    conn = _conn(db_path)
    conn.execute("UPDATE session_versions SET version_value = ? WHERE id = ?", (version_value, version_id))
    conn.commit()
    conn.close()


# ── Categories ──

def create_category(db_path, session_id, name, description, created_by):
    conn = _conn(db_path)
    max_order = conn.execute(
        "SELECT COALESCE(MAX(sort_order), -1) FROM categories WHERE session_id = ?", (session_id,)
    ).fetchone()[0]
    cur = conn.execute(
        "INSERT INTO categories (session_id, name, description, sort_order, created_by, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (session_id, name, description, max_order + 1, created_by, _now()),
    )
    conn.commit()
    cat_id = cur.lastrowid
    conn.close()
    return cat_id


def get_categories(db_path, session_id):
    conn = _conn(db_path)
    rows = conn.execute(
        "SELECT * FROM categories WHERE session_id = ? ORDER BY sort_order", (session_id,)
    ).fetchall()
    result = []
    for row in rows:
        cat = dict(row)
        items = conn.execute(
            "SELECT * FROM test_items WHERE category_id = ? ORDER BY sort_order", (cat["id"],)
        ).fetchall()
        cat["items"] = [dict(i) for i in items]
        result.append(cat)
    conn.close()
    return result


def update_category(db_path, category_id, name, description):
    conn = _conn(db_path)
    conn.execute("UPDATE categories SET name = ?, description = ? WHERE id = ?", (name, description, category_id))
    conn.commit()
    conn.close()


def delete_category(db_path, category_id):
    conn = _conn(db_path)
    conn.execute("DELETE FROM comments WHERE item_id IN (SELECT id FROM test_items WHERE category_id = ?)", (category_id,))
    conn.execute("DELETE FROM attachments WHERE item_id IN (SELECT id FROM test_items WHERE category_id = ?)", (category_id,))
    conn.execute("DELETE FROM test_items WHERE category_id = ?", (category_id,))
    conn.execute("DELETE FROM categories WHERE id = ?", (category_id,))
    conn.commit()
    conn.close()


def reorder_categories(db_path, ordered_ids):
    conn = _conn(db_path)
    for i, cid in enumerate(ordered_ids):
        conn.execute("UPDATE categories SET sort_order = ? WHERE id = ?", (i, cid))
    conn.commit()
    conn.close()


# ── Test Items ──

def create_test_item(db_path, category_id, name, description, created_by):
    conn = _conn(db_path)
    max_order = conn.execute(
        "SELECT COALESCE(MAX(sort_order), -1) FROM test_items WHERE category_id = ?", (category_id,)
    ).fetchone()[0]
    cur = conn.execute(
        "INSERT INTO test_items (category_id, name, description, result, notes, sort_order, created_by, created_at) VALUES (?, ?, ?, 'pending', '', ?, ?, ?)",
        (category_id, name, description, max_order + 1, created_by, _now()),
    )
    conn.commit()
    item_id = cur.lastrowid
    conn.close()
    return item_id


def update_test_item(db_path, item_id, **kwargs):
    conn = _conn(db_path)
    allowed = {"name", "description", "result", "notes", "sort_order"}
    sets = []
    vals = []
    for k, v in kwargs.items():
        if k in allowed:
            sets.append(f"{k} = ?")
            vals.append(v)
    if "updated_by" in kwargs:
        sets.append("updated_by = ?")
        vals.append(kwargs["updated_by"])
    sets.append("updated_at = ?")
    vals.append(_now())
    vals.append(item_id)
    conn.execute(f"UPDATE test_items SET {', '.join(sets)} WHERE id = ?", vals)
    conn.commit()
    conn.close()


def delete_test_item(db_path, item_id):
    conn = _conn(db_path)
    conn.execute("DELETE FROM comments WHERE item_id = ?", (item_id,))
    conn.execute("DELETE FROM attachments WHERE item_id = ?", (item_id,))
    conn.execute("DELETE FROM test_items WHERE id = ?", (item_id,))
    conn.commit()
    conn.close()


def reorder_items(db_path, ordered_ids):
    conn = _conn(db_path)
    for i, iid in enumerate(ordered_ids):
        conn.execute("UPDATE test_items SET sort_order = ? WHERE id = ?", (i, iid))
    conn.commit()
    conn.close()


def get_test_item(db_path, item_id):
    conn = _conn(db_path)
    row = conn.execute("SELECT * FROM test_items WHERE id = ?", (item_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


# ── Comments ──

def create_comment(db_path, item_id, content, created_by, parent_id=None):
    conn = _conn(db_path)
    cur = conn.execute(
        "INSERT INTO comments (item_id, parent_id, content, created_by, created_at) VALUES (?, ?, ?, ?, ?)",
        (item_id, parent_id, content, created_by, _now()),
    )
    conn.commit()
    comment_id = cur.lastrowid
    conn.close()
    return comment_id


def get_comments(db_path, item_id):
    conn = _conn(db_path)
    rows = conn.execute(
        "SELECT c.*, u.display_name as author_name FROM comments c JOIN users u ON c.created_by = u.id WHERE c.item_id = ? ORDER BY c.created_at",
        (item_id,),
    ).fetchall()
    comments = [dict(r) for r in rows]
    for comment in comments:
        atts = conn.execute(
            "SELECT id, filename, original_name, created_at FROM attachments WHERE comment_id = ?", (comment["id"],)
        ).fetchall()
        comment["attachments"] = [dict(a) for a in atts]
    conn.close()
    return comments


# ── Attachments ──

def create_attachment(db_path, filename, original_name, created_by, item_id=None, comment_id=None):
    conn = _conn(db_path)
    cur = conn.execute(
        "INSERT INTO attachments (item_id, comment_id, filename, original_name, created_by, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (item_id, comment_id, filename, original_name, created_by, _now()),
    )
    conn.commit()
    att_id = cur.lastrowid
    conn.close()
    return att_id


def get_item_attachments(db_path, item_id):
    conn = _conn(db_path)
    rows = conn.execute(
        "SELECT id, filename, original_name, created_at FROM attachments WHERE item_id = ? AND comment_id IS NULL ORDER BY created_at",
        (item_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ── Notifications ──

def create_notification(db_path, user_id, ntype, message, target_item_id=None):
    conn = _conn(db_path)
    conn.execute(
        "INSERT INTO notifications (user_id, type, message, target_item_id, created_at) VALUES (?, ?, ?, ?, ?)",
        (user_id, ntype, message, target_item_id, _now()),
    )
    conn.commit()
    conn.close()


def get_unread_notifications(db_path, user_id):
    conn = _conn(db_path)
    rows = conn.execute(
        "SELECT * FROM notifications WHERE user_id = ? AND is_read = 0 ORDER BY created_at DESC", (user_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def mark_notifications_read(db_path, user_id):
    conn = _conn(db_path)
    conn.execute("UPDATE notifications SET is_read = 1 WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()


# ── Template Copy ──

def copy_session_structure(db_path, source_session_id, new_name, created_by):
    new_session_id = create_session(db_path, new_name, created_by)
    conn = _conn(db_path)
    src_versions = conn.execute(
        "SELECT group_name, sw_name, sort_order FROM session_versions WHERE session_id = ?", (source_session_id,)
    ).fetchall()
    conn.execute("DELETE FROM session_versions WHERE session_id = ?", (new_session_id,))
    for v in src_versions:
        conn.execute(
            "INSERT INTO session_versions (session_id, group_name, sw_name, version_value, sort_order) VALUES (?, ?, ?, '', ?)",
            (new_session_id, v["group_name"], v["sw_name"], v["sort_order"]),
        )
    categories = conn.execute(
        "SELECT id, name, description, sort_order FROM categories WHERE session_id = ? ORDER BY sort_order",
        (source_session_id,),
    ).fetchall()
    for cat in categories:
        cur = conn.execute(
            "INSERT INTO categories (session_id, name, description, sort_order, created_by, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (new_session_id, cat["name"], cat["description"], cat["sort_order"], created_by, _now()),
        )
        new_cat_id = cur.lastrowid
        items = conn.execute(
            "SELECT name, description, sort_order FROM test_items WHERE category_id = ? ORDER BY sort_order",
            (cat["id"],),
        ).fetchall()
        for item in items:
            conn.execute(
                "INSERT INTO test_items (category_id, name, description, result, notes, sort_order, created_by, created_at) VALUES (?, ?, ?, 'pending', '', ?, ?, ?)",
                (new_cat_id, item["name"], item["description"], item["sort_order"], created_by, _now()),
            )
    conn.commit()
    conn.close()
    return new_session_id
```

- [ ] **Step 6: Run tests — verify they pass**

Run: `cd D:\claude\smart-review-portal && python -m pytest tracker/tests/test_auth.py -v`
Expected: All 6 tests PASS

- [ ] **Step 7: Commit**

```bash
git add tracker/models.py tracker/requirements.txt tracker/tests/
git commit -m "feat: add database schema and models for test tracker"
```

---

### Task 2: Flask App & Auth Routes

**Files:**
- Create: `tracker/app.py`
- Create: `tracker/tests/test_auth_routes.py`

- [ ] **Step 1: Write failing auth route tests**

Create `tracker/tests/test_auth_routes.py`:

```python
import os
import sys
import json
import tempfile
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


@pytest.fixture
def client():
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)

    os.environ["TRACKER_DB"] = db_path
    import app as tracker_app
    tracker_app.app.config["TESTING"] = True
    tracker_app.DB_PATH = db_path

    import models
    models.init_db(db_path)

    with tracker_app.app.test_client() as c:
        yield c

    os.unlink(db_path)


def test_register(client):
    resp = client.post("/api/auth/register", json={
        "username": "admin", "password": "pw123", "display_name": "Admin User"
    })
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["role"] == "admin"


def test_register_duplicate(client):
    client.post("/api/auth/register", json={
        "username": "admin", "password": "pw", "display_name": "A"
    })
    resp = client.post("/api/auth/register", json={
        "username": "admin", "password": "pw2", "display_name": "B"
    })
    assert resp.status_code == 409


def test_login_success(client):
    client.post("/api/auth/register", json={
        "username": "admin", "password": "pw123", "display_name": "Admin"
    })
    resp = client.post("/api/auth/login", json={
        "username": "admin", "password": "pw123"
    })
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["username"] == "admin"


def test_login_pending_user(client):
    client.post("/api/auth/register", json={
        "username": "admin", "password": "pw", "display_name": "Admin"
    })
    client.post("/api/auth/register", json={
        "username": "user2", "password": "pw", "display_name": "User 2"
    })
    resp = client.post("/api/auth/login", json={
        "username": "user2", "password": "pw"
    })
    assert resp.status_code == 403


def test_admin_approve_user(client):
    client.post("/api/auth/register", json={
        "username": "admin", "password": "pw", "display_name": "Admin"
    })
    client.post("/api/auth/login", json={"username": "admin", "password": "pw"})
    client.post("/api/auth/register", json={
        "username": "user2", "password": "pw", "display_name": "User 2"
    })
    resp = client.post("/api/admin/approve", json={
        "user_id": 2, "role": "tester"
    })
    assert resp.status_code == 200


def test_non_admin_cannot_approve(client):
    client.post("/api/auth/register", json={
        "username": "admin", "password": "pw", "display_name": "Admin"
    })
    client.post("/api/auth/register", json={
        "username": "user2", "password": "pw", "display_name": "User 2"
    })
    # Approve user2 as tester first
    client.post("/api/auth/login", json={"username": "admin", "password": "pw"})
    client.post("/api/admin/approve", json={"user_id": 2, "role": "tester"})
    # Login as user2, try to approve
    client.post("/api/auth/login", json={"username": "user2", "password": "pw"})
    resp = client.post("/api/admin/approve", json={"user_id": 2, "role": "reviewer"})
    assert resp.status_code == 403
```

- [ ] **Step 2: Run tests — verify they fail**

Run: `cd D:\claude\smart-review-portal && python -m pytest tracker/tests/test_auth_routes.py -v`
Expected: FAIL (no app module)

- [ ] **Step 3: Implement app.py with auth routes**

Create `tracker/app.py`:

```python
import os
import sys
import json
import uuid
from datetime import datetime
from flask import Flask, request, jsonify, session, send_from_directory, render_template
from flask_socketio import SocketIO, emit, join_room, leave_room
from werkzeug.utils import secure_filename

import models

def get_exe_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))

BASE_DIR = get_exe_dir()
DB_PATH = os.environ.get("TRACKER_DB", os.path.join(BASE_DIR, "tracker.db"))
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "bmp", "webp"}
MAX_UPLOAD_SIZE = 10 * 1024 * 1024  # 10MB

app = Flask(__name__, template_folder=os.path.join(BASE_DIR, "templates"))
app.secret_key = os.environ.get("SECRET_KEY", "smart-review-tracker-secret-key-2026")
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_SIZE

socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

os.makedirs(UPLOAD_DIR, exist_ok=True)

online_users = {}  # sid -> {user_id, display_name}


def require_auth(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        user_id = session.get("user_id")
        if not user_id:
            return jsonify({"error": "Unauthorized"}), 401
        user = models.get_user_by_id(DB_PATH, user_id)
        if not user or user["status"] != "approved":
            return jsonify({"error": "Unauthorized"}), 401
        request.user = user
        return f(*args, **kwargs)
    return decorated


def require_role(min_role):
    role_levels = {"viewer": 0, "tester": 1, "reviewer": 2, "admin": 3}
    def decorator(f):
        from functools import wraps
        @wraps(f)
        def decorated(*args, **kwargs):
            user = request.user
            if role_levels.get(user["role"], 0) < role_levels.get(min_role, 0):
                return jsonify({"error": "Forbidden"}), 403
            return f(*args, **kwargs)
        return decorated
    return decorator


# ── Auth Routes ──

@app.route("/api/auth/register", methods=["POST"])
def register():
    data = request.get_json()
    username = data.get("username", "").strip()
    password = data.get("password", "")
    display_name = data.get("display_name", "").strip()
    if not username or not password or not display_name:
        return jsonify({"error": "Missing fields"}), 400
    user_id = models.create_user(DB_PATH, username, password, display_name)
    if user_id is None:
        return jsonify({"error": "Username taken"}), 409
    user = models.get_user_by_id(DB_PATH, user_id)
    if user["status"] == "approved":
        session["user_id"] = user_id
    return jsonify({
        "id": user["id"], "username": user["username"],
        "display_name": user["display_name"], "role": user["role"],
        "status": user["status"],
    })


@app.route("/api/auth/login", methods=["POST"])
def login():
    data = request.get_json()
    username = data.get("username", "")
    password = data.get("password", "")
    if not models.verify_password(DB_PATH, username, password):
        return jsonify({"error": "Invalid credentials"}), 401
    user = models.get_user_by_username(DB_PATH, username)
    if user["status"] == "pending":
        return jsonify({"error": "Pending approval"}), 403
    session["user_id"] = user["id"]
    return jsonify({
        "id": user["id"], "username": user["username"],
        "display_name": user["display_name"], "role": user["role"],
    })


@app.route("/api/auth/logout", methods=["POST"])
def logout():
    session.clear()
    return jsonify({"status": "ok"})


@app.route("/api/auth/me", methods=["GET"])
def me():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401
    user = models.get_user_by_id(DB_PATH, user_id)
    if not user or user["status"] != "approved":
        return jsonify({"error": "Not authorized"}), 401
    return jsonify({
        "id": user["id"], "username": user["username"],
        "display_name": user["display_name"], "role": user["role"],
    })


# ── Admin Routes ──

@app.route("/api/admin/users", methods=["GET"])
@require_auth
@require_role("admin")
def admin_users():
    return jsonify(models.get_all_users(DB_PATH))


@app.route("/api/admin/pending", methods=["GET"])
@require_auth
@require_role("admin")
def admin_pending():
    return jsonify(models.get_pending_users(DB_PATH))


@app.route("/api/admin/approve", methods=["POST"])
@require_auth
@require_role("admin")
def admin_approve():
    data = request.get_json()
    user_id = data.get("user_id")
    role = data.get("role", "viewer")
    if role not in ("viewer", "tester", "reviewer", "admin"):
        return jsonify({"error": "Invalid role"}), 400
    models.approve_user(DB_PATH, user_id, role)
    return jsonify({"status": "approved"})


@app.route("/api/admin/role", methods=["POST"])
@require_auth
@require_role("admin")
def admin_update_role():
    data = request.get_json()
    user_id = data.get("user_id")
    role = data.get("role")
    if role not in ("viewer", "tester", "reviewer", "admin"):
        return jsonify({"error": "Invalid role"}), 400
    models.update_user_role(DB_PATH, user_id, role)
    return jsonify({"status": "updated"})


# ── Session Routes ──

@app.route("/api/sessions", methods=["GET"])
@require_auth
def list_sessions():
    active = models.get_sessions_by_status(DB_PATH, ["draft", "in_progress"])
    archived = models.get_sessions_by_status(DB_PATH, ["completed"])
    return jsonify({"active": active, "archived": archived})


@app.route("/api/sessions", methods=["POST"])
@require_auth
@require_role("reviewer")
def create_session_route():
    data = request.get_json()
    name = data.get("name", "").strip()
    if not name:
        return jsonify({"error": "Name required"}), 400
    template_id = data.get("template_id")
    if template_id:
        session_id = models.copy_session_structure(DB_PATH, template_id, name, request.user["id"])
    else:
        session_id = models.create_session(DB_PATH, name, request.user["id"])
    s = models.get_session(DB_PATH, session_id)
    socketio.emit("session_created", s, to="tracker")
    return jsonify(s)


@app.route("/api/sessions/<int:session_id>", methods=["GET"])
@require_auth
def get_session_route(session_id):
    s = models.get_session(DB_PATH, session_id)
    if not s:
        return jsonify({"error": "Not found"}), 404
    s["categories"] = models.get_categories(DB_PATH, session_id)
    return jsonify(s)


@app.route("/api/sessions/<int:session_id>/status", methods=["PUT"])
@require_auth
@require_role("reviewer")
def update_session_status_route(session_id):
    data = request.get_json()
    new_status = data.get("status")
    if new_status not in ("draft", "in_progress", "completed"):
        return jsonify({"error": "Invalid status"}), 400
    s = models.get_session(DB_PATH, session_id)
    if not s:
        return jsonify({"error": "Not found"}), 404
    if new_status == "in_progress" and s["status"] == "completed":
        if request.user["role"] != "admin":
            return jsonify({"error": "Only admin can reopen"}), 403
    models.update_session_status(DB_PATH, session_id, new_status)
    socketio.emit("session_updated", {"id": session_id, "status": new_status}, to="tracker")
    return jsonify({"status": new_status})


@app.route("/api/sessions/<int:session_id>/versions/<int:version_id>", methods=["PUT"])
@require_auth
@require_role("reviewer")
def update_version_route(session_id, version_id):
    data = request.get_json()
    models.update_session_version(DB_PATH, version_id, data.get("version_value", ""))
    socketio.emit("version_updated", {
        "session_id": session_id, "version_id": version_id,
        "version_value": data.get("version_value", ""),
    }, to="tracker")
    return jsonify({"status": "updated"})


# ── Category Routes ──

@app.route("/api/sessions/<int:session_id>/categories", methods=["POST"])
@require_auth
@require_role("reviewer")
def create_category_route(session_id):
    data = request.get_json()
    cat_id = models.create_category(DB_PATH, session_id, data.get("name", ""), data.get("description", ""), request.user["id"])
    cats = models.get_categories(DB_PATH, session_id)
    socketio.emit("categories_updated", {"session_id": session_id, "categories": cats}, to="tracker")
    return jsonify({"id": cat_id})


@app.route("/api/categories/<int:category_id>", methods=["PUT"])
@require_auth
@require_role("reviewer")
def update_category_route(category_id):
    data = request.get_json()
    models.update_category(DB_PATH, category_id, data.get("name", ""), data.get("description", ""))
    return jsonify({"status": "updated"})


@app.route("/api/categories/<int:category_id>", methods=["DELETE"])
@require_auth
@require_role("reviewer")
def delete_category_route(category_id):
    models.delete_category(DB_PATH, category_id)
    return jsonify({"status": "deleted"})


@app.route("/api/sessions/<int:session_id>/categories/reorder", methods=["PUT"])
@require_auth
@require_role("reviewer")
def reorder_categories_route(session_id):
    data = request.get_json()
    models.reorder_categories(DB_PATH, data.get("ordered_ids", []))
    socketio.emit("categories_reordered", {"session_id": session_id, "ordered_ids": data.get("ordered_ids", [])}, to="tracker")
    return jsonify({"status": "reordered"})


# ── Test Item Routes ──

@app.route("/api/categories/<int:category_id>/items", methods=["POST"])
@require_auth
@require_role("reviewer")
def create_item_route(category_id):
    data = request.get_json()
    item_id = models.create_test_item(DB_PATH, category_id, data.get("name", ""), data.get("description", ""), request.user["id"])
    item = models.get_test_item(DB_PATH, item_id)
    socketio.emit("item_created", {"category_id": category_id, "item": item}, to="tracker")
    return jsonify(item)


@app.route("/api/items/<int:item_id>", methods=["PUT"])
@require_auth
@require_role("tester")
def update_item_route(item_id):
    data = request.get_json()
    data["updated_by"] = request.user["id"]
    models.update_test_item(DB_PATH, item_id, **data)
    item = models.get_test_item(DB_PATH, item_id)
    socketio.emit("item_updated", item, to="tracker")
    return jsonify(item)


@app.route("/api/items/<int:item_id>", methods=["DELETE"])
@require_auth
@require_role("reviewer")
def delete_item_route(item_id):
    models.delete_test_item(DB_PATH, item_id)
    socketio.emit("item_deleted", {"id": item_id}, to="tracker")
    return jsonify({"status": "deleted"})


@app.route("/api/categories/<int:category_id>/items/reorder", methods=["PUT"])
@require_auth
@require_role("reviewer")
def reorder_items_route(category_id):
    data = request.get_json()
    models.reorder_items(DB_PATH, data.get("ordered_ids", []))
    return jsonify({"status": "reordered"})


# ── Comment Routes ──

@app.route("/api/items/<int:item_id>/comments", methods=["GET"])
@require_auth
def get_comments_route(item_id):
    return jsonify(models.get_comments(DB_PATH, item_id))


@app.route("/api/items/<int:item_id>/comments", methods=["POST"])
@require_auth
@require_role("tester")
def create_comment_route(item_id):
    data = request.get_json()
    comment_id = models.create_comment(DB_PATH, item_id, data.get("content", ""), request.user["id"], data.get("parent_id"))
    comments = models.get_comments(DB_PATH, item_id)
    socketio.emit("comments_updated", {"item_id": item_id, "comments": comments}, to="tracker")
    return jsonify({"id": comment_id})


# ── Upload Routes ──

@app.route("/api/upload", methods=["POST"])
@require_auth
@require_role("tester")
def upload_file():
    if "file" not in request.files:
        return jsonify({"error": "No file"}), 400
    f = request.files["file"]
    if not f.filename:
        return jsonify({"error": "No filename"}), 400
    ext = f.filename.rsplit(".", 1)[-1].lower() if "." in f.filename else ""
    if ext not in ALLOWED_EXTENSIONS:
        return jsonify({"error": "Invalid file type"}), 400
    filename = f"{uuid.uuid4().hex}.{ext}"
    f.save(os.path.join(UPLOAD_DIR, filename))
    item_id = request.form.get("item_id", type=int)
    comment_id = request.form.get("comment_id", type=int)
    att_id = models.create_attachment(DB_PATH, filename, f.filename, request.user["id"], item_id=item_id, comment_id=comment_id)
    return jsonify({"id": att_id, "filename": filename, "original_name": f.filename, "url": f"/uploads/{filename}"})


@app.route("/uploads/<filename>")
def serve_upload(filename):
    return send_from_directory(UPLOAD_DIR, filename)


# ── Notification Routes ──

@app.route("/api/notifications", methods=["GET"])
@require_auth
def get_notifications():
    return jsonify(models.get_unread_notifications(DB_PATH, request.user["id"]))


@app.route("/api/notifications/read", methods=["POST"])
@require_auth
def mark_read():
    models.mark_notifications_read(DB_PATH, request.user["id"])
    return jsonify({"status": "ok"})


# ── WebSocket Events ──

@socketio.on("connect")
def on_connect():
    user_id = session.get("user_id")
    if user_id:
        user = models.get_user_by_id(DB_PATH, user_id)
        if user and user["status"] == "approved":
            join_room("tracker")
            online_users[request.sid] = {"user_id": user_id, "display_name": user["display_name"]}
            emit("online_users", list(online_users.values()), to="tracker")


@socketio.on("disconnect")
def on_disconnect():
    if request.sid in online_users:
        del online_users[request.sid]
        emit("online_users", list(online_users.values()), to="tracker")


# ── Main Page ──

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/health")
def health():
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    models.init_db(DB_PATH)
    print("=" * 50)
    print("  Smart Review Test Tracker")
    print("=" * 50)
    print(f"  URL: http://localhost:9091")
    print(f"  DB:  {DB_PATH}")
    print("=" * 50)
    socketio.run(app, host="0.0.0.0", port=9091, debug=False, allow_unsafe_werkzeug=True)
```

- [ ] **Step 4: Create minimal template placeholder**

Create `tracker/templates/index.html`:

```html
<!DOCTYPE html>
<html><head><title>Smart Review Test Tracker</title></head>
<body><h1>Smart Review Test Tracker</h1><p>Loading...</p></body>
</html>
```

- [ ] **Step 5: Run auth route tests — verify they pass**

Run: `cd D:\claude\smart-review-portal && python -m pytest tracker/tests/test_auth_routes.py -v`
Expected: All 6 tests PASS

- [ ] **Step 6: Commit**

```bash
git add tracker/app.py tracker/templates/index.html
git commit -m "feat: add Flask app with auth, session, item, comment, upload routes"
```

---

### Task 3: Session & Item API Tests

**Files:**
- Create: `tracker/tests/test_sessions.py`
- Create: `tracker/tests/test_items.py`

- [ ] **Step 1: Write session tests**

Create `tracker/tests/test_sessions.py`:

```python
import os
import sys
import tempfile
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


@pytest.fixture
def client():
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.environ["TRACKER_DB"] = db_path
    import app as tracker_app
    tracker_app.app.config["TESTING"] = True
    tracker_app.DB_PATH = db_path
    import models
    models.init_db(db_path)
    with tracker_app.app.test_client() as c:
        c.post("/api/auth/register", json={"username": "admin", "password": "pw", "display_name": "Admin"})
        c.post("/api/auth/login", json={"username": "admin", "password": "pw"})
        yield c
    os.unlink(db_path)


def test_create_session(client):
    resp = client.post("/api/sessions", json={"name": "SR 2.10 Test"})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["name"] == "SR 2.10 Test"
    assert data["status"] == "draft"
    assert len(data["versions"]) == 10


def test_session_has_correct_sw_structure(client):
    resp = client.post("/api/sessions", json={"name": "Test"})
    versions = resp.get_json()["versions"]
    groups = {}
    for v in versions:
        groups.setdefault(v["group_name"], []).append(v["sw_name"])
    assert len(groups["Vision PC"]) == 5
    assert len(groups["Review PC"]) == 4
    assert len(groups["AI Model Management"]) == 1
    assert "Base Library" in groups["Review PC"]


def test_session_status_flow(client):
    resp = client.post("/api/sessions", json={"name": "Test"})
    sid = resp.get_json()["id"]
    client.put(f"/api/sessions/{sid}/status", json={"status": "in_progress"})
    resp = client.get(f"/api/sessions/{sid}")
    assert resp.get_json()["status"] == "in_progress"
    client.put(f"/api/sessions/{sid}/status", json={"status": "completed"})
    resp = client.get(f"/api/sessions/{sid}")
    assert resp.get_json()["status"] == "completed"


def test_update_version(client):
    resp = client.post("/api/sessions", json={"name": "Test"})
    versions = resp.get_json()["versions"]
    vid = versions[0]["id"]
    client.put(f"/api/sessions/1/versions/{vid}", json={"version_value": "KY_AOI_2.10.2.0"})
    resp = client.get("/api/sessions/1")
    updated = [v for v in resp.get_json()["versions"] if v["id"] == vid][0]
    assert updated["version_value"] == "KY_AOI_2.10.2.0"


def test_template_copy(client):
    resp = client.post("/api/sessions", json={"name": "Original"})
    sid = resp.get_json()["id"]
    client.post(f"/api/sessions/{sid}/categories", json={"name": "Cat1", "description": "desc"})
    resp = client.post("/api/sessions", json={"name": "Copy", "template_id": sid})
    copy_id = resp.get_json()["id"]
    resp = client.get(f"/api/sessions/{copy_id}")
    data = resp.get_json()
    assert data["name"] == "Copy"
    assert len(data["categories"]) == 1
    assert data["categories"][0]["name"] == "Cat1"
```

- [ ] **Step 2: Write item tests**

Create `tracker/tests/test_items.py`:

```python
import os
import sys
import tempfile
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


@pytest.fixture
def client():
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.environ["TRACKER_DB"] = db_path
    import app as tracker_app
    tracker_app.app.config["TESTING"] = True
    tracker_app.DB_PATH = db_path
    import models
    models.init_db(db_path)
    with tracker_app.app.test_client() as c:
        c.post("/api/auth/register", json={"username": "admin", "password": "pw", "display_name": "Admin"})
        c.post("/api/auth/login", json={"username": "admin", "password": "pw"})
        c.post("/api/sessions", json={"name": "Test Session"})
        yield c
    os.unlink(db_path)


def test_create_category(client):
    resp = client.post("/api/sessions/1/categories", json={"name": "Inspection Accuracy", "description": "검사 정확도"})
    assert resp.status_code == 200


def test_create_item(client):
    client.post("/api/sessions/1/categories", json={"name": "Cat1"})
    resp = client.post("/api/categories/1/items", json={"name": "Solder bridge detection", "description": "Test desc"})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["result"] == "pending"


def test_update_item_result(client):
    client.post("/api/sessions/1/categories", json={"name": "Cat1"})
    client.post("/api/categories/1/items", json={"name": "Test1"})
    resp = client.put("/api/items/1", json={"result": "pass", "notes": "OK"})
    assert resp.status_code == 200
    assert resp.get_json()["result"] == "pass"


def test_delete_item(client):
    client.post("/api/sessions/1/categories", json={"name": "Cat1"})
    client.post("/api/categories/1/items", json={"name": "Test1"})
    resp = client.delete("/api/items/1")
    assert resp.status_code == 200


def test_delete_category_cascades(client):
    client.post("/api/sessions/1/categories", json={"name": "Cat1"})
    client.post("/api/categories/1/items", json={"name": "Item1"})
    client.post("/api/items/1/comments", json={"content": "Comment1"})
    resp = client.delete("/api/categories/1")
    assert resp.status_code == 200
    resp = client.get("/api/sessions/1")
    assert len(resp.get_json()["categories"]) == 0
```

- [ ] **Step 3: Run all tests**

Run: `cd D:\claude\smart-review-portal && python -m pytest tracker/tests/ -v`
Expected: All tests PASS

- [ ] **Step 4: Commit**

```bash
git add tracker/tests/test_sessions.py tracker/tests/test_items.py
git commit -m "test: add session and item API tests"
```

---

### Task 4: Frontend — HTML/CSS/JS Complete Single-Page Application

This is the largest task. The entire frontend is a single `index.html` file with embedded CSS and JS. It includes: login/register, admin panel, session management, test table with inline editing, feedback panel with image paste, real-time sync via Socket.IO, notification bell, and archive view.

**Files:**
- Modify: `tracker/templates/index.html`

- [ ] **Step 1: Build complete frontend**

Replace `tracker/templates/index.html` with the full single-page application. The file structure:

1. **`<head>`** — Meta tags, CDN imports (Socket.IO client, SortableJS for drag-drop), embedded CSS
2. **`<body>`** — Login/register screen, main app layout (sidebar + content + feedback panel)
3. **`<script>`** — All JavaScript: auth flow, Socket.IO client, CRUD operations, drag-drop, image paste, notifications

Key CDN dependencies:
- `https://cdn.socket.io/4.7.5/socket.io.min.js` — Socket.IO client
- `https://cdn.jsdelivr.net/npm/sortablejs@1.15.0/Sortable.min.js` — Drag-and-drop sorting

CSS design approach:
- Clean, modern design with CSS variables for theming
- 3-panel layout: sidebar (280px) + main (flex) + feedback panel (380px, toggleable)
- Color-coded result badges: Pass (green), Fail (red), N/A (gray), Pending (blue-outline)
- Responsive notification bell with red badge counter

JavaScript architecture:
- `state` object holding current session, user, categories
- Socket.IO event handlers that update state and re-render
- REST API calls via `fetch()` with JSON
- Image paste handler on feedback textarea (`paste` event → FormData upload → inline `<img>`)
- SortableJS instances on category and item lists

The complete HTML file will be approximately 1500-2000 lines. It must be written as a single self-contained file with no external dependencies beyond the two CDN scripts.

**Key UI sections:**

```
┌──────────────────────────────────────────────────────────┐
│ [Logo] Smart Review Test Tracker    🔔(3) 👤Admin ⚙️    │
├──────────┬───────────────────────────────┬───────────────┤
│ Sessions │ [Session: SR 2.10 Test]       │ Feedback      │
│          │                               │               │
│ ▶ Active │ 📦 Vision PC                  │ Item: XXX     │
│  └ SR2.10│   AOIGUI-Halcon: v2.10.2.0   │ ───────────── │
│          │   AOIGUI-FastRed: v2.10.2.0   │ User1: text   │
│ 📦Archive│   ...                         │   [image.png] │
│  └ SR2.9 │                               │ User2: reply  │
│          │ ▼ Inspection Accuracy          │               │
│ ──────── │   ☑ Solder bridge  [Pass] ... │ ┌───────────┐ │
│ 👥 Users │   ☐ Component pos  [Fail] ... │ │ Type here  │ │
│ (Admin)  │   ☐ ...                       │ │ 📎 Ctrl+V  │ │
│          │ ▼ AI Performance              │ └───────────┘ │
│          │   ...                         │               │
└──────────┴───────────────────────────────┴───────────────┘
```

This step produces the full file. Due to its size, the implementor should build it in logical sections, testing each in the browser before moving to the next:
1. Login/register screen
2. Main layout shell (sidebar + header)
3. Session list + creation
4. Version info display + editing
5. Category/item table with CRUD
6. Result editing (dropdown + notes)
7. Feedback panel with comments
8. Image paste/upload
9. Socket.IO real-time sync
10. Notifications
11. Archive view + search
12. Admin user management panel
13. Drag-and-drop sorting

- [ ] **Step 2: Start dev server and test manually**

Run: `cd D:\claude\smart-review-portal\tracker && python app.py`

Test in browser at `http://localhost:9091`:
1. Register first user (becomes Admin)
2. Create a test session
3. Verify 10 SW version slots appear (5 Vision + 4 Review + 1 AI Model)
4. Add categories and test items
5. Change results to Pass/Fail
6. Open feedback panel, post a comment
7. Paste an image (Ctrl+V)
8. Open a second browser tab — verify changes appear in real-time

- [ ] **Step 3: Commit**

```bash
git add tracker/templates/index.html
git commit -m "feat: add complete frontend single-page application"
```

---

### Task 5: Archive, Search & Final Polish

**Files:**
- Modify: `tracker/app.py` (add search endpoint)
- Modify: `tracker/templates/index.html` (archive view, search UI)

- [ ] **Step 1: Add search API endpoint**

Add to `tracker/app.py` before the `# ── WebSocket Events ──` section:

```python
@app.route("/api/sessions/search", methods=["GET"])
@require_auth
def search_sessions():
    q = request.args.get("q", "").strip()
    result_filter = request.args.get("result", "")
    date_from = request.args.get("from", "")
    date_to = request.args.get("to", "")
    conn = models._conn(DB_PATH)
    query = "SELECT * FROM sessions WHERE 1=1"
    params = []
    if q:
        query += " AND name LIKE ?"
        params.append(f"%{q}%")
    if date_from:
        query += " AND created_at >= ?"
        params.append(date_from)
    if date_to:
        query += " AND created_at <= ?"
        params.append(date_to + " 23:59:59")
    query += " ORDER BY created_at DESC"
    rows = conn.execute(query, params).fetchall()
    sessions = [dict(r) for r in rows]
    if result_filter:
        filtered = []
        for s in sessions:
            items = conn.execute(
                "SELECT result FROM test_items WHERE category_id IN (SELECT id FROM categories WHERE session_id = ?)",
                (s["id"],),
            ).fetchall()
            if any(i["result"] == result_filter for i in items):
                filtered.append(s)
        sessions = filtered
    conn.close()
    return jsonify(sessions)
```

- [ ] **Step 2: Update frontend with archive search UI**

Add search bar in the archive section of `index.html`:
- Text search input
- Date range picker (from/to)
- Result filter dropdown (All / Pass / Fail / Pending)
- Results update on input change (debounced 300ms)

- [ ] **Step 3: Test archive and search**

1. Complete a test session (status → Completed)
2. Verify it moves to archive
3. Search by name
4. Filter by Fail results
5. Verify read-only mode in archive

- [ ] **Step 4: Commit**

```bash
git add tracker/app.py tracker/templates/index.html
git commit -m "feat: add archive search and filtering"
```

---

### Task 6: Deployment Setup

**Files:**
- Create: `tracker/start_tracker.bat`
- Create: `tracker/TrackerServer.spec` (PyInstaller)

- [ ] **Step 1: Create start script**

Create `tracker/start_tracker.bat`:

```batch
@echo off
title Smart Review Test Tracker
cd /d "%~dp0"
echo ============================================
echo   Smart Review Test Tracker
echo   URL: http://localhost:9091
echo ============================================
echo.

if exist "TrackerServer.exe" (
    TrackerServer.exe
) else (
    python app.py
)

pause
```

- [ ] **Step 2: Create PyInstaller spec**

Create `tracker/TrackerServer.spec`:

```python
# -*- mode: python ; coding: utf-8 -*-
a = Analysis(
    ['app.py'],
    pathex=[],
    binaries=[],
    datas=[('templates', 'templates')],
    hiddenimports=['engineio.async_drivers.threading'],
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, a.binaries, a.datas, [],
    name='TrackerServer',
    debug=False,
    strip=False,
    upx=True,
    console=True,
)
```

- [ ] **Step 3: Build exe (optional — can also run as python app.py)**

Run: `cd D:\claude\smart-review-portal\tracker && pyinstaller TrackerServer.spec --clean`
Expected: `dist/TrackerServer.exe` created

- [ ] **Step 4: Test deployment**

1. Run `start_tracker.bat`
2. Open browser to `http://localhost:9091`
3. Verify all features work
4. Test from another PC on the network: `http://10.4.10.140:9091`

- [ ] **Step 5: Final commit**

```bash
git add tracker/start_tracker.bat tracker/TrackerServer.spec
git commit -m "feat: add deployment scripts for test tracker"
```

---

### Task 7: Run Full Test Suite & Final Verification

- [ ] **Step 1: Run all tests**

Run: `cd D:\claude\smart-review-portal && python -m pytest tracker/tests/ -v --tb=short`
Expected: All tests PASS

- [ ] **Step 2: Manual end-to-end test**

Run the server and verify in browser:

1. **Auth flow**: Register admin → register user2 → admin approves user2 as tester → user2 logs in
2. **Session**: Create "SR 2.10 Full Test" → fill version info → set In Progress
3. **Categories**: Add 2-3 categories → add items under each
4. **Testing**: Set results (Pass/Fail/N/A) → add notes
5. **Feedback**: Post comments with text → paste image (Ctrl+V) → reply to comment
6. **Real-time**: Open 2 browser tabs → verify changes sync instantly
7. **Notifications**: Check bell icon shows new feedback count
8. **Archive**: Set session Completed → verify moves to archive → verify read-only
9. **Search**: Search archived sessions by name, filter by Fail
10. **Template**: Create new session from archived template → verify structure copied
11. **Admin**: Change user role → verify permission changes

- [ ] **Step 3: Final commit with all changes**

```bash
git add -A tracker/
git commit -m "feat: Smart Review Test Tracker complete — real-time test tracking with WebSocket"
```
