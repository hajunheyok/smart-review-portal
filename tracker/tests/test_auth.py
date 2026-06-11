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


def test_first_user_is_admin(empty_db):
    user_id = models.create_user(empty_db, "admin", "pw", "Admin")
    user = models.get_user_by_id(empty_db, user_id)
    assert user["role"] == "admin"
    assert user["status"] == "approved"
