# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Activate virtual environment (Windows)
venv\Scripts\activate

# Run development server (port 5001, debug mode)
python app.py

# Install dependencies
pip install -r requirements.txt

# Run tests
pytest
```

## Architecture

**Spendly** is a Flask expense tracker with server-rendered Jinja2 templates, a SQLite backend, and vanilla CSS/JS frontend. No build step — all assets are served directly from `static/`.

### Request flow

`app.py` defines all routes → Flask renders templates from `templates/` → `templates/base.html` is the master layout that all pages extend → `static/css/style.css` and `static/js/main.js` are loaded globally.

### Route groups

- **Implemented:** `GET /`, `/register`, `/login`, `/terms`, `/privacy`
- **Placeholders (student steps):** `/logout` (Step 3), `/profile` (Step 4), `/expenses/add` (Step 7), `/expenses/<id>/edit` (Step 8), `/expenses/<id>/delete` (Step 9)

### Database layer (`database/db.py`)

Currently a stub. Intended to export three functions:
- `get_db()` — SQLite connection with `row_factory` and foreign keys enabled
- `init_db()` — creates all tables via `CREATE TABLE IF NOT EXISTS`
- `seed_db()` — inserts sample development data

The database module is not yet imported by `app.py`; wiring it in is part of Step 1.

### CSS design system

`static/css/style.css` uses CSS custom properties defined on `:root`:
- Colors: `--accent` (forest green `#1a472a`), `--accent-2` (warm orange `#c17f24`), `--danger`, `--ink`, `--paper`
- Typography: DM Sans (body) + DM Serif Display (headings), loaded from Google Fonts in `base.html`
- Auth pages use a 440px centered container; content max-width is 1200px

### Template inheritance

All pages `{% extends "base.html" %}` and fill `{% block content %}`. The base template includes the sticky navbar and footer.
