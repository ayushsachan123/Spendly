# Spec: Registration

## Overview
Wire up the existing `/register` form so that submitting it creates a real user account. Currently the route only handles `GET` and renders the template — this step adds the `POST` handler that validates input, checks for duplicate emails, hashes the password, inserts the user into the database, and redirects to the login page on success. This is the first step where the database is written to by user action.

## Depends on
- Step 1 (Database Setup) — `users` table must exist and `get_db()` must be importable from `database/db.py`

## Routes
- `GET /register` — render the registration form — public
- `POST /register` — process form submission, create account, redirect to login — public

The existing `GET /register` stub is converted to a dual-method route (`methods=["GET", "POST"]`).

## Database changes
No new tables or columns. The existing `users` table is sufficient.

## Templates
- **Modify:** `templates/register.html`
  - Add sticky form values: `name` and `email` inputs should re-populate on validation failure using `value="{{ name or '' }}"` and `value="{{ email or '' }}"`
  - The `{% if error %}` block already exists — no change needed there

## Files to change
- `app.py` — convert `/register` to a dual GET/POST route; add imports (`request`, `redirect`, `url_for`); add `app.secret_key`
- `templates/register.html` — add sticky `value` attributes to `name` and `email` inputs

## Files to create
None.

## New dependencies
No new dependencies.

## Rules for implementation
- No SQLAlchemy or ORMs — use raw `sqlite3` via `get_db()`
- Parameterised queries only — never use string formatting in SQL
- Passwords hashed with `werkzeug.security.generate_password_hash`
- Use CSS variables — never hardcode hex values
- All templates extend `base.html`
- Set `app.secret_key` to a hard-coded dev string (e.g. `"spendly-dev-secret"`) directly in `app.py` — no env file needed at this stage
- On duplicate email: catch `sqlite3.IntegrityError` and re-render the form with `error="An account with that email already exists."`
- On success: `redirect(url_for("login"))` — no flash message needed yet (flash/session is wired in a later step)
- Validation order: name → email → password length (≥ 8 chars) — fail fast, show first error only
- Always close the DB connection in a `finally` block

## Definition of done
- [ ] Submitting the form with valid data creates a row in the `users` table with a hashed password
- [ ] Resubmitting the same email shows the error "An account with that email already exists."
- [ ] Submitting with an empty name shows a validation error
- [ ] Submitting with a password shorter than 8 characters shows a validation error
- [ ] After a validation error the name and email fields retain their submitted values
- [ ] Successful registration redirects to `/login`
- [ ] The plain-text password is never stored — only the werkzeug hash is in the DB
- [ ] App starts without errors after changes to `app.py`
