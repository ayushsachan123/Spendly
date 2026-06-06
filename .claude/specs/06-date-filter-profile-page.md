# Spec: Date Filter For Profile Page

## Overview
Step 6 adds a date range filter to the profile page so users can scope all
displayed data — summary stats, recent transactions, and category breakdown —
to a chosen time window. Currently every section shows lifetime totals with no
way to narrow by period. This step wires `from_date` and `to_date` query
parameters into the existing `GET /profile` route and propagates them through
the four query helpers in `database/queries.py`, making the profile page
meaningfully interactive before the expense CRUD steps begin.

## Depends on
- Step 1: Database setup (`expenses` table with `date` column must exist)
- Step 2: Registration (users must be creatable)
- Step 3: Login / Logout (`session["user_id"]` is set on login)
- Step 4: Profile page static UI (`profile.html` layout already exists)
- Step 5: Backend connection (all four query helpers exist in `database/queries.py`)

## Routes
No new routes. The existing `GET /profile` route is modified to accept optional
query parameters:
- `from` — ISO date string (`YYYY-MM-DD`); start of range (inclusive)
- `to` — ISO date string (`YYYY-MM-DD`); end of range (inclusive)

Example: `GET /profile?from=2026-06-01&to=2026-06-30`

## Database changes
No database changes. The `expenses` table already has a `date TEXT` column
that stores ISO dates (`YYYY-MM-DD`), which SQLite compares correctly as
strings.

## Templates
- **Modify**: `templates/profile.html`
  - Add a date filter form above the stats row with two `<input type="date">`
    fields labelled "From" and "To" and an "Apply" submit button.
  - The form uses `method="GET"` and `action="/profile"` so filters live in
    the URL and are bookmarkable / shareable.
  - Pre-populate both inputs with the currently active `from_date` / `to_date`
    values passed from the route (empty if no filter is active).
  - Add a "Clear" link (`/profile` with no query params) next to the Apply
    button so users can reset to the full lifetime view.
  - All existing sections (user card, stats, transactions, breakdown) must
    already render correctly — no structural changes needed, only the filter
    form is new markup.

## Files to change
- `app.py`
  - In the `profile()` view, read `request.args.get("from")` and
    `request.args.get("to")`.
  - Validate that both values, if provided, are valid ISO dates
    (`YYYY-MM-DD`). If either is malformed, ignore both and fall back to the
    unfiltered view (do not raise an error).
  - Pass `from_date` and `to_date` to all four query helpers.
  - Pass `from_date` and `to_date` back to the template so the form inputs
    can be pre-populated.

- `database/queries.py`
  - Update all four helpers to accept optional `from_date=None` and
    `to_date=None` keyword arguments.
  - When both are provided, append `AND date BETWEEN ? AND ?` to each
    relevant SQL query (or equivalent `AND date >= ? AND date <= ?`).
  - When only one bound is provided, apply only that bound
    (`AND date >= from_date` or `AND date <= to_date`).
  - When neither is provided, behaviour is unchanged (no date clause added).
  - `get_user_by_id` does not touch the `expenses` table — its signature
    remains unchanged; no date filter applies.

## Files to create
None.

## New dependencies
No new dependencies.

## Rules for implementation
- No SQLAlchemy or ORMs — raw `sqlite3` only via `get_db()`
- Parameterised queries only — never string-format values or dates into SQL
- Use CSS variables — never hardcode hex values
- All templates extend `base.html`
- No inline styles
- Date validation in `app.py` must use `datetime.strptime(value, "%Y-%m-%d")`
  inside a `try/except ValueError` — do not use regex or manual string checks
- The filter form must use `method="GET"` (not POST) so filtered URLs are
  shareable
- If `from_date` is after `to_date`, treat the filter as invalid and fall back
  to the unfiltered view
- An empty filter (no params) must show identical output to the current
  unfiltered profile page — no regressions

## Definition of done
- [ ] Visiting `/profile` (no query params) still shows all-time data — no
      regression from Step 5 behaviour
- [ ] A date filter form with "From", "To" inputs and an "Apply" button is
      visible on the profile page
- [ ] Submitting the form with `from=2026-06-01` and `to=2026-06-10` shows
      only transactions whose date falls within that range
- [ ] Summary stats (total spent, transaction count, top category) update to
      reflect the filtered date range
- [ ] Category breakdown updates to reflect the filtered date range
- [ ] The "From" and "To" inputs are pre-populated with the active filter
      values after the form is submitted
- [ ] A "Clear" link resets the page to the full unfiltered view
- [ ] Supplying a malformed date (e.g. `?from=not-a-date`) does not crash the
      app — it silently falls back to the unfiltered view
- [ ] Supplying only one date bound (e.g. `?from=2026-06-01` with no `to`)
      applies a one-sided filter correctly
- [ ] The filter UI uses only CSS variables — no hardcoded hex values
