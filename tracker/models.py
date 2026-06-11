"""
models.py — SQLite database layer for Smart Review Test Tracker
"""
import sqlite3
from datetime import datetime, timezone

from werkzeug.security import generate_password_hash, check_password_hash

# ---------------------------------------------------------------------------
# SW version template — 10 entries matching Smart Review portal structure
# ---------------------------------------------------------------------------
SW_VERSION_TEMPLATE = [
    # (category_label, sw_name)
    ("Vision PC", "AOIGUI-Halcon"),
    ("Vision PC", "AOIGUI-FastRed"),
    ("Vision PC", "ONNX Model"),
    ("Vision PC", "Base Library"),
    ("Vision PC", "Graphic Driver"),
    ("Review PC", "Review Station 3"),
    ("Review PC", "AI SmartGate V2"),
    ("Review PC", "SROCV"),
    ("Review PC", "Base Library"),
    ("AI Model Management", "AI Model Management Tool"),
]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _conn(db_path: str) -> sqlite3.Connection:
    """Return an SQLite connection with Row factory, WAL mode, foreign keys."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _now() -> str:
    """Current UTC datetime as ISO-8601 string."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


# ---------------------------------------------------------------------------
# Schema initialisation
# ---------------------------------------------------------------------------

def init_db(db_path: str) -> None:
    """Create all tables if they do not already exist."""
    conn = _conn(db_path)
    with conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            username      TEXT    NOT NULL UNIQUE,
            password_hash TEXT    NOT NULL,
            display_name  TEXT    NOT NULL,
            role          TEXT    NOT NULL DEFAULT 'viewer',
            status        TEXT    NOT NULL DEFAULT 'pending',
            created_at    TEXT    NOT NULL
        );

        CREATE TABLE IF NOT EXISTS sessions (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            name         TEXT    NOT NULL,
            status       TEXT    NOT NULL DEFAULT 'active',
            created_by   TEXT    NOT NULL,
            created_at   TEXT    NOT NULL,
            completed_at TEXT
        );

        CREATE TABLE IF NOT EXISTS session_versions (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id     INTEGER NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
            category_label TEXT    NOT NULL,
            sw_name        TEXT    NOT NULL,
            version_value  TEXT    NOT NULL DEFAULT '',
            sort_order     INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS categories (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id  INTEGER NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
            name        TEXT    NOT NULL,
            description TEXT    NOT NULL DEFAULT '',
            sort_order  INTEGER NOT NULL DEFAULT 0,
            created_by  TEXT    NOT NULL,
            created_at  TEXT    NOT NULL
        );

        CREATE TABLE IF NOT EXISTS test_items (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            category_id INTEGER NOT NULL REFERENCES categories(id) ON DELETE CASCADE,
            name        TEXT    NOT NULL,
            description TEXT    NOT NULL DEFAULT '',
            result      TEXT    NOT NULL DEFAULT 'pending',
            notes       TEXT    NOT NULL DEFAULT '',
            sort_order  INTEGER NOT NULL DEFAULT 0,
            created_by  TEXT    NOT NULL,
            created_at  TEXT    NOT NULL,
            updated_by  TEXT,
            updated_at  TEXT
        );

        CREATE TABLE IF NOT EXISTS attachments (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            filename      TEXT    NOT NULL,
            original_name TEXT    NOT NULL,
            item_id       INTEGER REFERENCES test_items(id) ON DELETE CASCADE,
            comment_id    INTEGER REFERENCES comments(id)   ON DELETE CASCADE,
            created_by    TEXT    NOT NULL,
            created_at    TEXT    NOT NULL
        );

        CREATE TABLE IF NOT EXISTS comments (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            item_id    INTEGER NOT NULL REFERENCES test_items(id) ON DELETE CASCADE,
            parent_id  INTEGER REFERENCES comments(id) ON DELETE CASCADE,
            content    TEXT    NOT NULL,
            created_by TEXT    NOT NULL,
            created_at TEXT    NOT NULL
        );

        CREATE TABLE IF NOT EXISTS notifications (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id        INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            ntype          TEXT    NOT NULL,
            message        TEXT    NOT NULL,
            target_item_id INTEGER REFERENCES test_items(id) ON DELETE SET NULL,
            is_read        INTEGER NOT NULL DEFAULT 0,
            created_at     TEXT    NOT NULL
        );
        """)
    conn.close()


# ---------------------------------------------------------------------------
# User functions
# ---------------------------------------------------------------------------

def create_user(db_path: str, username: str, password: str, display_name: str):
    """
    Hash password with werkzeug and insert a new user.

    The first user in the database automatically gets role='admin' and
    status='approved'. Subsequent users start as role='viewer', status='pending'.

    Returns the new user id, or None if the username already exists.
    """
    conn = _conn(db_path)
    try:
        with conn:
            # Check whether this is the very first user
            row = conn.execute("SELECT COUNT(*) AS cnt FROM users").fetchone()
            is_first = row["cnt"] == 0

            role = "admin" if is_first else "viewer"
            status = "approved" if is_first else "pending"

            password_hash = generate_password_hash(password)
            cur = conn.execute(
                """
                INSERT INTO users (username, password_hash, display_name, role, status, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (username, password_hash, display_name, role, status, _now()),
            )
            return cur.lastrowid
    except sqlite3.IntegrityError:
        return None
    finally:
        conn.close()


def get_user_by_username(db_path: str, username: str):
    """Return a user dict (without password_hash) or None."""
    conn = _conn(db_path)
    try:
        row = conn.execute(
            "SELECT id, username, display_name, role, status, created_at FROM users WHERE username = ?",
            (username,),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_user_by_id(db_path: str, user_id: int):
    """Return a user dict (without password_hash) or None."""
    conn = _conn(db_path)
    try:
        row = conn.execute(
            "SELECT id, username, display_name, role, status, created_at FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def verify_password(db_path: str, username: str, password: str) -> bool:
    """Return True if username exists and password matches the stored hash."""
    conn = _conn(db_path)
    try:
        row = conn.execute(
            "SELECT password_hash FROM users WHERE username = ?", (username,)
        ).fetchone()
        if row is None:
            return False
        return check_password_hash(row["password_hash"], password)
    finally:
        conn.close()


def approve_user(db_path: str, user_id: int, role: str) -> None:
    """Set status='approved' and assign the given role."""
    conn = _conn(db_path)
    with conn:
        conn.execute(
            "UPDATE users SET status = 'approved', role = ? WHERE id = ?",
            (role, user_id),
        )
    conn.close()


def update_user_role(db_path: str, user_id: int, role: str) -> None:
    """Change a user's role."""
    conn = _conn(db_path)
    with conn:
        conn.execute("UPDATE users SET role = ? WHERE id = ?", (role, user_id))
    conn.close()


def get_all_users(db_path: str) -> list:
    """Return all users as a list of dicts (without password_hash)."""
    conn = _conn(db_path)
    try:
        rows = conn.execute(
            "SELECT id, username, display_name, role, status, created_at FROM users ORDER BY id"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_pending_users(db_path: str) -> list:
    """Return users whose status is 'pending'."""
    conn = _conn(db_path)
    try:
        rows = conn.execute(
            "SELECT id, username, display_name, role, status, created_at FROM users WHERE status = 'pending' ORDER BY id"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Session functions
# ---------------------------------------------------------------------------

def create_session(db_path: str, name: str, created_by: str) -> int:
    """
    Create a new test session and auto-populate 10 SW version rows from the
    template. Returns the new session id.
    """
    conn = _conn(db_path)
    try:
        with conn:
            cur = conn.execute(
                "INSERT INTO sessions (name, status, created_by, created_at) VALUES (?, 'active', ?, ?)",
                (name, created_by, _now()),
            )
            session_id = cur.lastrowid
            for idx, (cat_label, sw_name) in enumerate(SW_VERSION_TEMPLATE):
                conn.execute(
                    """
                    INSERT INTO session_versions
                        (session_id, category_label, sw_name, version_value, sort_order)
                    VALUES (?, ?, ?, '', ?)
                    """,
                    (session_id, cat_label, sw_name, idx),
                )
        return session_id
    finally:
        conn.close()


def get_session(db_path: str, session_id: int):
    """Return a session dict with a 'versions' list, or None."""
    conn = _conn(db_path)
    try:
        row = conn.execute(
            "SELECT * FROM sessions WHERE id = ?", (session_id,)
        ).fetchone()
        if row is None:
            return None
        session = dict(row)
        versions = conn.execute(
            "SELECT * FROM session_versions WHERE session_id = ? ORDER BY sort_order",
            (session_id,),
        ).fetchall()
        session["versions"] = [dict(v) for v in versions]
        return session
    finally:
        conn.close()


def get_sessions_by_status(db_path: str, statuses: list) -> list:
    """Return sessions whose status is in the given list."""
    if not statuses:
        return []
    placeholders = ",".join("?" * len(statuses))
    conn = _conn(db_path)
    try:
        rows = conn.execute(
            f"SELECT * FROM sessions WHERE status IN ({placeholders}) ORDER BY id DESC",
            statuses,
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def update_session_status(db_path: str, session_id: int, status: str) -> None:
    """Update session status; set completed_at when status becomes 'completed'."""
    conn = _conn(db_path)
    with conn:
        if status == "completed":
            conn.execute(
                "UPDATE sessions SET status = ?, completed_at = ? WHERE id = ?",
                (status, _now(), session_id),
            )
        else:
            conn.execute(
                "UPDATE sessions SET status = ?, completed_at = NULL WHERE id = ?",
                (status, session_id),
            )
    conn.close()


def update_session_version(db_path: str, version_id: int, version_value: str) -> None:
    """Update the version text for one SW version row."""
    conn = _conn(db_path)
    with conn:
        conn.execute(
            "UPDATE session_versions SET version_value = ? WHERE id = ?",
            (version_value, version_id),
        )
    conn.close()


# ---------------------------------------------------------------------------
# Category functions
# ---------------------------------------------------------------------------

def create_category(
    db_path: str,
    session_id: int,
    name: str,
    description: str,
    created_by: str,
) -> int:
    """Create a category with auto-incremented sort_order. Returns category id."""
    conn = _conn(db_path)
    try:
        with conn:
            row = conn.execute(
                "SELECT COALESCE(MAX(sort_order), -1) + 1 AS next FROM categories WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            sort_order = row["next"]
            cur = conn.execute(
                """
                INSERT INTO categories (session_id, name, description, sort_order, created_by, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (session_id, name, description, sort_order, created_by, _now()),
            )
            return cur.lastrowid
    finally:
        conn.close()


def get_categories(db_path: str, session_id: int) -> list:
    """Return categories for a session with nested test items."""
    conn = _conn(db_path)
    try:
        cats = conn.execute(
            "SELECT * FROM categories WHERE session_id = ? ORDER BY sort_order",
            (session_id,),
        ).fetchall()
        result = []
        for cat in cats:
            cat_dict = dict(cat)
            items = conn.execute(
                "SELECT * FROM test_items WHERE category_id = ? ORDER BY sort_order",
                (cat["id"],),
            ).fetchall()
            cat_dict["items"] = [dict(i) for i in items]
            result.append(cat_dict)
        return result
    finally:
        conn.close()


def update_category(db_path: str, category_id: int, name: str, description: str) -> None:
    conn = _conn(db_path)
    with conn:
        conn.execute(
            "UPDATE categories SET name = ?, description = ? WHERE id = ?",
            (name, description, category_id),
        )
    conn.close()


def delete_category(db_path: str, category_id: int) -> None:
    """
    Delete a category.  Cascade rules handle items → comments and attachments.
    """
    conn = _conn(db_path)
    with conn:
        conn.execute("DELETE FROM categories WHERE id = ?", (category_id,))
    conn.close()


def reorder_categories(db_path: str, ordered_ids: list) -> None:
    """Update sort_order for each category id in ordered_ids (index = order)."""
    conn = _conn(db_path)
    with conn:
        for idx, cat_id in enumerate(ordered_ids):
            conn.execute(
                "UPDATE categories SET sort_order = ? WHERE id = ?",
                (idx, cat_id),
            )
    conn.close()


# ---------------------------------------------------------------------------
# Test item functions
# ---------------------------------------------------------------------------

def create_test_item(
    db_path: str,
    category_id: int,
    name: str,
    description: str,
    created_by: str,
) -> int:
    """Create a test item with default result='pending'. Returns item id."""
    conn = _conn(db_path)
    try:
        with conn:
            row = conn.execute(
                "SELECT COALESCE(MAX(sort_order), -1) + 1 AS next FROM test_items WHERE category_id = ?",
                (category_id,),
            ).fetchone()
            sort_order = row["next"]
            cur = conn.execute(
                """
                INSERT INTO test_items
                    (category_id, name, description, result, notes, sort_order, created_by, created_at)
                VALUES (?, ?, ?, 'pending', '', ?, ?, ?)
                """,
                (category_id, name, description, sort_order, created_by, _now()),
            )
            return cur.lastrowid
    finally:
        conn.close()


_ALLOWED_ITEM_KEYS = {"name", "description", "result", "notes", "sort_order", "updated_by"}


def update_test_item(db_path: str, item_id: int, **kwargs) -> None:
    """Update allowed fields on a test item. Also sets updated_at."""
    fields = {k: v for k, v in kwargs.items() if k in _ALLOWED_ITEM_KEYS}
    if not fields:
        return
    fields["updated_at"] = _now()
    set_clause = ", ".join(f"{k} = ?" for k in fields)
    values = list(fields.values()) + [item_id]
    conn = _conn(db_path)
    with conn:
        conn.execute(f"UPDATE test_items SET {set_clause} WHERE id = ?", values)
    conn.close()


def delete_test_item(db_path: str, item_id: int) -> None:
    """Delete an item; cascade removes its comments and attachments."""
    conn = _conn(db_path)
    with conn:
        conn.execute("DELETE FROM test_items WHERE id = ?", (item_id,))
    conn.close()


def reorder_items(db_path: str, ordered_ids: list) -> None:
    """Update sort_order for each item id in ordered_ids (index = order)."""
    conn = _conn(db_path)
    with conn:
        for idx, item_id in enumerate(ordered_ids):
            conn.execute(
                "UPDATE test_items SET sort_order = ? WHERE id = ?",
                (idx, item_id),
            )
    conn.close()


def get_test_item(db_path: str, item_id: int):
    """Return a test item dict or None."""
    conn = _conn(db_path)
    try:
        row = conn.execute(
            "SELECT * FROM test_items WHERE id = ?", (item_id,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Comment functions
# ---------------------------------------------------------------------------

def create_comment(
    db_path: str,
    item_id: int,
    content: str,
    created_by: str,
    parent_id=None,
) -> int:
    """Create a comment (optionally threaded). Returns comment id."""
    conn = _conn(db_path)
    try:
        with conn:
            cur = conn.execute(
                """
                INSERT INTO comments (item_id, parent_id, content, created_by, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (item_id, parent_id, content, created_by, _now()),
            )
            return cur.lastrowid
    finally:
        conn.close()


def get_comments(db_path: str, item_id: int) -> list:
    """
    Return comments for an item, joining users for author_name.
    Each comment dict includes an 'attachments' list.
    """
    conn = _conn(db_path)
    try:
        rows = conn.execute(
            """
            SELECT c.id, c.item_id, c.parent_id, c.content, c.created_by,
                   c.created_at,
                   u.display_name AS author_name
            FROM comments c
            LEFT JOIN users u ON u.username = c.created_by
            WHERE c.item_id = ?
            ORDER BY c.created_at
            """,
            (item_id,),
        ).fetchall()
        comments = []
        for row in rows:
            comment = dict(row)
            attachments = conn.execute(
                "SELECT * FROM attachments WHERE comment_id = ?", (row["id"],)
            ).fetchall()
            comment["attachments"] = [dict(a) for a in attachments]
            comments.append(comment)
        return comments
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Attachment functions
# ---------------------------------------------------------------------------

def create_attachment(
    db_path: str,
    filename: str,
    original_name: str,
    created_by: str,
    item_id=None,
    comment_id=None,
) -> int:
    """Create an attachment record. Returns attachment id."""
    conn = _conn(db_path)
    try:
        with conn:
            cur = conn.execute(
                """
                INSERT INTO attachments
                    (filename, original_name, item_id, comment_id, created_by, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (filename, original_name, item_id, comment_id, created_by, _now()),
            )
            return cur.lastrowid
    finally:
        conn.close()


def get_item_attachments(db_path: str, item_id: int) -> list:
    """Return direct item attachments only (comment_id IS NULL)."""
    conn = _conn(db_path)
    try:
        rows = conn.execute(
            "SELECT * FROM attachments WHERE item_id = ? AND comment_id IS NULL ORDER BY created_at",
            (item_id,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Notification functions
# ---------------------------------------------------------------------------

def create_notification(
    db_path: str,
    user_id: int,
    ntype: str,
    message: str,
    target_item_id=None,
) -> int:
    """Create a notification. Returns notification id."""
    conn = _conn(db_path)
    try:
        with conn:
            cur = conn.execute(
                """
                INSERT INTO notifications
                    (user_id, ntype, message, target_item_id, is_read, created_at)
                VALUES (?, ?, ?, ?, 0, ?)
                """,
                (user_id, ntype, message, target_item_id, _now()),
            )
            return cur.lastrowid
    finally:
        conn.close()


def get_unread_notifications(db_path: str, user_id: int) -> list:
    """Return unread notifications for a user, newest first."""
    conn = _conn(db_path)
    try:
        rows = conn.execute(
            """
            SELECT * FROM notifications
            WHERE user_id = ? AND is_read = 0
            ORDER BY created_at DESC
            """,
            (user_id,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def mark_notifications_read(db_path: str, user_id: int) -> None:
    """Mark all notifications for a user as read."""
    conn = _conn(db_path)
    with conn:
        conn.execute(
            "UPDATE notifications SET is_read = 1 WHERE user_id = ?", (user_id,)
        )
    conn.close()


# ---------------------------------------------------------------------------
# Template copy
# ---------------------------------------------------------------------------

def copy_session_structure(
    db_path: str,
    source_session_id: int,
    new_name: str,
    created_by: str,
) -> int:
    """
    Copy a session's SW version rows, categories, and test items into a new
    session. Results are reset to 'pending'; no comments or attachments are
    copied.

    Returns the new session id.
    """
    conn = _conn(db_path)
    try:
        with conn:
            # Create new session
            cur = conn.execute(
                "INSERT INTO sessions (name, status, created_by, created_at) VALUES (?, 'active', ?, ?)",
                (new_name, created_by, _now()),
            )
            new_session_id = cur.lastrowid

            # Copy SW version rows
            versions = conn.execute(
                "SELECT * FROM session_versions WHERE session_id = ? ORDER BY sort_order",
                (source_session_id,),
            ).fetchall()
            for v in versions:
                conn.execute(
                    """
                    INSERT INTO session_versions
                        (session_id, category_label, sw_name, version_value, sort_order)
                    VALUES (?, ?, ?, '', ?)
                    """,
                    (new_session_id, v["category_label"], v["sw_name"], v["sort_order"]),
                )

            # Copy categories and items
            categories = conn.execute(
                "SELECT * FROM categories WHERE session_id = ? ORDER BY sort_order",
                (source_session_id,),
            ).fetchall()
            for cat in categories:
                cur2 = conn.execute(
                    """
                    INSERT INTO categories
                        (session_id, name, description, sort_order, created_by, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        new_session_id,
                        cat["name"],
                        cat["description"],
                        cat["sort_order"],
                        created_by,
                        _now(),
                    ),
                )
                new_cat_id = cur2.lastrowid

                items = conn.execute(
                    "SELECT * FROM test_items WHERE category_id = ? ORDER BY sort_order",
                    (cat["id"],),
                ).fetchall()
                for item in items:
                    conn.execute(
                        """
                        INSERT INTO test_items
                            (category_id, name, description, result, notes,
                             sort_order, created_by, created_at)
                        VALUES (?, ?, ?, 'pending', '', ?, ?, ?)
                        """,
                        (
                            new_cat_id,
                            item["name"],
                            item["description"],
                            item["sort_order"],
                            created_by,
                            _now(),
                        ),
                    )

        return new_session_id
    finally:
        conn.close()
