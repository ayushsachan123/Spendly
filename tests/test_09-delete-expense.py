"""
tests/test_09-delete-expense.py

Tests for Step 9: Delete Expense feature.

Route under test:
  POST /expenses/<int:id>/delete — deletes the expense if it belongs to the
                                   logged-in user, then redirects to /profile.

Spec (source of truth for all assertions below):
  - POST while logged out              → 302 to /login
  - GET request to the route           → 405 Method Not Allowed
  - POST valid id owned by session user → row deleted + 302 to /profile
  - After deletion row is gone from DB  (query by id returns nothing)
  - Other rows for same user are not affected
  - expense count drops by exactly 1 after a successful delete
  - POST with id belonging to another user → NO deletion + 302 to /profile
  - POST with non-existent id             → 302 to /profile (no crash)

Fixture strategy (mirrors test_07_add_expense.py):
  - db_path  : temp-file SQLite DB (required because get_db opens multiple
               connections per request; an in-memory DB cannot be shared)
  - auth_client : Flask test client with session pre-set to the primary user
  - Unauthenticated tests spin up a bare test_client() inside the test itself
  - get_db is patched via unittest.mock.patch to point at the temp-file DB
"""

import sqlite3

import pytest
from unittest.mock import patch
from werkzeug.security import generate_password_hash

import app as flask_app


# ---------------------------------------------------------------------------
# Schema — must match database/db.py exactly
# ---------------------------------------------------------------------------

_SCHEMA = """
    CREATE TABLE users (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        name          TEXT    NOT NULL,
        email         TEXT    NOT NULL UNIQUE,
        password_hash TEXT    NOT NULL,
        created_at    TEXT    DEFAULT (datetime('now'))
    );
    CREATE TABLE expenses (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id     INTEGER NOT NULL REFERENCES users(id),
        amount      REAL    NOT NULL,
        category    TEXT    NOT NULL,
        date        TEXT    NOT NULL,
        description TEXT,
        created_at  TEXT    DEFAULT (datetime('now'))
    );
"""


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def db_path(tmp_path):
    """
    Temp-file SQLite DB with schema + two users + several expenses.

    Returns (path_str, primary_user_id, other_user_id, primary_expense_ids, other_expense_id).

    primary user  — the user the test client will be logged in as
    other user    — a second user whose expenses must NOT be deletable by the primary user
    """
    path = str(tmp_path / "test.db")
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(_SCHEMA)

    # Primary user
    conn.execute(
        "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
        ("Primary User", "primary@spendly.com", generate_password_hash("primary123")),
    )
    primary_user_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    # Other user
    conn.execute(
        "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
        ("Other User", "other@spendly.com", generate_password_hash("other1234")),
    )
    other_user_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    # Three expenses for the primary user
    primary_expenses = [
        (primary_user_id, 100.00, "Food",      "2026-06-01", "Lunch"),
        (primary_user_id, 200.00, "Transport", "2026-06-02", "Taxi"),
        (primary_user_id, 300.00, "Bills",     "2026-06-03", "Electricity"),
    ]
    conn.executemany(
        "INSERT INTO expenses (user_id, amount, category, date, description) VALUES (?, ?, ?, ?, ?)",
        primary_expenses,
    )
    # Collect IDs in insertion order
    first_primary_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    primary_expense_ids = [first_primary_id - 2, first_primary_id - 1, first_primary_id]

    # One expense for the other user
    conn.execute(
        "INSERT INTO expenses (user_id, amount, category, date, description) VALUES (?, ?, ?, ?, ?)",
        (other_user_id, 500.00, "Shopping", "2026-06-04", "Clothes"),
    )
    other_expense_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    conn.commit()
    conn.close()
    return path, primary_user_id, other_user_id, primary_expense_ids, other_expense_id


def _make_conn_factory(db_path: str):
    """Return a callable that opens a fresh connection to db_path each call."""
    def factory():
        c = sqlite3.connect(db_path)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA foreign_keys = ON")
        return c
    return factory


@pytest.fixture
def auth_client(db_path):
    """
    Flask test client pre-authenticated as the primary user.

    Yields (client, primary_user_id, other_user_id, primary_expense_ids,
            other_expense_id, make_conn) so tests can drive DB assertions
    and get_db patches independently.
    """
    path, primary_user_id, other_user_id, primary_expense_ids, other_expense_id = db_path
    make_conn = _make_conn_factory(path)

    flask_app.app.config["TESTING"] = True
    flask_app.app.config["SECRET_KEY"] = "test-secret"

    with flask_app.app.test_client() as client:
        with client.session_transaction() as sess:
            sess["user_id"] = primary_user_id
            sess["user_name"] = "Primary User"
        yield client, primary_user_id, other_user_id, primary_expense_ids, other_expense_id, make_conn


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _post_delete(client, make_conn, expense_id):
    """Issue POST /expenses/<id>/delete with get_db patched to the temp-file DB."""
    with patch("app.get_db", side_effect=make_conn):
        return client.post(f"/expenses/{expense_id}/delete")


def _expense_exists(make_conn, expense_id):
    """Return True if the expense row with that id still exists in the DB."""
    conn = make_conn()
    try:
        row = conn.execute(
            "SELECT id FROM expenses WHERE id = ?", (expense_id,)
        ).fetchone()
        return row is not None
    finally:
        conn.close()


def _count_expenses_for_user(make_conn, user_id):
    """Return the total number of expense rows for a given user."""
    conn = make_conn()
    try:
        row = conn.execute(
            "SELECT COUNT(*) AS cnt FROM expenses WHERE user_id = ?", (user_id,)
        ).fetchone()
        return row["cnt"]
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# 1. Auth guard — unauthenticated requests
# ---------------------------------------------------------------------------

class TestAuthGuard:
    """Unauthenticated POST must redirect to /login without touching the DB."""

    def test_post_unauthenticated_returns_302(self):
        flask_app.app.config["TESTING"] = True
        with flask_app.app.test_client() as c:
            response = c.post("/expenses/1/delete")
        assert response.status_code == 302, (
            "Unauthenticated POST /expenses/<id>/delete must return 302"
        )

    def test_post_unauthenticated_redirects_to_login(self):
        flask_app.app.config["TESTING"] = True
        with flask_app.app.test_client() as c:
            response = c.post("/expenses/1/delete")
        assert "/login" in response.headers["Location"], (
            "Unauthenticated POST must redirect to /login"
        )

    def test_post_unauthenticated_does_not_delete_row(self, db_path):
        """The expense row must still exist after an unauthenticated POST attempt."""
        path, _, _, primary_expense_ids, _ = db_path
        make_conn = _make_conn_factory(path)
        target_id = primary_expense_ids[0]

        flask_app.app.config["TESTING"] = True
        with flask_app.app.test_client() as c:
            with patch("app.get_db", side_effect=make_conn):
                c.post(f"/expenses/{target_id}/delete")

        assert _expense_exists(make_conn, target_id), (
            "Expense row must not be deleted by an unauthenticated request"
        )


# ---------------------------------------------------------------------------
# 2. Method Not Allowed — GET is not supported
# ---------------------------------------------------------------------------

class TestMethodNotAllowed:
    """GET /expenses/<id>/delete must return 405."""

    def test_get_returns_405(self, auth_client):
        client, _, _, primary_expense_ids, _, make_conn = auth_client
        target_id = primary_expense_ids[0]
        with patch("app.get_db", side_effect=make_conn):
            response = client.get(f"/expenses/{target_id}/delete")
        assert response.status_code == 405, (
            "GET /expenses/<id>/delete must return 405 Method Not Allowed"
        )

    def test_get_unauthenticated_returns_405(self):
        """Even without a session, GET must be 405 — method is checked before auth."""
        flask_app.app.config["TESTING"] = True
        with flask_app.app.test_client() as c:
            response = c.get("/expenses/1/delete")
        # Flask returns 405 before the view function runs — auth state is irrelevant
        assert response.status_code == 405, (
            "GET /expenses/<id>/delete must always return 405, regardless of auth"
        )


# ---------------------------------------------------------------------------
# 3. Happy path — delete own expense
# ---------------------------------------------------------------------------

class TestDeleteOwnExpense:
    """POST with a valid id owned by the session user deletes the row and redirects."""

    def test_returns_302(self, auth_client):
        client, _, _, primary_expense_ids, _, make_conn = auth_client
        response = _post_delete(client, make_conn, primary_expense_ids[0])
        assert response.status_code == 302, (
            "Successful delete must return 302 redirect"
        )

    def test_redirects_to_profile(self, auth_client):
        client, _, _, primary_expense_ids, _, make_conn = auth_client
        response = _post_delete(client, make_conn, primary_expense_ids[0])
        assert "/profile" in response.headers["Location"], (
            "Successful delete must redirect to /profile"
        )

    def test_row_no_longer_exists_in_db(self, auth_client):
        client, _, _, primary_expense_ids, _, make_conn = auth_client
        target_id = primary_expense_ids[0]

        _post_delete(client, make_conn, target_id)

        assert not _expense_exists(make_conn, target_id), (
            f"Expense id={target_id} must no longer exist in the DB after deletion"
        )

    def test_expense_count_decreases_by_one(self, auth_client):
        client, primary_user_id, _, primary_expense_ids, _, make_conn = auth_client
        before = _count_expenses_for_user(make_conn, primary_user_id)

        _post_delete(client, make_conn, primary_expense_ids[0])

        after = _count_expenses_for_user(make_conn, primary_user_id)
        assert after == before - 1, (
            f"Expense count must drop by 1 after deletion (was {before}, got {after})"
        )

    def test_other_own_expenses_remain(self, auth_client):
        """Deleting one expense must not affect the user's other expenses."""
        client, primary_user_id, _, primary_expense_ids, _, make_conn = auth_client
        # Delete only the first expense
        _post_delete(client, make_conn, primary_expense_ids[0])

        # The remaining two expenses for the primary user must still exist
        for remaining_id in primary_expense_ids[1:]:
            assert _expense_exists(make_conn, remaining_id), (
                f"Expense id={remaining_id} must still exist after an unrelated deletion"
            )

    @pytest.mark.parametrize("expense_index", [0, 1, 2])
    def test_each_own_expense_can_be_deleted(self, auth_client, expense_index):
        """Every expense owned by the user can be independently deleted."""
        client, _, _, primary_expense_ids, _, make_conn = auth_client
        target_id = primary_expense_ids[expense_index]

        response = _post_delete(client, make_conn, target_id)

        assert response.status_code == 302, (
            f"Deleting own expense at index {expense_index} must redirect (302)"
        )
        assert not _expense_exists(make_conn, target_id), (
            f"Expense id={target_id} (index {expense_index}) must be deleted from DB"
        )


# ---------------------------------------------------------------------------
# 4. Ownership enforcement — cannot delete another user's expense
# ---------------------------------------------------------------------------

class TestOwnershipEnforcement:
    """POST with an id belonging to another user must not delete it."""

    def test_foreign_expense_post_returns_302(self, auth_client):
        """The redirect must still happen — the response is silent about the failure."""
        client, _, _, _, other_expense_id, make_conn = auth_client
        response = _post_delete(client, make_conn, other_expense_id)
        assert response.status_code == 302, (
            "Attempting to delete another user's expense must still return 302"
        )

    def test_foreign_expense_redirects_to_profile(self, auth_client):
        client, _, _, _, other_expense_id, make_conn = auth_client
        response = _post_delete(client, make_conn, other_expense_id)
        assert "/profile" in response.headers["Location"], (
            "Attempting to delete another user's expense must redirect to /profile"
        )

    def test_foreign_expense_row_not_deleted(self, auth_client):
        """The other user's expense row must survive the cross-user delete attempt."""
        client, _, _, _, other_expense_id, make_conn = auth_client

        _post_delete(client, make_conn, other_expense_id)

        assert _expense_exists(make_conn, other_expense_id), (
            f"Other user's expense id={other_expense_id} must NOT be deleted "
            "when a different user posts the delete request"
        )

    def test_foreign_expense_primary_count_unchanged(self, auth_client):
        """Primary user's own expense count must not change when targeting another user's row."""
        client, primary_user_id, _, _, other_expense_id, make_conn = auth_client
        before = _count_expenses_for_user(make_conn, primary_user_id)

        _post_delete(client, make_conn, other_expense_id)

        after = _count_expenses_for_user(make_conn, primary_user_id)
        assert after == before, (
            "Primary user's expense count must not change when attempting "
            "to delete another user's expense"
        )

    def test_foreign_expense_other_count_unchanged(self, auth_client):
        """Other user's expense count must remain 1 after the failed delete attempt."""
        client, _, other_user_id, _, other_expense_id, make_conn = auth_client
        before = _count_expenses_for_user(make_conn, other_user_id)

        _post_delete(client, make_conn, other_expense_id)

        after = _count_expenses_for_user(make_conn, other_user_id)
        assert after == before, (
            "Other user's expense count must be unchanged after a cross-user delete attempt"
        )


# ---------------------------------------------------------------------------
# 5. Non-existent expense IDs — silent redirect, no crash
# ---------------------------------------------------------------------------

class TestNonExistentId:
    """POST with a non-existent id must silently redirect to /profile without error."""

    @pytest.mark.parametrize("bad_id", [99999, 1000000, 42])
    def test_nonexistent_id_returns_302(self, auth_client, bad_id):
        client, _, _, _, _, make_conn = auth_client
        response = _post_delete(client, make_conn, bad_id)
        assert response.status_code == 302, (
            f"POST with non-existent id={bad_id} must return 302"
        )

    @pytest.mark.parametrize("bad_id", [99999, 1000000, 42])
    def test_nonexistent_id_redirects_to_profile(self, auth_client, bad_id):
        client, _, _, _, _, make_conn = auth_client
        response = _post_delete(client, make_conn, bad_id)
        assert "/profile" in response.headers["Location"], (
            f"POST with non-existent id={bad_id} must redirect to /profile"
        )

    @pytest.mark.parametrize("bad_id", [99999, 1000000, 42])
    def test_nonexistent_id_leaves_db_intact(self, auth_client, bad_id):
        """All existing expense rows must be undisturbed when the target id is missing."""
        client, primary_user_id, other_user_id, primary_expense_ids, other_expense_id, make_conn = auth_client
        before_primary = _count_expenses_for_user(make_conn, primary_user_id)
        before_other   = _count_expenses_for_user(make_conn, other_user_id)

        _post_delete(client, make_conn, bad_id)

        assert _count_expenses_for_user(make_conn, primary_user_id) == before_primary, (
            "Primary user's expense count must not change for a non-existent id"
        )
        assert _count_expenses_for_user(make_conn, other_user_id) == before_other, (
            "Other user's expense count must not change for a non-existent id"
        )


# ---------------------------------------------------------------------------
# 6. Implicit stats update — row count reflects deletion
# ---------------------------------------------------------------------------

class TestImplicitStatsUpdate:
    """
    After a successful delete the expense is absent from the DB, which means
    any stat computed from the expenses table (count, total) will be correct
    automatically. These tests confirm the DB state is clean.
    """

    def test_deleted_expense_absent_from_all_user_rows(self, auth_client):
        client, primary_user_id, _, primary_expense_ids, _, make_conn = auth_client
        target_id = primary_expense_ids[1]  # middle expense

        _post_delete(client, make_conn, target_id)

        conn = make_conn()
        try:
            all_ids = [
                row["id"]
                for row in conn.execute(
                    "SELECT id FROM expenses WHERE user_id = ?", (primary_user_id,)
                ).fetchall()
            ]
        finally:
            conn.close()

        assert target_id not in all_ids, (
            f"Deleted expense id={target_id} must not appear in any "
            "subsequent query of the user's expenses"
        )

    def test_remaining_expenses_data_intact(self, auth_client):
        """After one deletion, the surviving rows must retain their original data."""
        client, primary_user_id, _, primary_expense_ids, _, make_conn = auth_client
        # Delete the first expense; the other two must be intact
        _post_delete(client, make_conn, primary_expense_ids[0])

        conn = make_conn()
        try:
            rows = conn.execute(
                "SELECT id, amount FROM expenses WHERE user_id = ? ORDER BY id",
                (primary_user_id,),
            ).fetchall()
        finally:
            conn.close()

        assert len(rows) == 2, (
            "Exactly 2 expenses must remain for primary user after one deletion"
        )
        surviving_ids = [r["id"] for r in rows]
        assert primary_expense_ids[1] in surviving_ids, (
            "Second primary expense must survive the deletion of the first"
        )
        assert primary_expense_ids[2] in surviving_ids, (
            "Third primary expense must survive the deletion of the first"
        )

    def test_expense_count_for_other_user_unchanged_after_own_delete(self, auth_client):
        """Deleting own expense must not affect the other user's row count."""
        client, _, other_user_id, primary_expense_ids, _, make_conn = auth_client
        before = _count_expenses_for_user(make_conn, other_user_id)

        _post_delete(client, make_conn, primary_expense_ids[0])

        after = _count_expenses_for_user(make_conn, other_user_id)
        assert after == before, (
            "Other user's expense count must be unaffected by primary user's deletion"
        )
