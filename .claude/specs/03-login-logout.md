# Spec: Login and Logout

## Overview
Implement the login and logout flows so users can authenticate with their email and password and maintain a session across requests. The `/login` route currently only handles `GET` — this step adds the `POST` handler that verifies credentials, starts a Flask session, and redirects to the dashboard (or back to the form on failure). The `/logout` route currently returns a placeholder string — this step clears the session and redirects to the landing page. After this step, the app has a working auth loop: register → login → logout.

## Depends on
- Step 1 (Database Setup) — `get_db()` must be importable and `users` table must exist
- Step 2 (Registration) — at least one user must be creatable to test login

## Routes
- `GET /login` — render the login form — public
- `POST /login` — validate credentials, start session, redirect to `/` on success — public
- `GET /logout` — clear session, redirect to `/` — logged-in (no hard guard needed yet; safe to call unauthenticated)

## Database changes
No database changes. The existing `users` table with `email` and `password_hash` columns is sufficient.

## Templates
- **Modify:** `templates/login.html`
  - Add `method="POST"` and `action="{{ url_for('login') }}"` to the `<form>` tag if not already present
  - Add a sticky `value="{{ email or '' }}"` attribute to the email input so it repopulates on error
  - Render an error message block: `{% if error %}<p class="form-error">{{ error }}</p>{% endif %}`
- **Modify:** `templates/base.html`
  - In the navbar, conditionally show logout link when `session.get('user_id')` is set:
    - Logged-in: show user's name and a "Logout" link pointing to `url_for('logout')`
    - Logged-out: show "Login" and "Register" links

## Files to change
- `app.py`
  - Add `session` and `check_password_hash` imports
  - Convert `GET /login` stub to a dual GET/POST route (`methods=["GET", "POST"]`)
  - Implement POST handler: look up user by email, verify password, set `session['user_id']` and `session['user_name']`, redirect to `/`
  - Implement `GET /logout`: call `session.clear()`, redirect to `url_for('landing')`
- `templates/login.html` — form attributes + sticky email + error block
- `templates/base.html` — conditional navbar links based on session state

## Files to create
None.

## New dependencies
No new dependencies. `flask.session` and `werkzeug.security.check_password_hash` are already available.

## Rules for implementation
- No SQLAlchemy or ORMs — use raw `sqlite3` via `get_db()`
- Parameterised queries only — never use string formatting in SQL
- Passwords verified with `werkzeug.security.check_password_hash` — never compare plain text
- Use CSS variables — never hardcode hex values
- All templates extend `base.html`
- Store only `user_id` (int) and `user_name` (str) in the session — never store the password or hash
- On bad credentials: show a generic error `"Invalid email or password."` — do not reveal which field was wrong
- On success: `redirect(url_for("landing"))` — redirect to landing page (dashboard is a later step)
- Validation order: check email present → look up user → verify password — fail with the generic message at any step
- Always close the DB connection in a `finally` block
- `app.secret_key` is already set in `app.py` — do not change it

## Definition of done
- [ ] Submitting valid credentials sets `session['user_id']` and redirects to `/`
- [ ] Submitting an unknown email shows "Invalid email or password."
- [ ] Submitting the correct email with a wrong password shows "Invalid email or password."
- [ ] Submitting with an empty email shows a validation error
- [ ] After a failed login the email field retains its submitted value
- [ ] Visiting `/logout` clears the session and redirects to `/`
- [ ] After logout, `session.get('user_id')` is `None`
- [ ] Navbar shows Login/Register links when logged out
- [ ] Navbar shows the user's name and a Logout link when logged in
- [ ] App starts without errors after changes to `app.py`
