# Spec: Add Expense

## Overview
Step 7 implements the Add Expense feature, allowing logged-in users to record a
new expense by submitting a form with an amount, category, date, and optional
description. The `/expenses/add` route currently returns a placeholder string —
this step replaces it with a fully functional GET/POST handler backed by a
parameterised `INSERT` query. After a successful submission the user is
redirected to the profile page where the new expense appears immediately in the
transaction list and updates the summary stats.

## Depends on
- Step 1: Database setup (`expenses` table must exist with `user_id`, `amount`,
  `category`, `date`, `description` columns)
- Step 2: Registration (users must be creatable)
- Step 3: Login / Logout (`session["user_id"]` is set on login; add-expense
  must be auth-gated)
- Step 4: Profile page (`/profile` must exist so the post-save redirect lands
  somewhere meaningful)

## Routes
- `GET /expenses/add` — render the add-expense form — logged-in only
- `POST /expenses/add` — validate and insert the expense, then redirect to
  `/profile` — logged-in only

## Database changes
No new tables or columns. The existing `expenses` table already has all
required columns:
- `user_id` — taken from `session["user_id"]`
- `amount` — REAL (stored as float)
- `category` — TEXT
- `date` — TEXT (`YYYY-MM-DD`)
- `description` — TEXT (optional, nullable)

## Templates
- **Create:** `templates/add_expense.html`
  - Extends `base.html`
  - Contains a form with `method="POST"` and `action="/expenses/add"`
  - Fields: Amount (number input, step="0.01", required), Category (select
    with fixed options), Date (date input, required, pre-filled with today),
    Description (textarea, optional)
  - Category options: Food, Transport, Bills, Health, Entertainment, Shopping,
    Other
  - Shows an inline error message when validation fails, re-populating
    previously entered values
  - A "Cancel" link navigates back to `/profile`
  - Styled to match the existing Spendly design system (CSS variables only)

## Files to change
- `app.py`
  - Replace the `add_expense()` stub with a full GET/POST handler
  - `GET`: redirect to `/login` if not authenticated; render `add_expense.html`
    with today's date pre-filled
  - `POST`: redirect to `/login` if not authenticated; read `amount`,
    `category`, `date`, `description` from `request.form`; validate all
    required fields; insert into `expenses`; redirect to `/profile` on success;
    re-render the form with an error message on failure

## Files to create
- `templates/add_expense.html` — the add-expense form template

## New dependencies
No new dependencies.

## Rules for implementation
- No SQLAlchemy or ORMs — raw `sqlite3` only via `get_db()`
- Parameterised queries only — never string-format values into SQL
- Passwords hashed with werkzeug (not applicable here, but pattern must be
  followed elsewhere)
- Use CSS variables — never hardcode hex values
- All templates extend `base.html`
- No inline styles
- Auth guard: both GET and POST must redirect unauthenticated users to `/login`
- Amount validation: must be a positive number greater than 0; reject
  non-numeric or zero/negative values
- Date validation: must be a valid `YYYY-MM-DD` string using
  `datetime.strptime`; reject malformed dates
- Category validation: must be one of the fixed allowed values; reject anything
  else
- Description is optional; store `None` / empty string as-is — do not treat
  blank descriptions as errors
- On POST failure, re-render the form with the previously submitted values
  pre-populated so the user does not have to retype everything
- After a successful INSERT, redirect to `/profile` using `redirect(url_for("profile"))`

## Definition of done
- [ ] Visiting `/expenses/add` while logged out redirects to `/login`
- [ ] Visiting `/expenses/add` while logged in renders a form with Amount,
      Category, Date, and Description fields
- [ ] The Date field is pre-filled with today's date on first load
- [ ] Submitting the form with valid data inserts a row into `expenses` and
      redirects to `/profile`
- [ ] The new expense appears in the Recent Transactions list on the profile
      page immediately after submission
- [ ] Summary stats on the profile page update to reflect the new expense
- [ ] Submitting with a blank Amount shows an inline error and re-populates
      all other fields
- [ ] Submitting with a non-numeric Amount (e.g. "abc") shows an inline error
- [ ] Submitting with Amount = 0 or a negative number shows an inline error
- [ ] Submitting with a blank Date shows an inline error
- [ ] Submitting with an invalid Category (e.g. via form manipulation) shows
      an inline error
- [ ] Submitting with a blank Description succeeds (it is optional)
- [ ] The form UI uses only CSS variables — no hardcoded hex values
- [ ] A "Cancel" link on the form navigates back to `/profile`
