"""
app.py — Flask + SocketIO application for Smart Review Test Tracker
"""
import os
import sys
import uuid
from functools import wraps

from flask import (
    Flask,
    jsonify,
    request,
    send_from_directory,
    session,
    render_template,
)
from flask_socketio import SocketIO, join_room, leave_room, emit

import models

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

def _exe_dir() -> str:
    """Return the directory next to the running executable (or script)."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


BASE_DIR = _exe_dir()
DB_PATH = os.environ.get("TRACKER_DB", os.path.join(BASE_DIR, "tracker.db"))
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "bmp", "webp"}
MAX_CONTENT_LENGTH = 10 * 1024 * 1024  # 10 MB

os.makedirs(UPLOAD_DIR, exist_ok=True)

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------

app = Flask(__name__, template_folder="templates")
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-key-change-in-production")
app.config["MAX_CONTENT_LENGTH"] = MAX_CONTENT_LENGTH

socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

# Track connected users: {sid: user_id}
online_users: dict = {}

# ---------------------------------------------------------------------------
# Role level map
# ---------------------------------------------------------------------------

ROLE_LEVELS = {"viewer": 0, "tester": 1, "reviewer": 2, "admin": 3}

# ---------------------------------------------------------------------------
# Decorators
# ---------------------------------------------------------------------------


def require_auth(f):
    """Verify session, load user, check approved status. Sets request.user."""
    @wraps(f)
    def decorated(*args, **kwargs):
        user_id = session.get("user_id")
        if not user_id:
            return jsonify({"error": "Unauthorized"}), 401
        user = models.get_user_by_id(DB_PATH, user_id)
        if not user:
            return jsonify({"error": "Unauthorized"}), 401
        if user.get("status") != "approved":
            return jsonify({"error": "Account pending approval"}), 403
        request.user = user
        return f(*args, **kwargs)
    return decorated


def require_role(min_role: str):
    """Check that the authenticated user has at least min_role."""
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            user_id = session.get("user_id")
            if not user_id:
                return jsonify({"error": "Unauthorized"}), 401
            user = models.get_user_by_id(DB_PATH, user_id)
            if not user:
                return jsonify({"error": "Unauthorized"}), 401
            if user.get("status") != "approved":
                return jsonify({"error": "Account pending approval"}), 403
            if ROLE_LEVELS.get(user.get("role", "viewer"), 0) < ROLE_LEVELS.get(min_role, 0):
                return jsonify({"error": "Insufficient role"}), 403
            request.user = user
            return f(*args, **kwargs)
        return decorated
    return decorator


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


# ---------------------------------------------------------------------------
# General routes
# ---------------------------------------------------------------------------


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/health")
def health():
    return jsonify({"status": "ok"})


# ---------------------------------------------------------------------------
# Auth routes
# ---------------------------------------------------------------------------


@app.route("/api/auth/register", methods=["POST"])
def auth_register():
    data = request.get_json(silent=True) or {}
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""
    display_name = (data.get("display_name") or username).strip()

    if not username or not password:
        return jsonify({"error": "username and password required"}), 400

    user_id = models.create_user(DB_PATH, username, password, display_name)
    if user_id is None:
        return jsonify({"error": "Username already exists"}), 409

    user = models.get_user_by_id(DB_PATH, user_id)
    return jsonify(user), 201


@app.route("/api/auth/login", methods=["POST"])
def auth_login():
    data = request.get_json(silent=True) or {}
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""

    if not models.verify_password(DB_PATH, username, password):
        return jsonify({"error": "Invalid credentials"}), 401

    user = models.get_user_by_username(DB_PATH, username)
    if not user:
        return jsonify({"error": "User not found"}), 404

    if user.get("status") == "pending":
        return jsonify({"error": "Account pending approval"}), 403

    session["user_id"] = user["id"]
    return jsonify(user)


@app.route("/api/auth/logout", methods=["POST"])
def auth_logout():
    session.clear()
    return jsonify({"ok": True})


@app.route("/api/auth/me")
def auth_me():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401
    user = models.get_user_by_id(DB_PATH, user_id)
    if not user:
        return jsonify({"error": "User not found"}), 404
    return jsonify(user)


# ---------------------------------------------------------------------------
# Admin routes
# ---------------------------------------------------------------------------


@app.route("/api/admin/users")
@require_role("admin")
def admin_users():
    return jsonify(models.get_all_users(DB_PATH))


@app.route("/api/admin/pending")
@require_role("admin")
def admin_pending():
    return jsonify(models.get_pending_users(DB_PATH))


@app.route("/api/admin/approve", methods=["POST"])
@require_role("admin")
def admin_approve():
    data = request.get_json(silent=True) or {}
    user_id = data.get("user_id")
    role = data.get("role", "viewer")
    if not user_id:
        return jsonify({"error": "user_id required"}), 400
    models.approve_user(DB_PATH, user_id, role)
    return jsonify({"ok": True})


@app.route("/api/admin/role", methods=["POST"])
@require_role("admin")
def admin_role():
    data = request.get_json(silent=True) or {}
    user_id = data.get("user_id")
    role = data.get("role")
    if not user_id or not role:
        return jsonify({"error": "user_id and role required"}), 400
    if role not in ROLE_LEVELS:
        return jsonify({"error": "Invalid role"}), 400
    models.update_user_role(DB_PATH, user_id, role)
    return jsonify({"ok": True})


# ---------------------------------------------------------------------------
# Session routes
# ---------------------------------------------------------------------------


@app.route("/api/sessions/search")
@require_auth
def sessions_search():
    q = request.args.get("q", "")
    from_date = request.args.get("from", "")
    to_date = request.args.get("to", "")
    result_filter = request.args.get("result", "")

    conn = models._conn(DB_PATH)
    try:
        sql = "SELECT * FROM sessions WHERE 1=1"
        params = []

        if q:
            sql += " AND name LIKE ?"
            params.append(f"%{q}%")
        if from_date:
            sql += " AND created_at >= ?"
            params.append(from_date)
        if to_date:
            sql += " AND created_at <= ?"
            params.append(to_date + " 23:59:59")
        if result_filter:
            sql += " AND status = ?"
            params.append(result_filter)

        sql += " ORDER BY id DESC"
        rows = conn.execute(sql, params).fetchall()
        return jsonify([dict(r) for r in rows])
    finally:
        conn.close()


@app.route("/api/sessions")
@require_auth
def sessions_list():
    active = models.get_sessions_by_status(DB_PATH, ["draft", "in_progress"])
    archived = models.get_sessions_by_status(DB_PATH, ["completed"])
    return jsonify({"active": active, "archived": archived})


@app.route("/api/sessions", methods=["POST"])
@require_role("reviewer")
def sessions_create():
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    template_id = data.get("template_id")

    if not name:
        return jsonify({"error": "name required"}), 400

    if template_id:
        session_id = models.copy_session_structure(
            DB_PATH, template_id, name, request.user["username"]
        )
    else:
        session_id = models.create_session(DB_PATH, name, request.user["username"])

    sess = models.get_session(DB_PATH, session_id)
    socketio.emit("session_created", sess, room="tracker")
    return jsonify(sess), 201


@app.route("/api/sessions/<int:session_id>")
@require_auth
def sessions_get(session_id):
    sess = models.get_session(DB_PATH, session_id)
    if not sess:
        return jsonify({"error": "Not found"}), 404
    sess["categories"] = models.get_categories(DB_PATH, session_id)
    return jsonify(sess)


@app.route("/api/sessions/<int:session_id>/name", methods=["PUT"])
@require_role("reviewer")
def sessions_update_name(session_id):
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"error": "name required"}), 400
    sess = models.get_session(DB_PATH, session_id)
    if not sess:
        return jsonify({"error": "Not found"}), 404
    models.update_session_name(DB_PATH, session_id, name)
    updated = models.get_session(DB_PATH, session_id)
    socketio.emit("session_updated", updated, room="tracker")
    return jsonify(updated)


@app.route("/api/sessions/<int:session_id>/status", methods=["PUT"])
@require_role("reviewer")
def sessions_update_status(session_id):
    data = request.get_json(silent=True) or {}
    new_status = data.get("status")
    valid_statuses = {"draft", "in_progress", "completed"}
    if new_status not in valid_statuses:
        return jsonify({"error": "Invalid status"}), 400

    sess = models.get_session(DB_PATH, session_id)
    if not sess:
        return jsonify({"error": "Not found"}), 404

    # Reviewer+ can change session status (including reopening completed)
    if sess.get("status") == "completed" and new_status != "completed":
        if ROLE_LEVELS.get(request.user.get("role", "viewer"), 0) < ROLE_LEVELS["reviewer"]:
            return jsonify({"error": "Reviewer+ can reopen a completed session"}), 403

    models.update_session_status(DB_PATH, session_id, new_status)
    updated = models.get_session(DB_PATH, session_id)
    socketio.emit("session_updated", updated, room="tracker")
    return jsonify(updated)


@app.route("/api/sessions/<int:session_id>/versions/<int:version_id>", methods=["PUT"])
@require_role("reviewer")
def sessions_update_version(session_id, version_id):
    data = request.get_json(silent=True) or {}
    version_value = data.get("version_value", "")
    models.update_session_version(DB_PATH, version_id, version_value)
    updated = models.get_session(DB_PATH, session_id)
    socketio.emit("version_updated", updated, room="tracker")
    return jsonify(updated)


# ---------------------------------------------------------------------------
# Category routes
# ---------------------------------------------------------------------------


@app.route("/api/sessions/<int:session_id>/categories", methods=["POST"])
@require_role("reviewer")
def categories_create(session_id):
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    description = (data.get("description") or "").strip()

    if not name:
        return jsonify({"error": "name required"}), 400

    cat_id = models.create_category(
        DB_PATH, session_id, name, description, request.user["username"]
    )
    categories = models.get_categories(DB_PATH, session_id)
    socketio.emit("categories_updated", {"session_id": session_id, "categories": categories}, room="tracker")
    cat = next((c for c in categories if c["id"] == cat_id), None)
    return jsonify(cat), 201


@app.route("/api/categories/<int:category_id>", methods=["PUT"])
@require_role("reviewer")
def categories_update(category_id):
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    description = (data.get("description") or "").strip()

    if not name:
        return jsonify({"error": "name required"}), 400

    models.update_category(DB_PATH, category_id, name, description)
    return jsonify({"ok": True})


@app.route("/api/categories/<int:category_id>", methods=["DELETE"])
@require_role("reviewer")
def categories_delete(category_id):
    models.delete_category(DB_PATH, category_id)
    return jsonify({"ok": True})


@app.route("/api/sessions/<int:session_id>/categories/reorder", methods=["PUT"])
@require_role("reviewer")
def categories_reorder(session_id):
    data = request.get_json(silent=True) or {}
    ordered_ids = data.get("ordered_ids", [])
    if not isinstance(ordered_ids, list):
        return jsonify({"error": "ordered_ids must be a list"}), 400
    models.reorder_categories(DB_PATH, ordered_ids)
    return jsonify({"ok": True})


# ---------------------------------------------------------------------------
# Test item routes
# ---------------------------------------------------------------------------


@app.route("/api/categories/<int:category_id>/items", methods=["POST"])
@require_role("reviewer")
def items_create(category_id):
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    description = (data.get("description") or "").strip()

    if not name:
        return jsonify({"error": "name required"}), 400

    item_id = models.create_test_item(
        DB_PATH, category_id, name, description, request.user["username"]
    )
    item = models.get_test_item(DB_PATH, item_id)
    socketio.emit("item_created", item, room="tracker")
    return jsonify(item), 201


@app.route("/api/items/<int:item_id>", methods=["PUT"])
@require_role("tester")
def items_update(item_id):
    data = request.get_json(silent=True) or {}
    kwargs = {}
    for field in ("name", "description", "result", "notes"):
        if field in data:
            kwargs[field] = data[field]
    kwargs["updated_by"] = request.user["username"]

    models.update_test_item(DB_PATH, item_id, **kwargs)
    item = models.get_test_item(DB_PATH, item_id)
    socketio.emit("item_updated", item, room="tracker")
    return jsonify(item)


@app.route("/api/items/<int:item_id>", methods=["DELETE"])
@require_role("reviewer")
def items_delete(item_id):
    models.delete_test_item(DB_PATH, item_id)
    socketio.emit("item_deleted", {"id": item_id}, room="tracker")
    return jsonify({"ok": True})


@app.route("/api/categories/<int:category_id>/items/reorder", methods=["PUT"])
@require_role("reviewer")
def items_reorder(category_id):
    data = request.get_json(silent=True) or {}
    ordered_ids = data.get("ordered_ids", [])
    if not isinstance(ordered_ids, list):
        return jsonify({"error": "ordered_ids must be a list"}), 400
    models.reorder_items(DB_PATH, ordered_ids)
    return jsonify({"ok": True})


# ---------------------------------------------------------------------------
# Comment routes
# ---------------------------------------------------------------------------


@app.route("/api/items/<int:item_id>/comments")
@require_auth
def comments_list(item_id):
    return jsonify(models.get_comments(DB_PATH, item_id))


@app.route("/api/items/<int:item_id>/comments", methods=["POST"])
@require_role("tester")
def comments_create(item_id):
    data = request.get_json(silent=True) or {}
    content = (data.get("content") or "").strip()
    parent_id = data.get("parent_id")

    if not content:
        return jsonify({"error": "content required"}), 400

    comment_id = models.create_comment(
        DB_PATH, item_id, content, request.user["username"], parent_id
    )
    comments = models.get_comments(DB_PATH, item_id)
    socketio.emit("comments_updated", {"item_id": item_id, "comments": comments}, room="tracker")
    comment = next((c for c in comments if c["id"] == comment_id), None)
    return jsonify(comment), 201


# ---------------------------------------------------------------------------
# Upload routes
# ---------------------------------------------------------------------------


@app.route("/api/upload", methods=["POST"])
@require_role("tester")
def upload_file():
    if "file" not in request.files:
        return jsonify({"error": "No file part"}), 400

    f = request.files["file"]
    if not f.filename:
        return jsonify({"error": "No file selected"}), 400
    if not _allowed_file(f.filename):
        return jsonify({"error": "File type not allowed"}), 400

    ext = f.filename.rsplit(".", 1)[1].lower()
    unique_name = f"{uuid.uuid4().hex}.{ext}"
    save_path = os.path.join(UPLOAD_DIR, unique_name)
    f.save(save_path)

    item_id = request.form.get("item_id")
    comment_id = request.form.get("comment_id")
    item_id = int(item_id) if item_id else None
    comment_id = int(comment_id) if comment_id else None

    att_id = models.create_attachment(
        DB_PATH,
        unique_name,
        f.filename,
        request.user["username"],
        item_id=item_id,
        comment_id=comment_id,
    )

    return jsonify({
        "id": att_id,
        "filename": unique_name,
        "original_name": f.filename,
        "url": f"/uploads/{unique_name}",
    }), 201


@app.route("/uploads/<path:filename>")
def serve_upload(filename):
    return send_from_directory(UPLOAD_DIR, filename)


# ---------------------------------------------------------------------------
# Notification routes
# ---------------------------------------------------------------------------


@app.route("/api/notifications")
@require_auth
def notifications_list():
    return jsonify(models.get_unread_notifications(DB_PATH, request.user["id"]))


@app.route("/api/notifications/read", methods=["POST"])
@require_auth
def notifications_read():
    models.mark_notifications_read(DB_PATH, request.user["id"])
    return jsonify({"ok": True})


# ---------------------------------------------------------------------------
# WebSocket events
# ---------------------------------------------------------------------------


@socketio.on("connect")
def ws_connect():
    user_id = session.get("user_id")
    if not user_id:
        return False  # Reject unauthenticated connections

    user = models.get_user_by_id(DB_PATH, user_id)
    if not user or user.get("status") != "approved":
        return False

    join_room("tracker")
    online_users[request.sid] = user_id
    socketio.emit(
        "online_users",
        list(online_users.values()),
        room="tracker",
    )


@socketio.on("disconnect")
def ws_disconnect():
    online_users.pop(request.sid, None)
    socketio.emit(
        "online_users",
        list(online_users.values()),
        room="tracker",
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    models.init_db(DB_PATH)
    print("=" * 60)
    print("  Smart Review Test Tracker")
    print(f"  URL  : http://0.0.0.0:9091")
    print(f"  DB   : {DB_PATH}")
    print(f"  UPL  : {UPLOAD_DIR}")
    print("=" * 60)
    socketio.run(app, host="0.0.0.0", port=9091, allow_unsafe_werkzeug=True)
