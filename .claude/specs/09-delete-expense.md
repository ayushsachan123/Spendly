# Spec: Delete Expense

## Overview
Step 9 implements the Delete Expense feature, allowing logged-in users to remove
any of their own expenses directly from the Recent Transactions table on the
profile page. The `/expenses/<id>/delete` route is currently a GET placeholder
returning a string — this step replaces it with a POST handler that validates
ownership, deletes the row from the database, and redirects back to the profile
page. A JavaScript `confirm()` dialog prevents accidental deletions. No
confirmation page is needed.

## Depends on
- Step 1: Database setup (`expenses` table must exist)
- Step 2: Registration (users must exist to own expenses)
- Step 3: Login / Logout (`session["user_id"]` must be available)
- Step 4–6: Profile page (`/profile` must exist as the post-delete redirect target
  and as the page that hosts the delete buttons)
- Step 7: Add Expense (expenses must be creatable before they can be deleted)

## Routes
- `POST /expenses/<int:id>/delete` — delete the expense with the given id if it
  belongs to the current user, then redirect to `/profile` — logged-in only

## Database changes
No new tables or columns. Uses the existing `expenses` table. The query is a
parameterised `DELETE FROM expenses WHERE id = ? AND user_id = ?` — the
`user_id` filter enforces ownership at the database level.

## Templates
- **Modify:** `templates/profile.html`
  - Add an `Actions` column header to the `<thead>` of the `.txn-table`
  - For each row in `{% for txn in transactions %}`, add a `<td>` containing a
    `<form>` with `method="POST"` and `action="/expenses/{{ txn.id }}/delete"`
  - The form contains a single submit button styled with the `.btn-danger` class
    and labelled "Delete"
  - The submit button has an `onclick="return confirm('Delete this expense?')"` to
    prevent accidental deletions

## Files to change
- `app.py`
  - Change `@app.route("/expenses/<int:id>/delete")` to accept `methods=["POST"]`
  - Replace the stub body with:
    1. Auth guard — redirect unauthenticated users to `/login`
    2. Ownership check — `DELETE FROM expenses WHERE id = ? AND user_id = ?`
       using `session["user_id"]`; if no row was deleted the expense either does
       not exist or belongs to another user — either way redirect to `/profile`
       silently (no error page needed)
    3. Commit and redirect to `/profile`
- `templates/profile.html`
  - Add `<th>Actions</th>` as the last column in `<thead>`
  - Add a delete form `<td>` as the last cell in every `<tr>` inside `<tbody>`
- `static/css/style.css`
  - Add `.btn-danger` style using `var(--danger)` as background and white text,
    matching the size and border-radius of `.btn-primary`

## Files to create
No new files.

## New dependencies
No new dependencies.

## Rules for implementation
- No SQLAlchemy or ORMs — raw `sqlite3` only via `get_db()`
- Parameterised queries only — never string-format values into SQL
- Passwords hashed with werkzeug (not applicable here, but pattern must be
  followed elsewhere)
- Use CSS variables — never hardcode hex values
- All templates extend `base.html`
- No inline styles — button appearance must come from the `.btn-danger` CSS class
- Route must be POST only — reject GET requests implicitly (Flask will return 405)
- Ownership enforced at the SQL level with `WHERE id = ? AND user_id = ?` —
  never fetch first and compare in Python
- After delete, always redirect to `/profile` — never re-render a template
- Do not expose whether the expense existed or belonged to another user; silently
  redirect in both error cases

## Definition of done
- [ ] Visiting `POST /expenses/<id>/delete` while logged out redirects to `/login`
- [ ] A `GET` request to `/expenses/<id>/delete` returns 405 Method Not Allowed
- [ ] Each row in the Recent Transactions table shows a red "Delete" button
- [ ] Clicking "Delete" triggers a browser confirmation dialog before submitting
- [ ] Confirming the dialog submits the POST form and deletes the expense
- [ ] After deletion the user is redirected to `/profile` and the deleted expense
      no longer appears in the transactions list
- [ ] Summary stats update to reflect the removal (total spent decreases, count
      decreases)
- [ ] Attempting to delete an expense that belongs to another user (by crafting a
      POST request manually) does not delete it and redirects to `/profile`
- [ ] Attempting to delete a non-existent expense ID redirects to `/profile`
      without an error page
- [ ] The Delete button uses `var(--danger)` — no hardcoded hex colours
