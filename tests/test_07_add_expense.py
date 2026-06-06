"""
tests/test_07_add_expense.py

Tests for Step 7: Add Expense feature.

Routes under test:
  GET  /expenses/add  — render the add-expense form (auth required)
  POST /expenses/add  — validate, insert, redirect to /profile (auth required)

Fixture strategy mirrors test_06_date_filter.py exactly:
  - db_path  : temp-file SQLite DB with schema + one seed user
  - auth_client : Flask test client with session pre-set to seed user
  - Unauthenticated tests spin up a bare test_client() inside the test itself

DB writes are intercepted by patching app.get_db with a factory that opens
fresh connections to the same temp-file DB (side_effect=make_conn).
GET requests that do not touch the DB are issued without patching.
"""

import sqlite3
from datetime import datetime

import pytest
from unittest.mock import patch
from werkzeug.security import generate_password_hash

import app as flask_app


# ---------------------------------------------------------------------------
# Schema — must match production schema in database/db.py
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

_VALID_CATEGORIES = [
    "Food", "Transport", "Bills", "Health",
    "Entertainment", "Shopping", "Other",
]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def db_path(tmp_path):
    """
    Temp-file SQLite DB with schema + one seed user.
    Returns (path_str, user_id).
    The temp-file approach is required because get_db is called multiple
    times per request; an in-memory DB cannot be shared across connections.
    """
    path = str(tmp_path / "test.db")
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(_SCHEMA)
    conn.execute(
        "INSERT INTO users (name, email, password_hash, created_at) VALUES (?, ?, ?, ?)",
        (
            "Demo User",
            "demo@spendly.com",
            generate_password_hash("demo123"),
            "2026-01-15 10:00:00",
        ),
    )
    user_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.commit()
    conn.close()
    return path, user_id


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
    Flask test client pre-authenticated as the seed demo user.
    Yields (client, user_id, make_conn) so tests can drive get_db patches.
    """
    path, user_id = db_path
    make_conn = _make_conn_factory(path)

    flask_app.app.config["TESTING"] = True
    flask_app.app.config["SECRET_KEY"] = "test-secret"

    with flask_app.app.test_client() as client:
        with client.session_transaction() as sess:
            sess["user_id"] = user_id
            sess["user_name"] = "Demo User"
        yield client, user_id, make_conn


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _post_add(client, make_conn, data):
    """Issue a POST /expenses/add with get_db patched to the temp-file DB."""
    with patch("app.get_db", side_effect=make_conn):
        return client.post("/expenses/add", data=data)


def _get_add(client):
    """Issue a GET /expenses/add — route does not call get_db on GET."""
    return client.get("/expenses/add")


def _count_expenses(make_conn, user_id):
    """Return the number of expense rows for user_id."""
    conn = make_conn()
    try:
        row = conn.execute(
            "SELECT COUNT(*) AS cnt FROM expenses WHERE user_id = ?", (user_id,)
        ).fetchone()
        return row["cnt"]
    finally:
        conn.close()


def _fetch_latest_expense(make_conn, user_id):
    """Return the most recently inserted expense row for user_id, or None."""
    conn = make_conn()
    try:
        return conn.execute(
            "SELECT * FROM expenses WHERE user_id = ? ORDER BY id DESC LIMIT 1",
            (user_id,),
        ).fetchone()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# 1. Auth guard
# ---------------------------------------------------------------------------

class TestAuthGuard:
    """Both GET and POST must redirect unauthenticated users to /login."""

    def test_get_unauthenticated_redirects_to_login(self):
        flask_app.app.config["TESTING"] = True
        with flask_app.app.test_client() as c:
            response = c.get("/expenses/add")
        assert response.status_code == 302, (
            "Unauthenticated GET /expenses/add must return 302"
        )
        assert "/login" in response.headers["Location"], (
            "Unauthenticated GET /expenses/add must redirect to /login"
        )

    def test_post_unauthenticated_redirects_to_login(self):
        flask_app.app.config["TESTING"] = True
        with flask_app.app.test_client() as c:
            response = c.post("/expenses/add", data={
                "amount": "100",
                "category": "Food",
                "date": "2026-06-01",
                "description": "Test",
            })
        assert response.status_code == 302, (
            "Unauthenticated POST /expenses/add must return 302"
        )
        assert "/login" in response.headers["Location"], (
            "Unauthenticated POST /expenses/add must redirect to /login"
        )

    def test_get_unauthenticated_does_not_render_form(self):
        flask_app.app.config["TESTING"] = True
        with flask_app.app.test_client() as c:
            response = c.get("/expenses/add")
        # Must not render the add-expense form for unauthenticated users
        assert b'name="amount"' not in response.data, (
            "Unauthenticated GET must not render the add-expense form"
        )


# ---------------------------------------------------------------------------
# 2. GET form rendering
# ---------------------------------------------------------------------------

class TestGetForm:
    """GET /expenses/add while authenticated renders the add-expense form."""

    def test_get_returns_200(self, auth_client):
        client, _, _ = auth_client
        response = _get_add(client)
        assert response.status_code == 200, "Authenticated GET /expenses/add must return 200"

    def test_get_renders_amount_field(self, auth_client):
        client, _, _ = auth_client
        response = _get_add(client)
        assert b'name="amount"' in response.data, (
            "Form must contain an amount input field"
        )

    def test_get_renders_category_field(self, auth_client):
        client, _, _ = auth_client
        response = _get_add(client)
        assert b'name="category"' in response.data, (
            "Form must contain a category select field"
        )

    def test_get_renders_date_field(self, auth_client):
        client, _, _ = auth_client
        response = _get_add(client)
        assert b'name="date"' in response.data, (
            "Form must contain a date input field"
        )

    def test_get_renders_description_field(self, auth_client):
        client, _, _ = auth_client
        response = _get_add(client)
        assert b'name="description"' in response.data, (
            "Form must contain a description textarea field"
        )

    def test_get_date_prefilled_with_today(self, auth_client):
        client, _, _ = auth_client
        response = _get_add(client)
        today = datetime.now().strftime("%Y-%m-%d")
        assert today.encode() in response.data, (
            f"Date input must be pre-filled with today's date ({today})"
        )

    def test_get_all_seven_categories_present(self, auth_client):
        client, _, _ = auth_client
        response = _get_add(client)
        html = response.data.decode()
        for cat in _VALID_CATEGORIES:
            assert cat in html, (
                f"Category option '{cat}' must be present in the form"
            )

    def test_get_cancel_link_points_to_profile(self, auth_client):
        client, _, _ = auth_client
        response = _get_add(client)
        html = response.data.decode()
        assert 'href="/profile"' in html, (
            "Cancel link must point to /profile"
        )

    def test_get_cancel_link_text_present(self, auth_client):
        client, _, _ = auth_client
        response = _get_add(client)
        assert b"Cancel" in response.data, (
            "Page must contain a Cancel link"
        )

    def test_get_page_heading_present(self, auth_client):
        client, _, _ = auth_client
        response = _get_add(client)
        assert b"Add Expense" in response.data, (
            "Page must render an 'Add Expense' heading"
        )

    def test_get_form_uses_post_method(self, auth_client):
        client, _, _ = auth_client
        response = _get_add(client)
        html = response.data.decode()
        assert 'method="POST"' in html or "method=POST" in html, (
            "Add-expense form must use POST method"
        )


# ---------------------------------------------------------------------------
# 3. POST success
# ---------------------------------------------------------------------------

class TestPostSuccess:
    """Valid POST inserts a row in the DB and redirects 302 to /profile."""

    def test_valid_post_redirects_to_profile(self, auth_client):
        client, _, make_conn = auth_client
        response = _post_add(client, make_conn, {
            "amount": "250.50",
            "category": "Food",
            "date": "2026-06-10",
            "description": "Lunch at cafe",
        })
        assert response.status_code == 302, (
            "Valid POST must return 302 redirect"
        )
        assert "/profile" in response.headers["Location"], (
            "Valid POST must redirect to /profile"
        )

    def test_valid_post_inserts_row_in_db(self, auth_client):
        client, user_id, make_conn = auth_client
        before = _count_expenses(make_conn, user_id)
        _post_add(client, make_conn, {
            "amount": "500",
            "category": "Transport",
            "date": "2026-06-15",
            "description": "Taxi ride",
        })
        after = _count_expenses(make_conn, user_id)
        assert after == before + 1, (
            "Valid POST must insert exactly one new expense row"
        )

    def test_valid_post_stores_correct_amount(self, auth_client):
        client, user_id, make_conn = auth_client
        _post_add(client, make_conn, {
            "amount": "123.45",
            "category": "Bills",
            "date": "2026-06-20",
            "description": "Electricity",
        })
        row = _fetch_latest_expense(make_conn, user_id)
        assert row is not None, "An expense row must exist after valid POST"
        assert abs(row["amount"] - 123.45) < 0.001, (
            f"Stored amount must be 123.45, got {row['amount']}"
        )

    def test_valid_post_stores_correct_category(self, auth_client):
        client, user_id, make_conn = auth_client
        _post_add(client, make_conn, {
            "amount": "80",
            "category": "Health",
            "date": "2026-06-21",
            "description": "Pharmacy",
        })
        row = _fetch_latest_expense(make_conn, user_id)
        assert row["category"] == "Health", (
            f"Stored category must be 'Health', got '{row['category']}'"
        )

    def test_valid_post_stores_correct_date(self, auth_client):
        client, user_id, make_conn = auth_client
        _post_add(client, make_conn, {
            "amount": "300",
            "category": "Shopping",
            "date": "2026-07-04",
            "description": "Clothes",
        })
        row = _fetch_latest_expense(make_conn, user_id)
        assert row["date"] == "2026-07-04", (
            f"Stored date must be '2026-07-04', got '{row['date']}'"
        )

    def test_valid_post_stores_correct_description(self, auth_client):
        client, user_id, make_conn = auth_client
        _post_add(client, make_conn, {
            "amount": "99",
            "category": "Entertainment",
            "date": "2026-06-25",
            "description": "Cinema night",
        })
        row = _fetch_latest_expense(make_conn, user_id)
        assert row["description"] == "Cinema night", (
            f"Stored description must be 'Cinema night', got '{row['description']}'"
        )

    def test_valid_post_stores_correct_user_id(self, auth_client):
        client, user_id, make_conn = auth_client
        _post_add(client, make_conn, {
            "amount": "150",
            "category": "Other",
            "date": "2026-06-28",
            "description": "Miscellaneous",
        })
        row = _fetch_latest_expense(make_conn, user_id)
        assert row["user_id"] == user_id, (
            f"Stored user_id must match session user_id ({user_id}), got {row['user_id']}"
        )

    def test_valid_post_blank_description_succeeds(self, auth_client):
        """Blank description is optional — POST must still succeed."""
        client, user_id, make_conn = auth_client
        response = _post_add(client, make_conn, {
            "amount": "200",
            "category": "Food",
            "date": "2026-06-30",
            "description": "",
        })
        assert response.status_code == 302, (
            "Blank description must not cause validation failure"
        )
        assert "/profile" in response.headers["Location"], (
            "Blank description POST must redirect to /profile"
        )

    def test_valid_post_blank_description_stores_none_or_empty(self, auth_client):
        """Blank description should be stored as NULL or empty string — not crash."""
        client, user_id, make_conn = auth_client
        _post_add(client, make_conn, {
            "amount": "50",
            "category": "Food",
            "date": "2026-06-30",
            "description": "",
        })
        row = _fetch_latest_expense(make_conn, user_id)
        assert row is not None, "Expense row must exist after POST with blank description"
        # description may be stored as None or empty string — both are acceptable
        assert row["description"] is None or row["description"] == "", (
            "Blank description must be stored as NULL or empty string"
        )

    def test_valid_post_decimal_amount_stored_as_float(self, auth_client):
        """Amount submitted as a string with decimals must be stored as a float."""
        client, user_id, make_conn = auth_client
        _post_add(client, make_conn, {
            "amount": "19.99",
            "category": "Food",
            "date": "2026-06-15",
            "description": "Coffee",
        })
        row = _fetch_latest_expense(make_conn, user_id)
        assert isinstance(row["amount"], float), (
            f"amount column must be a float, got {type(row['amount'])}"
        )
        assert abs(row["amount"] - 19.99) < 0.001, (
            f"Stored amount must be 19.99, got {row['amount']}"
        )


# ---------------------------------------------------------------------------
# 4. POST validation failures
# ---------------------------------------------------------------------------

class TestPostValidation:
    """Each invalid input must re-render the form (200) with an error message."""

    # --- Amount validation ---

    def test_blank_amount_returns_200(self, auth_client):
        client, _, make_conn = auth_client
        response = _post_add(client, make_conn, {
            "amount": "",
            "category": "Food",
            "date": "2026-06-01",
            "description": "Test",
        })
        assert response.status_code == 200, (
            "Blank amount must re-render the form with 200"
        )

    def test_blank_amount_shows_error(self, auth_client):
        client, _, make_conn = auth_client
        response = _post_add(client, make_conn, {
            "amount": "",
            "category": "Food",
            "date": "2026-06-01",
            "description": "Test",
        })
        assert b"error" in response.data.lower() or b"amount" in response.data.lower(), (
            "Blank amount must show an error message"
        )

    def test_blank_amount_does_not_insert_row(self, auth_client):
        client, user_id, make_conn = auth_client
        before = _count_expenses(make_conn, user_id)
        _post_add(client, make_conn, {
            "amount": "",
            "category": "Food",
            "date": "2026-06-01",
            "description": "Test",
        })
        assert _count_expenses(make_conn, user_id) == before, (
            "Blank amount must not insert a row into the DB"
        )

    def test_non_numeric_amount_returns_200(self, auth_client):
        client, _, make_conn = auth_client
        response = _post_add(client, make_conn, {
            "amount": "abc",
            "category": "Food",
            "date": "2026-06-01",
            "description": "Test",
        })
        assert response.status_code == 200, (
            "Non-numeric amount must re-render the form with 200"
        )

    def test_non_numeric_amount_shows_error(self, auth_client):
        client, _, make_conn = auth_client
        response = _post_add(client, make_conn, {
            "amount": "not-a-number",
            "category": "Food",
            "date": "2026-06-01",
            "description": "",
        })
        html = response.data.decode()
        assert "error" in html.lower() or "amount" in html.lower(), (
            "Non-numeric amount must show an error message"
        )

    def test_non_numeric_amount_does_not_insert_row(self, auth_client):
        client, user_id, make_conn = auth_client
        before = _count_expenses(make_conn, user_id)
        _post_add(client, make_conn, {
            "amount": "twelve",
            "category": "Food",
            "date": "2026-06-01",
            "description": "",
        })
        assert _count_expenses(make_conn, user_id) == before, (
            "Non-numeric amount must not insert a row into the DB"
        )

    def test_zero_amount_returns_200(self, auth_client):
        client, _, make_conn = auth_client
        response = _post_add(client, make_conn, {
            "amount": "0",
            "category": "Food",
            "date": "2026-06-01",
            "description": "Test",
        })
        assert response.status_code == 200, (
            "Zero amount must re-render the form with 200"
        )

    def test_zero_amount_shows_error(self, auth_client):
        client, _, make_conn = auth_client
        response = _post_add(client, make_conn, {
            "amount": "0",
            "category": "Food",
            "date": "2026-06-01",
            "description": "",
        })
        html = response.data.decode()
        assert "error" in html.lower(), (
            "Zero amount must show an error message"
        )

    def test_zero_amount_does_not_insert_row(self, auth_client):
        client, user_id, make_conn = auth_client
        before = _count_expenses(make_conn, user_id)
        _post_add(client, make_conn, {
            "amount": "0",
            "category": "Food",
            "date": "2026-06-01",
            "description": "",
        })
        assert _count_expenses(make_conn, user_id) == before, (
            "Zero amount must not insert a row into the DB"
        )

    def test_negative_amount_returns_200(self, auth_client):
        client, _, make_conn = auth_client
        response = _post_add(client, make_conn, {
            "amount": "-50",
            "category": "Food",
            "date": "2026-06-01",
            "description": "Test",
        })
        assert response.status_code == 200, (
            "Negative amount must re-render the form with 200"
        )

    def test_negative_amount_shows_error(self, auth_client):
        client, _, make_conn = auth_client
        response = _post_add(client, make_conn, {
            "amount": "-100",
            "category": "Food",
            "date": "2026-06-01",
            "description": "",
        })
        html = response.data.decode()
        assert "error" in html.lower(), (
            "Negative amount must show an error message"
        )

    def test_negative_amount_does_not_insert_row(self, auth_client):
        client, user_id, make_conn = auth_client
        before = _count_expenses(make_conn, user_id)
        _post_add(client, make_conn, {
            "amount": "-0.01",
            "category": "Food",
            "date": "2026-06-01",
            "description": "",
        })
        assert _count_expenses(make_conn, user_id) == before, (
            "Negative amount must not insert a row into the DB"
        )

    # --- Date validation ---

    def test_blank_date_returns_200(self, auth_client):
        client, _, make_conn = auth_client
        response = _post_add(client, make_conn, {
            "amount": "100",
            "category": "Food",
            "date": "",
            "description": "Test",
        })
        assert response.status_code == 200, (
            "Blank date must re-render the form with 200"
        )

    def test_blank_date_shows_error(self, auth_client):
        client, _, make_conn = auth_client
        response = _post_add(client, make_conn, {
            "amount": "100",
            "category": "Food",
            "date": "",
            "description": "",
        })
        html = response.data.decode()
        assert "error" in html.lower(), (
            "Blank date must show an error message"
        )

    def test_blank_date_does_not_insert_row(self, auth_client):
        client, user_id, make_conn = auth_client
        before = _count_expenses(make_conn, user_id)
        _post_add(client, make_conn, {
            "amount": "100",
            "category": "Food",
            "date": "",
            "description": "",
        })
        assert _count_expenses(make_conn, user_id) == before, (
            "Blank date must not insert a row into the DB"
        )

    @pytest.mark.parametrize("bad_date", [
        "06-01-2026",       # DD-MM-YYYY instead of YYYY-MM-DD
        "2026/06/01",       # wrong separator
        "not-a-date",       # plain string
        "2026-13-01",       # month 13
        "2026-06-32",       # day 32
        "20260601",         # no separators
        "June 1, 2026",     # natural language
    ])
    def test_malformed_date_returns_200(self, auth_client, bad_date):
        client, _, make_conn = auth_client
        response = _post_add(client, make_conn, {
            "amount": "100",
            "category": "Food",
            "date": bad_date,
            "description": "",
        })
        assert response.status_code == 200, (
            f"Malformed date '{bad_date}' must re-render the form with 200"
        )

    @pytest.mark.parametrize("bad_date", [
        "06-01-2026",
        "2026/06/01",
        "not-a-date",
        "2026-13-01",
        "2026-06-32",
    ])
    def test_malformed_date_shows_error(self, auth_client, bad_date):
        client, _, make_conn = auth_client
        response = _post_add(client, make_conn, {
            "amount": "100",
            "category": "Food",
            "date": bad_date,
            "description": "",
        })
        html = response.data.decode()
        assert "error" in html.lower(), (
            f"Malformed date '{bad_date}' must show an error message"
        )

    @pytest.mark.parametrize("bad_date", [
        "06-01-2026",
        "not-a-date",
        "2026-13-01",
    ])
    def test_malformed_date_does_not_insert_row(self, auth_client, bad_date):
        client, user_id, make_conn = auth_client
        before = _count_expenses(make_conn, user_id)
        _post_add(client, make_conn, {
            "amount": "100",
            "category": "Food",
            "date": bad_date,
            "description": "",
        })
        assert _count_expenses(make_conn, user_id) == before, (
            f"Malformed date '{bad_date}' must not insert a row into the DB"
        )

    # --- Category validation ---

    def test_invalid_category_returns_200(self, auth_client):
        client, _, make_conn = auth_client
        response = _post_add(client, make_conn, {
            "amount": "100",
            "category": "Luxury",   # not in CATEGORIES
            "date": "2026-06-01",
            "description": "Test",
        })
        assert response.status_code == 200, (
            "Invalid category must re-render the form with 200"
        )

    def test_invalid_category_shows_error(self, auth_client):
        client, _, make_conn = auth_client
        response = _post_add(client, make_conn, {
            "amount": "100",
            "category": "Travel",   # not in CATEGORIES
            "date": "2026-06-01",
            "description": "",
        })
        html = response.data.decode()
        assert "error" in html.lower(), (
            "Invalid category must show an error message"
        )

    def test_invalid_category_does_not_insert_row(self, auth_client):
        client, user_id, make_conn = auth_client
        before = _count_expenses(make_conn, user_id)
        _post_add(client, make_conn, {
            "amount": "100",
            "category": "NotACategory",
            "date": "2026-06-01",
            "description": "",
        })
        assert _count_expenses(make_conn, user_id) == before, (
            "Invalid category must not insert a row into the DB"
        )

    def test_blank_category_returns_200(self, auth_client):
        client, _, make_conn = auth_client
        response = _post_add(client, make_conn, {
            "amount": "100",
            "category": "",
            "date": "2026-06-01",
            "description": "",
        })
        assert response.status_code == 200, (
            "Blank category must re-render the form with 200"
        )

    def test_blank_category_does_not_insert_row(self, auth_client):
        client, user_id, make_conn = auth_client
        before = _count_expenses(make_conn, user_id)
        _post_add(client, make_conn, {
            "amount": "100",
            "category": "",
            "date": "2026-06-01",
            "description": "",
        })
        assert _count_expenses(make_conn, user_id) == before, (
            "Blank category must not insert a row into the DB"
        )

    # --- Description is optional ---

    def test_blank_description_does_not_fail_validation(self, auth_client):
        """Description is optional — blank description with valid other fields must succeed."""
        client, _, make_conn = auth_client
        response = _post_add(client, make_conn, {
            "amount": "75",
            "category": "Other",
            "date": "2026-06-05",
            "description": "",
        })
        assert response.status_code == 302, (
            "Blank description with all other fields valid must redirect (302)"
        )

    # --- Parametrized: all valid categories are accepted ---

    @pytest.mark.parametrize("cat", _VALID_CATEGORIES)
    def test_each_valid_category_is_accepted(self, auth_client, cat):
        client, _, make_conn = auth_client
        response = _post_add(client, make_conn, {
            "amount": "10",
            "category": cat,
            "date": "2026-06-01",
            "description": "",
        })
        assert response.status_code == 302, (
            f"Valid category '{cat}' must be accepted and redirect (302)"
        )


# ---------------------------------------------------------------------------
# 5. Re-population of form fields on validation failure
# ---------------------------------------------------------------------------

class TestPostRepopulation:
    """
    When validation fails the form must be re-rendered with all previously
    submitted field values pre-populated so the user does not lose their input.
    """

    def test_invalid_amount_repopulates_amount(self, auth_client):
        client, _, make_conn = auth_client
        response = _post_add(client, make_conn, {
            "amount": "badvalue",
            "category": "Food",
            "date": "2026-06-10",
            "description": "Some desc",
        })
        assert b"badvalue" in response.data, (
            "Re-rendered form must contain the submitted (invalid) amount value"
        )

    def test_invalid_amount_repopulates_category(self, auth_client):
        client, _, make_conn = auth_client
        response = _post_add(client, make_conn, {
            "amount": "badvalue",
            "category": "Transport",
            "date": "2026-06-10",
            "description": "Taxi",
        })
        html = response.data.decode()
        # The selected option value or a visible indicator of 'Transport' must be present
        assert "Transport" in html, (
            "Re-rendered form must retain the submitted category value"
        )

    def test_invalid_amount_repopulates_date(self, auth_client):
        client, _, make_conn = auth_client
        response = _post_add(client, make_conn, {
            "amount": "badvalue",
            "category": "Food",
            "date": "2026-06-10",
            "description": "",
        })
        assert b"2026-06-10" in response.data, (
            "Re-rendered form must retain the submitted date value"
        )

    def test_invalid_amount_repopulates_description(self, auth_client):
        client, _, make_conn = auth_client
        response = _post_add(client, make_conn, {
            "amount": "badvalue",
            "category": "Food",
            "date": "2026-06-10",
            "description": "Lunch meeting",
        })
        assert b"Lunch meeting" in response.data, (
            "Re-rendered form must retain the submitted description value"
        )

    def test_invalid_date_repopulates_amount(self, auth_client):
        client, _, make_conn = auth_client
        response = _post_add(client, make_conn, {
            "amount": "350",
            "category": "Bills",
            "date": "not-a-date",
            "description": "Electric bill",
        })
        assert b"350" in response.data, (
            "Re-rendered form must retain the valid amount even when date fails"
        )

    def test_invalid_date_repopulates_category(self, auth_client):
        client, _, make_conn = auth_client
        response = _post_add(client, make_conn, {
            "amount": "200",
            "category": "Health",
            "date": "not-a-date",
            "description": "Check-up",
        })
        html = response.data.decode()
        assert "Health" in html, (
            "Re-rendered form must retain the submitted category when date fails"
        )

    def test_invalid_date_repopulates_date(self, auth_client):
        client, _, make_conn = auth_client
        response = _post_add(client, make_conn, {
            "amount": "200",
            "category": "Health",
            "date": "06/15/2026",
            "description": "",
        })
        assert b"06/15/2026" in response.data, (
            "Re-rendered form must retain the submitted (invalid) date string"
        )

    def test_invalid_date_repopulates_description(self, auth_client):
        client, _, make_conn = auth_client
        response = _post_add(client, make_conn, {
            "amount": "100",
            "category": "Shopping",
            "date": "baddate",
            "description": "Online order",
        })
        assert b"Online order" in response.data, (
            "Re-rendered form must retain the submitted description when date fails"
        )

    def test_invalid_category_repopulates_amount(self, auth_client):
        client, _, make_conn = auth_client
        response = _post_add(client, make_conn, {
            "amount": "999",
            "category": "Groceries",    # not a valid category
            "date": "2026-06-20",
            "description": "",
        })
        assert b"999" in response.data, (
            "Re-rendered form must retain the valid amount when category fails"
        )

    def test_invalid_category_repopulates_date(self, auth_client):
        client, _, make_conn = auth_client
        response = _post_add(client, make_conn, {
            "amount": "50",
            "category": "Groceries",    # not a valid category
            "date": "2026-06-20",
            "description": "",
        })
        assert b"2026-06-20" in response.data, (
            "Re-rendered form must retain the valid date when category fails"
        )

    def test_invalid_category_shows_placeholder(self, auth_client):
        """Invalid category must not be echoed; the placeholder option must be present."""
        client, _, make_conn = auth_client
        response = _post_add(client, make_conn, {
            "amount": "50",
            "category": "Luxury",
            "date": "2026-06-20",
            "description": "",
        })
        assert b"Luxury" not in response.data, (
            "Rejected category value must not be rendered back into the select"
        )
        assert b"Select a category" in response.data, (
            "Placeholder option must be present when category is invalid"
        )

    def test_zero_amount_repopulates_all_fields(self, auth_client):
        """All submitted fields must survive a zero-amount validation failure."""
        client, _, make_conn = auth_client
        response = _post_add(client, make_conn, {
            "amount": "0",
            "category": "Entertainment",
            "date": "2026-07-01",
            "description": "Free movie",
        })
        html = response.data.decode()
        assert "0" in html, "Re-rendered form must contain amount '0'"
        assert "Entertainment" in html, "Re-rendered form must contain submitted category"
        assert "2026-07-01" in html, "Re-rendered form must contain submitted date"
        assert "Free movie" in html, "Re-rendered form must contain submitted description"
