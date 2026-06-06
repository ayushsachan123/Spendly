from datetime import datetime
from database.db import get_db


def _date_clauses(from_date, to_date):
    clauses, params = [], []
    if from_date:
        clauses.append("date >= ?")
        params.append(from_date)
    if to_date:
        clauses.append("date <= ?")
        params.append(to_date)
    sql = (" AND " + " AND ".join(clauses)) if clauses else ""
    return sql, params


def get_user_by_id(user_id):
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT id, name, email, created_at FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
    finally:
        conn.close()

    if row is None:
        return None

    initials = "".join(word[0].upper() for word in row["name"].split() if word)
    try:
        member_since = datetime.strptime(row["created_at"][:10], "%Y-%m-%d").strftime("%B %Y")
    except (ValueError, TypeError):
        member_since = "Unknown"

    return {
        "name": row["name"],
        "email": row["email"],
        "initials": initials,
        "member_since": member_since,
    }


def get_summary_stats(user_id, from_date=None, to_date=None):
    date_sql, date_params = _date_clauses(from_date, to_date)
    conn = get_db()
    try:
        agg = conn.execute(
            f"SELECT COUNT(*), COALESCE(SUM(amount), 0) FROM expenses WHERE user_id = ?{date_sql}",
            [user_id] + date_params,
        ).fetchone()
        top = conn.execute(
            f"SELECT category FROM expenses WHERE user_id = ?{date_sql} GROUP BY category ORDER BY SUM(amount) DESC LIMIT 1",
            [user_id] + date_params,
        ).fetchone()
    finally:
        conn.close()

    count = agg[0]
    total = agg[1]
    top_category = top["category"] if top else "—"

    return {
        "total_spent": f"₹{total:,.2f}",
        "transaction_count": count,
        "top_category": top_category,
    }


def get_recent_transactions(user_id, limit=10, from_date=None, to_date=None):
    date_sql, date_params = _date_clauses(from_date, to_date)
    conn = get_db()
    try:
        rows = conn.execute(
            f"SELECT date, description, category, amount FROM expenses"
            f" WHERE user_id = ?{date_sql} ORDER BY date DESC LIMIT ?",
            [user_id] + date_params + [limit],
        ).fetchall()
    finally:
        conn.close()

    result = []
    for row in rows:
        try:
            formatted_date = datetime.strptime(row["date"], "%Y-%m-%d").strftime("%d %b %Y")
        except (ValueError, TypeError):
            formatted_date = row["date"]
        result.append({
            "date": formatted_date,
            "description": row["description"] or "",
            "category": row["category"],
            "amount": f"₹{row['amount']:,.2f}",
        })
    return result


def get_category_breakdown(user_id, from_date=None, to_date=None):
    date_sql, date_params = _date_clauses(from_date, to_date)
    conn = get_db()
    try:
        rows = conn.execute(
            f"SELECT category, SUM(amount) AS total FROM expenses"
            f" WHERE user_id = ?{date_sql} GROUP BY category ORDER BY total DESC",
            [user_id] + date_params,
        ).fetchall()
    finally:
        conn.close()

    if not rows:
        return []

    grand_total = sum(row["total"] for row in rows)
    if grand_total == 0:
        return []

    categories = []
    for row in rows:
        categories.append({
            "name": row["category"],
            "amount": f"₹{row['total']:,.2f}",
            "_raw": row["total"],
        })

    # Compute percentages with largest-remainder correction
    exact = [c["_raw"] / grand_total * 100 for c in categories]
    floored = [int(p) for p in exact]
    remainders = [(exact[i] - floored[i], i) for i in range(len(floored))]
    deficit = 100 - sum(floored)
    for _, i in sorted(remainders, reverse=True)[:deficit]:
        floored[i] += 1

    for i, cat in enumerate(categories):
        cat["percent"] = floored[i]
        del cat["_raw"]

    return categories
