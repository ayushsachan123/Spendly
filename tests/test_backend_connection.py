import pytest
import sqlite3
from unittest.mock import patch
from werkzeug.security import generate_password_hash

import app as flask_app
from database import queries


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mem_db():
    """In-memory SQLite database pre-loaded with schema and one user + expenses."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript("""
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
    """)
    conn.execute(
        "INSERT INTO users (name, email, password_hash, created_at) VALUES (?, ?, ?, ?)",
        ("Demo User", "demo@spendly.com", generate_password_hash("demo123"), "2026-01-15 10:00:00"),
    )
    user_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    expenses = [
        (user_id, 450.00,  "Food",          "2026-06-01", "Grocery run"),
        (user_id, 150.00,  "Transport",     "2026-06-02", "Metro pass"),
        (user_id, 1200.00, "Bills",         "2026-06-03", "Electricity bill"),
        (user_id, 800.00,  "Health",        "2026-06-05", "Doctor visit"),
        (user_id, 350.00,  "Entertainment", "2026-06-08", "Movie tickets"),
        (user_id, 2500.00, "Shopping",      "2026-06-10", "New shoes"),
        (user_id, 320.00,  "Food",          "2026-06-12", "Restaurant dinner"),
        (user_id, 200.00,  "Other",         "2026-06-15", "Miscellaneous"),
    ]
    conn.executemany(
        "INSERT INTO expenses (user_id, amount, category, date, description) VALUES (?, ?, ?, ?, ?)",
        expenses,
    )
    conn.commit()
    yield conn, user_id
    conn.close()


@pytest.fixture
def empty_db():
    """In-memory DB with schema but no expenses (one user only)."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript("""
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
    """)
    conn.execute(
        "INSERT INTO users (name, email, password_hash, created_at) VALUES (?, ?, ?, ?)",
        ("New User", "new@spendly.com", generate_password_hash("pass1234"), "2026-06-01 08:00:00"),
    )
    user_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.commit()
    yield conn, user_id
    conn.close()


# ---------------------------------------------------------------------------
# Unit tests — get_user_by_id
# ---------------------------------------------------------------------------

def test_get_user_by_id_valid(mem_db):
    conn, user_id = mem_db
    with patch("database.queries.get_db", return_value=conn):
        result = queries.get_user_by_id(user_id)
    assert result is not None
    assert result["name"] == "Demo User"
    assert result["email"] == "demo@spendly.com"
    assert result["initials"] == "DU"
    assert result["member_since"] == "January 2026"


def test_get_user_by_id_missing(mem_db):
    conn, _ = mem_db
    with patch("database.queries.get_db", return_value=conn):
        result = queries.get_user_by_id(99999)
    assert result is None


# ---------------------------------------------------------------------------
# Unit tests — get_summary_stats
# ---------------------------------------------------------------------------

def test_get_summary_stats_with_expenses(mem_db):
    conn, user_id = mem_db
    with patch("database.queries.get_db", return_value=conn):
        stats = queries.get_summary_stats(user_id)
    assert stats["transaction_count"] == 8
    assert stats["total_spent"] == "₹5,970.00"
    assert stats["top_category"] == "Shopping"


def test_get_summary_stats_no_expenses(empty_db):
    conn, user_id = empty_db
    with patch("database.queries.get_db", return_value=conn):
        stats = queries.get_summary_stats(user_id)
    assert stats["transaction_count"] == 0
    assert stats["total_spent"] == "₹0.00"
    assert stats["top_category"] == "—"


# ---------------------------------------------------------------------------
# Unit tests — get_recent_transactions
# ---------------------------------------------------------------------------

def test_get_recent_transactions_ordered(mem_db):
    conn, user_id = mem_db
    with patch("database.queries.get_db", return_value=conn):
        txns = queries.get_recent_transactions(user_id)
    assert len(txns) == 8
    # newest first
    assert txns[0]["date"] == "15 Jun 2026"
    assert txns[-1]["date"] == "01 Jun 2026"
    for txn in txns:
        assert "date" in txn
        assert "description" in txn
        assert "category" in txn
        assert txn["amount"].startswith("₹")


def test_get_recent_transactions_empty(empty_db):
    conn, user_id = empty_db
    with patch("database.queries.get_db", return_value=conn):
        txns = queries.get_recent_transactions(user_id)
    assert txns == []


# ---------------------------------------------------------------------------
# Unit tests — get_category_breakdown
# ---------------------------------------------------------------------------

def test_get_category_breakdown_pct_sums_100(mem_db):
    conn, user_id = mem_db
    with patch("database.queries.get_db", return_value=conn):
        cats = queries.get_category_breakdown(user_id)
    assert len(cats) == 7
    assert sum(c["percent"] for c in cats) == 100
    # ordered by amount descending — Shopping is highest (2500)
    assert cats[0]["name"] == "Shopping"
    for cat in cats:
        assert isinstance(cat["percent"], int)
        assert cat["amount"].startswith("₹")


def test_get_category_breakdown_empty(empty_db):
    conn, user_id = empty_db
    with patch("database.queries.get_db", return_value=conn):
        cats = queries.get_category_breakdown(user_id)
    assert cats == []


# ---------------------------------------------------------------------------
# Route tests
# ---------------------------------------------------------------------------

@pytest.fixture
def client(mem_db):
    conn, user_id = mem_db
    flask_app.app.config["TESTING"] = True
    flask_app.app.config["SECRET_KEY"] = "test-secret"
    with flask_app.app.test_client() as client:
        with patch("database.queries.get_db", return_value=conn):
            yield client, user_id


def test_profile_unauthenticated():
    flask_app.app.config["TESTING"] = True
    with flask_app.app.test_client() as c:
        response = c.get("/profile")
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_profile_authenticated(tmp_path):
    """Use a real temp-file DB so each get_db() call opens a fresh connection."""
    db_path = str(tmp_path / "test.db")
    real_conn = sqlite3.connect(db_path)
    real_conn.row_factory = sqlite3.Row
    real_conn.execute("PRAGMA foreign_keys = ON")
    real_conn.executescript("""
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
    """)
    real_conn.execute(
        "INSERT INTO users (name, email, password_hash, created_at) VALUES (?, ?, ?, ?)",
        ("Demo User", "demo@spendly.com", generate_password_hash("demo123"), "2026-01-15 10:00:00"),
    )
    user_id = real_conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    real_conn.executemany(
        "INSERT INTO expenses (user_id, amount, category, date, description) VALUES (?, ?, ?, ?, ?)",
        [
            (user_id, 450.00,  "Food",          "2026-06-01", "Grocery run"),
            (user_id, 150.00,  "Transport",     "2026-06-02", "Metro pass"),
            (user_id, 1200.00, "Bills",         "2026-06-03", "Electricity bill"),
            (user_id, 800.00,  "Health",        "2026-06-05", "Doctor visit"),
            (user_id, 350.00,  "Entertainment", "2026-06-08", "Movie tickets"),
            (user_id, 2500.00, "Shopping",      "2026-06-10", "New shoes"),
            (user_id, 320.00,  "Food",          "2026-06-12", "Restaurant dinner"),
            (user_id, 200.00,  "Other",         "2026-06-15", "Miscellaneous"),
        ],
    )
    real_conn.commit()
    real_conn.close()

    def make_conn():
        c = sqlite3.connect(db_path)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA foreign_keys = ON")
        return c

    flask_app.app.config["TESTING"] = True
    flask_app.app.config["SECRET_KEY"] = "test-secret"
    with flask_app.app.test_client() as c:
        with c.session_transaction() as sess:
            sess["user_id"] = user_id
            sess["user_name"] = "Demo User"
        with patch("database.queries.get_db", side_effect=make_conn):
            response = c.get("/profile")
    assert response.status_code == 200
    html = response.data.decode()
    assert "Demo User" in html
    assert "demo@spendly.com" in html
    assert "₹" in html
