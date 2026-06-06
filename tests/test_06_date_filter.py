"""
tests/test_06_date_filter.py

Tests for Step 6: Date range filter on the /profile page.

Seed data (demo@spendly.com / demo123) used as the reference fixture:
  2026-06-01  Food          450.00   Grocery run
  2026-06-02  Transport     150.00   Metro pass
  2026-06-03  Bills        1200.00   Electricity bill
  2026-06-05  Health        800.00   Doctor visit
  2026-06-08  Entertainment 350.00   Movie tickets
  2026-06-10  Shopping     2500.00   New shoes
  2026-06-12  Food          320.00   Restaurant dinner
  2026-06-15  Other         200.00   Miscellaneous
  ─────────────────────────────────────────────────
  All-time total: ₹5,970.00  |  8 transactions  |  top: Shopping
"""

import sqlite3
import pytest
from unittest.mock import patch

from werkzeug.security import generate_password_hash

import app as flask_app


# ---------------------------------------------------------------------------
# Seed data constants — single source of truth
# ---------------------------------------------------------------------------

_SEED_EXPENSES = [
    (None, 450.00,  "Food",          "2026-06-01", "Grocery run"),
    (None, 150.00,  "Transport",     "2026-06-02", "Metro pass"),
    (None, 1200.00, "Bills",         "2026-06-03", "Electricity bill"),
    (None, 800.00,  "Health",        "2026-06-05", "Doctor visit"),
    (None, 350.00,  "Entertainment", "2026-06-08", "Movie tickets"),
    (None, 2500.00, "Shopping",      "2026-06-10", "New shoes"),
    (None, 320.00,  "Food",          "2026-06-12", "Restaurant dinner"),
    (None, 200.00,  "Other",         "2026-06-15", "Miscellaneous"),
]

ALL_TIME_TOTAL = "₹5,970.00"
ALL_TIME_COUNT = 8
ALL_TIME_TOP   = "Shopping"

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
def mem_db():
    """
    In-memory SQLite DB with schema + full seed data.
    Yields (conn, user_id).
    """
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(_SCHEMA)

    conn.execute(
        "INSERT INTO users (name, email, password_hash, created_at) VALUES (?, ?, ?, ?)",
        ("Demo User", "demo@spendly.com", generate_password_hash("demo123"), "2026-01-15 10:00:00"),
    )
    user_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    rows = [(user_id, amt, cat, dt, desc) for (_, amt, cat, dt, desc) in _SEED_EXPENSES]
    conn.executemany(
        "INSERT INTO expenses (user_id, amount, category, date, description) VALUES (?, ?, ?, ?, ?)",
        rows,
    )
    conn.commit()
    yield conn, user_id
    conn.close()


def _make_conn_factory(db_path: str):
    """Return a callable that opens a fresh connection to db_path each call."""
    def factory():
        c = sqlite3.connect(db_path)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA foreign_keys = ON")
        return c
    return factory


@pytest.fixture
def db_path(tmp_path):
    """
    Temp-file SQLite DB with schema + seed data.
    Needed when the route handler calls get_db() multiple times (once per
    query helper), because an in-memory connection cannot be shared safely
    across calls patched with side_effect.
    Returns the path string; callers use _make_conn_factory(db_path).
    """
    path = str(tmp_path / "test.db")
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(_SCHEMA)

    conn.execute(
        "INSERT INTO users (name, email, password_hash, created_at) VALUES (?, ?, ?, ?)",
        ("Demo User", "demo@spendly.com", generate_password_hash("demo123"), "2026-01-15 10:00:00"),
    )
    user_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    rows = [(user_id, amt, cat, dt, desc) for (_, amt, cat, dt, desc) in _SEED_EXPENSES]
    conn.executemany(
        "INSERT INTO expenses (user_id, amount, category, date, description) VALUES (?, ?, ?, ?, ?)",
        rows,
    )
    conn.commit()
    conn.close()
    return path, user_id


@pytest.fixture
def auth_client(db_path):
    """
    Flask test client pre-authenticated as the seed demo user,
    pointing at the temp-file DB.
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
# Helper
# ---------------------------------------------------------------------------

def _get(client, make_conn, url):
    """Issue a GET request with get_db patched to the temp-file DB."""
    with patch("database.queries.get_db", side_effect=make_conn):
        return client.get(url)


# ---------------------------------------------------------------------------
# Auth guard
# ---------------------------------------------------------------------------

class TestAuthGuard:
    def test_unauthenticated_redirects_to_login(self):
        flask_app.app.config["TESTING"] = True
        with flask_app.app.test_client() as c:
            response = c.get("/profile")
        assert response.status_code == 302, "Unauthenticated /profile must redirect"
        assert "/login" in response.headers["Location"], "Must redirect to /login"

    def test_unauthenticated_with_filter_params_still_redirects(self):
        flask_app.app.config["TESTING"] = True
        with flask_app.app.test_client() as c:
            response = c.get("/profile?from=2026-06-01&to=2026-06-10")
        assert response.status_code == 302
        assert "/login" in response.headers["Location"]


# ---------------------------------------------------------------------------
# No-regression baseline (no query params)
# ---------------------------------------------------------------------------

class TestNoRegressionBaseline:
    def test_profile_no_params_returns_200(self, auth_client):
        client, _, make_conn = auth_client
        response = _get(client, make_conn, "/profile")
        assert response.status_code == 200, "Authenticated /profile must return 200"

    def test_profile_no_params_shows_all_time_total(self, auth_client):
        client, _, make_conn = auth_client
        response = _get(client, make_conn, "/profile")
        html = response.data.decode()
        assert ALL_TIME_TOTAL in html, (
            f"Unfiltered profile must show all-time total {ALL_TIME_TOTAL}"
        )

    def test_profile_no_params_shows_all_transactions(self, auth_client):
        client, _, make_conn = auth_client
        response = _get(client, make_conn, "/profile")
        html = response.data.decode()
        # The template renders each transaction as a <tr>; check that all 8
        # distinct descriptions appear in the rendered HTML.
        descriptions = [desc for (_, _, _, _, desc) in _SEED_EXPENSES]
        for desc in descriptions:
            assert desc in html, f"Unfiltered profile must contain transaction: {desc}"

    def test_profile_no_params_shows_top_category(self, auth_client):
        client, _, make_conn = auth_client
        response = _get(client, make_conn, "/profile")
        html = response.data.decode()
        assert ALL_TIME_TOP in html, (
            f"Unfiltered profile must show top category {ALL_TIME_TOP}"
        )

    def test_profile_no_params_inputs_are_empty(self, auth_client):
        """From / To inputs must be empty when no filter is active."""
        client, _, make_conn = auth_client
        response = _get(client, make_conn, "/profile")
        html = response.data.decode()
        # Both inputs should have an empty value attribute or no value
        assert 'name="from"' in html, "From input must be present"
        assert 'name="to"' in html, "To input must be present"
        # The value attribute should be empty (not populated)
        assert 'name="from"\n' in html or 'value=""' in html or (
            html.count('value="2026') == 0
        ), "Filter inputs must be empty when no filter param supplied"


# ---------------------------------------------------------------------------
# Filter form presence
# ---------------------------------------------------------------------------

class TestFilterFormPresence:
    def test_filter_form_exists(self, auth_client):
        client, _, make_conn = auth_client
        response = _get(client, make_conn, "/profile")
        html = response.data.decode()
        assert '<form' in html, "Profile page must contain a filter form"
        assert 'method="GET"' in html or "method=GET" in html, (
            "Filter form must use GET method"
        )

    def test_filter_form_has_from_input(self, auth_client):
        client, _, make_conn = auth_client
        response = _get(client, make_conn, "/profile")
        html = response.data.decode()
        assert 'name="from"' in html, "Filter form must have a 'from' input"

    def test_filter_form_has_to_input(self, auth_client):
        client, _, make_conn = auth_client
        response = _get(client, make_conn, "/profile")
        html = response.data.decode()
        assert 'name="to"' in html, "Filter form must have a 'to' input"

    def test_filter_form_has_apply_button(self, auth_client):
        client, _, make_conn = auth_client
        response = _get(client, make_conn, "/profile")
        html = response.data.decode()
        assert "Apply" in html, "Filter form must have an Apply submit button"

    def test_filter_form_has_clear_link(self, auth_client):
        client, _, make_conn = auth_client
        response = _get(client, make_conn, "/profile")
        html = response.data.decode()
        assert "Clear" in html, "Profile page must have a Clear link"
        # The clear link must point to /profile with no query params
        assert 'href="/profile"' in html, "Clear link must href to /profile (no params)"


# ---------------------------------------------------------------------------
# Happy path — full two-sided filter
# ---------------------------------------------------------------------------

class TestFullRangeFilter:
    """
    Range: 2026-06-01 to 2026-06-10 (inclusive)
    Matching expenses: 01-Food, 02-Transport, 03-Bills, 05-Health, 08-Entertainment, 10-Shopping
    Total: 450 + 150 + 1200 + 800 + 350 + 2500 = 5450  =>  ₹5,450.00
    Count: 6   Top category: Shopping (2500)
    """
    RANGE_FROM = "2026-06-01"
    RANGE_TO   = "2026-06-10"
    EXPECTED_TOTAL = "₹5,450.00"
    EXPECTED_COUNT = 6
    EXPECTED_TOP   = "Shopping"

    # Expenses that MUST appear
    IN_RANGE = ["Grocery run", "Metro pass", "Electricity bill",
                "Doctor visit", "Movie tickets", "New shoes"]
    # Expenses that must NOT appear
    OUT_OF_RANGE = ["Restaurant dinner", "Miscellaneous"]

    def test_filtered_total_reflects_range(self, auth_client):
        client, _, make_conn = auth_client
        response = _get(
            client, make_conn,
            f"/profile?from={self.RANGE_FROM}&to={self.RANGE_TO}"
        )
        assert response.status_code == 200
        html = response.data.decode()
        assert self.EXPECTED_TOTAL in html, (
            f"Filtered total should be {self.EXPECTED_TOTAL}"
        )

    def test_filtered_in_range_transactions_visible(self, auth_client):
        client, _, make_conn = auth_client
        response = _get(
            client, make_conn,
            f"/profile?from={self.RANGE_FROM}&to={self.RANGE_TO}"
        )
        html = response.data.decode()
        for desc in self.IN_RANGE:
            assert desc in html, f"Transaction '{desc}' should appear in filtered view"

    def test_filtered_out_of_range_transactions_hidden(self, auth_client):
        client, _, make_conn = auth_client
        response = _get(
            client, make_conn,
            f"/profile?from={self.RANGE_FROM}&to={self.RANGE_TO}"
        )
        html = response.data.decode()
        for desc in self.OUT_OF_RANGE:
            assert desc not in html, (
                f"Transaction '{desc}' must NOT appear outside the filter range"
            )

    def test_filtered_top_category_reflects_range(self, auth_client):
        client, _, make_conn = auth_client
        response = _get(
            client, make_conn,
            f"/profile?from={self.RANGE_FROM}&to={self.RANGE_TO}"
        )
        html = response.data.decode()
        assert self.EXPECTED_TOP in html, (
            f"Top category should be {self.EXPECTED_TOP} for this range"
        )

    def test_filtered_unmatched_category_excluded_from_breakdown(self, auth_client):
        """Other (Jun 15) is outside the range — must not appear in breakdown."""
        client, _, make_conn = auth_client
        response = _get(
            client, make_conn,
            f"/profile?from={self.RANGE_FROM}&to={self.RANGE_TO}"
        )
        html = response.data.decode()
        # "Other" category only has one expense on 2026-06-15 (outside range)
        # We check the breakdown section does not list it as a standalone category
        # The breakdown renders category names inside .breakdown-name spans
        assert "Miscellaneous" not in html, (
            "The 'Other' expense on Jun 15 must be excluded from the filtered breakdown"
        )


# ---------------------------------------------------------------------------
# Pre-population of inputs after filter submission
# ---------------------------------------------------------------------------

class TestFilterPrePopulation:
    def test_from_input_prepopulated_after_filter(self, auth_client):
        client, _, make_conn = auth_client
        response = _get(client, make_conn, "/profile?from=2026-06-01&to=2026-06-10")
        html = response.data.decode()
        assert 'value="2026-06-01"' in html, (
            "From input must be pre-populated with the submitted from_date"
        )

    def test_to_input_prepopulated_after_filter(self, auth_client):
        client, _, make_conn = auth_client
        response = _get(client, make_conn, "/profile?from=2026-06-01&to=2026-06-10")
        html = response.data.decode()
        assert 'value="2026-06-10"' in html, (
            "To input must be pre-populated with the submitted to_date"
        )

    def test_only_from_prepopulated_when_only_from_given(self, auth_client):
        client, _, make_conn = auth_client
        response = _get(client, make_conn, "/profile?from=2026-06-08")
        html = response.data.decode()
        assert 'value="2026-06-08"' in html, (
            "From input must be pre-populated when only from is provided"
        )

    def test_only_to_prepopulated_when_only_to_given(self, auth_client):
        client, _, make_conn = auth_client
        response = _get(client, make_conn, "/profile?to=2026-06-05")
        html = response.data.decode()
        assert 'value="2026-06-05"' in html, (
            "To input must be pre-populated when only to is provided"
        )


# ---------------------------------------------------------------------------
# One-sided filters
# ---------------------------------------------------------------------------

class TestOneSidedFilter:
    """
    from-only: ?from=2026-06-08
    Matching: 08-Entertainment, 10-Shopping, 12-Food, 15-Other  =>  4 expenses
    Total: 350 + 2500 + 320 + 200 = 3370  =>  ₹3,370.00

    to-only: ?to=2026-06-05
    Matching: 01-Food, 02-Transport, 03-Bills, 05-Health  =>  4 expenses
    Total: 450 + 150 + 1200 + 800 = 2600  =>  ₹2,600.00
    """

    def test_from_only_excludes_earlier_expenses(self, auth_client):
        client, _, make_conn = auth_client
        response = _get(client, make_conn, "/profile?from=2026-06-08")
        html = response.data.decode()
        # Expenses before Jun 08 must be absent
        assert "Grocery run" not in html, "Grocery run (Jun 01) must be excluded"
        assert "Metro pass" not in html, "Metro pass (Jun 02) must be excluded"
        assert "Electricity bill" not in html, "Electricity bill (Jun 03) must be excluded"
        assert "Doctor visit" not in html, "Doctor visit (Jun 05) must be excluded"

    def test_from_only_includes_boundary_and_later(self, auth_client):
        client, _, make_conn = auth_client
        response = _get(client, make_conn, "/profile?from=2026-06-08")
        html = response.data.decode()
        assert "Movie tickets" in html, "Movie tickets (Jun 08, boundary) must be included"
        assert "New shoes" in html, "New shoes (Jun 10) must be included"
        assert "Restaurant dinner" in html, "Restaurant dinner (Jun 12) must be included"
        assert "Miscellaneous" in html, "Miscellaneous (Jun 15) must be included"

    def test_from_only_total_is_correct(self, auth_client):
        client, _, make_conn = auth_client
        response = _get(client, make_conn, "/profile?from=2026-06-08")
        html = response.data.decode()
        assert "₹3,370.00" in html, "from-only filter total must be ₹3,370.00"

    def test_to_only_excludes_later_expenses(self, auth_client):
        client, _, make_conn = auth_client
        response = _get(client, make_conn, "/profile?to=2026-06-05")
        html = response.data.decode()
        assert "Movie tickets" not in html, "Movie tickets (Jun 08) must be excluded"
        assert "New shoes" not in html, "New shoes (Jun 10) must be excluded"
        assert "Restaurant dinner" not in html, "Restaurant dinner (Jun 12) must be excluded"
        assert "Miscellaneous" not in html, "Miscellaneous (Jun 15) must be excluded"

    def test_to_only_includes_boundary_and_earlier(self, auth_client):
        client, _, make_conn = auth_client
        response = _get(client, make_conn, "/profile?to=2026-06-05")
        html = response.data.decode()
        assert "Grocery run" in html, "Grocery run (Jun 01) must be included"
        assert "Metro pass" in html, "Metro pass (Jun 02) must be included"
        assert "Electricity bill" in html, "Electricity bill (Jun 03) must be included"
        assert "Doctor visit" in html, "Doctor visit (Jun 05, boundary) must be included"

    def test_to_only_total_is_correct(self, auth_client):
        client, _, make_conn = auth_client
        response = _get(client, make_conn, "/profile?to=2026-06-05")
        html = response.data.decode()
        assert "₹2,600.00" in html, "to-only filter total must be ₹2,600.00"


# ---------------------------------------------------------------------------
# Malformed date params — must not crash, fall back to unfiltered
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("url_suffix", [
    "?from=not-a-date",
    "?to=99-99-99",
    "?from=2026-13-01",          # month 13 is invalid
    "?from=2026-06-32",          # day 32 is invalid
    "?from=abcdef&to=ghijkl",
    "?from=2026/06/01&to=2026/06/10",  # wrong separator
    "?from=01-06-2026",          # DD-MM-YYYY instead of YYYY-MM-DD
    "?from=&to=",                # empty strings (not really malformed, but edge)
])
def test_malformed_date_does_not_crash(auth_client, url_suffix):
    client, _, make_conn = auth_client
    response = _get(client, make_conn, f"/profile{url_suffix}")
    assert response.status_code == 200, (
        f"Malformed date param '{url_suffix}' must not crash — expected 200, "
        f"got {response.status_code}"
    )


@pytest.mark.parametrize("url_suffix", [
    "?from=not-a-date",
    "?to=99-99-99",
    "?from=2026-13-01",
    "?from=abcdef&to=ghijkl",
    "?from=2026/06/01&to=2026/06/10",
    "?from=01-06-2026",
])
def test_malformed_date_falls_back_to_unfiltered(auth_client, url_suffix):
    """When dates are malformed, the response must show all-time totals."""
    client, _, make_conn = auth_client
    response = _get(client, make_conn, f"/profile{url_suffix}")
    html = response.data.decode()
    assert ALL_TIME_TOTAL in html, (
        f"Malformed date '{url_suffix}' must fall back to all-time total {ALL_TIME_TOTAL}"
    )


# ---------------------------------------------------------------------------
# Backwards date range (from > to) — fall back to unfiltered
# ---------------------------------------------------------------------------

class TestBackwardsDateRange:
    def test_backwards_range_returns_200(self, auth_client):
        client, _, make_conn = auth_client
        response = _get(client, make_conn, "/profile?from=2026-06-15&to=2026-06-01")
        assert response.status_code == 200

    def test_backwards_range_falls_back_to_all_time_total(self, auth_client):
        client, _, make_conn = auth_client
        response = _get(client, make_conn, "/profile?from=2026-06-15&to=2026-06-01")
        html = response.data.decode()
        assert ALL_TIME_TOTAL in html, (
            "Backwards range must fall back to all-time total"
        )

    def test_backwards_range_shows_all_transactions(self, auth_client):
        client, _, make_conn = auth_client
        response = _get(client, make_conn, "/profile?from=2026-06-15&to=2026-06-01")
        html = response.data.decode()
        for _, _, _, _, desc in _SEED_EXPENSES:
            assert desc in html, (
                f"Backwards range fallback must show all transactions; missing: {desc}"
            )

    def test_backwards_range_inputs_are_not_prepopulated(self, auth_client):
        """Because the range is invalid, from_date and to_date are reset to None."""
        client, _, make_conn = auth_client
        response = _get(client, make_conn, "/profile?from=2026-06-15&to=2026-06-01")
        html = response.data.decode()
        # Since both are cleared, neither value should be set to these dates
        assert 'value="2026-06-15"' not in html, (
            "Invalid backwards from_date must not be pre-populated"
        )
        assert 'value="2026-06-01"' not in html, (
            "Invalid backwards to_date must not be pre-populated"
        )

    def test_equal_dates_are_valid_boundary(self, auth_client):
        """from == to is a valid single-day filter, not a backwards range."""
        client, _, make_conn = auth_client
        response = _get(client, make_conn, "/profile?from=2026-06-10&to=2026-06-10")
        assert response.status_code == 200
        html = response.data.decode()
        # Only the Jun 10 expense (New shoes, 2500) should appear
        assert "New shoes" in html, "Single-day filter must include the expense on that day"
        assert "₹2,500.00" in html, "Single-day filter total must be ₹2,500.00"
        assert "Grocery run" not in html, "Grocery run must be excluded from single-day filter"


# ---------------------------------------------------------------------------
# Clear link resets to full view
# ---------------------------------------------------------------------------

class TestClearLink:
    def test_clear_returns_200(self, auth_client):
        client, _, make_conn = auth_client
        response = _get(client, make_conn, "/profile")
        assert response.status_code == 200

    def test_clear_link_shows_all_time_data(self, auth_client):
        """Navigating to /profile without params gives the full unfiltered view."""
        client, _, make_conn = auth_client
        response = _get(client, make_conn, "/profile")
        html = response.data.decode()
        assert ALL_TIME_TOTAL in html, (
            "Clear (no params) must show all-time total"
        )

    def test_clear_link_contains_all_transactions(self, auth_client):
        client, _, make_conn = auth_client
        response = _get(client, make_conn, "/profile")
        html = response.data.decode()
        for _, _, _, _, desc in _SEED_EXPENSES:
            assert desc in html, f"Clear view must contain all transactions; missing: {desc}"

    def test_clear_link_inputs_empty(self, auth_client):
        """After clearing, both filter inputs should carry no date values."""
        client, _, make_conn = auth_client
        response = _get(client, make_conn, "/profile")
        html = response.data.decode()
        # None of the seed dates should appear as input values
        seed_dates = {dt for (_, _, _, dt, _) in _SEED_EXPENSES}
        for dt in seed_dates:
            assert f'value="{dt}"' not in html, (
                f"Filter input must not be pre-populated with {dt} on the clear view"
            )


# ---------------------------------------------------------------------------
# Category breakdown updates with filter
# ---------------------------------------------------------------------------

class TestCategoryBreakdown:
    def test_breakdown_only_shows_in_range_categories(self, auth_client):
        """
        Filter: 2026-06-01 to 2026-06-03
        Only Food (450), Transport (150), Bills (1200) exist in range.
        Health, Entertainment, Shopping, Other must not appear.
        """
        client, _, make_conn = auth_client
        response = _get(client, make_conn, "/profile?from=2026-06-01&to=2026-06-03")
        html = response.data.decode()
        assert "Food" in html, "Food must appear in the breakdown for this range"
        assert "Transport" in html, "Transport must appear in the breakdown for this range"
        assert "Bills" in html, "Bills must appear in the breakdown for this range"
        # Categories outside the range must not appear in the breakdown
        assert "Entertainment" not in html, (
            "Entertainment has no expenses in this range — must be excluded"
        )
        assert "Miscellaneous" not in html, (
            "Other/Miscellaneous is outside this range — must be excluded"
        )

    def test_breakdown_percentages_sum_to_100_filtered(self, auth_client):
        """
        We cannot inspect the rendered percentage numbers directly from HTML without
        parsing, but we verify that data-pct attributes are present, indicating the
        breakdown section rendered (relies on profile.html using data-pct).
        """
        client, _, make_conn = auth_client
        response = _get(client, make_conn, "/profile?from=2026-06-01&to=2026-06-10")
        html = response.data.decode()
        assert "data-pct" in html, (
            "Category breakdown bars (data-pct) must be present after filtering"
        )

    def test_breakdown_empty_when_no_expenses_in_range(self, auth_client):
        """A date range with no expenses should result in an empty breakdown."""
        client, _, make_conn = auth_client
        response = _get(
            client, make_conn, "/profile?from=2025-01-01&to=2025-01-31"
        )
        assert response.status_code == 200
        html = response.data.decode()
        # No data-pct bars should exist because there are no matching expenses
        assert "data-pct" not in html, (
            "No data-pct bars should render when the filtered range has no expenses"
        )

    def test_breakdown_total_correct_for_narrow_range(self, auth_client):
        """
        Single category range: ?from=2026-06-10&to=2026-06-10
        Only Shopping (2500) => 100%
        """
        client, _, make_conn = auth_client
        response = _get(client, make_conn, "/profile?from=2026-06-10&to=2026-06-10")
        html = response.data.decode()
        assert "Shopping" in html, "Shopping must appear in the breakdown"
        # 100% is the only bar value for a single-category filter
        assert "data-pct" in html, "Breakdown bar must render for single-category filter"


# ---------------------------------------------------------------------------
# Stats update with filter
# ---------------------------------------------------------------------------

class TestStatsUpdate:
    def test_transaction_count_reflects_filter(self, auth_client):
        """
        Range: 2026-06-01 to 2026-06-05 => 4 transactions.
        The stat card must NOT show 8.
        """
        client, _, make_conn = auth_client
        response = _get(client, make_conn, "/profile?from=2026-06-01&to=2026-06-05")
        html = response.data.decode()
        # total_spent for this range: 450+150+1200+800 = 2600
        assert "₹2,600.00" in html, "Stats total must reflect the filtered range"

    def test_top_category_reflects_filter(self, auth_client):
        """
        Range: 2026-06-01 to 2026-06-03
        Bills (1200) is the top category in this range, not Shopping.
        """
        client, _, make_conn = auth_client
        response = _get(client, make_conn, "/profile?from=2026-06-01&to=2026-06-03")
        html = response.data.decode()
        assert "Bills" in html, (
            "Top category stat must be Bills for the 2026-06-01 to 2026-06-03 range"
        )

    def test_stats_zero_for_range_with_no_expenses(self, auth_client):
        """A range that spans no expenses must show ₹0.00."""
        client, _, make_conn = auth_client
        response = _get(
            client, make_conn, "/profile?from=2025-01-01&to=2025-01-31"
        )
        assert response.status_code == 200
        html = response.data.decode()
        assert "₹0.00" in html, (
            "Stats total must be ₹0.00 when no expenses fall in the range"
        )
