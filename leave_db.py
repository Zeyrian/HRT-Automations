from database import db, now_ts

db.execute("""CREATE TABLE IF NOT EXISTS leaves (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    days INTEGER NOT NULL,
    reason TEXT NOT NULL,
    status TEXT NOT NULL,
    requested_ts INTEGER NOT NULL,
    start_ts INTEGER,
    end_ts INTEGER,
    reviewer_id INTEGER
)""")
db.commit()

COLUMNS = (
    "id", "user_id", "days", "reason", "status",
    "requested_ts", "start_ts", "end_ts", "reviewer_id",
)
SELECT = "SELECT " + ", ".join(COLUMNS) + " FROM leaves"


def _leave(row):
    return dict(zip(COLUMNS, row)) if row else None


def create_request(uid, days, reason):
    cur = db.execute(
        "INSERT INTO leaves (user_id, days, reason, status, requested_ts) "
        "VALUES (?, ?, ?, 'pending', ?)",
        (uid, days, reason, now_ts()),
    )
    db.commit()
    return cur.lastrowid


def delete_leave(leave_id):
    db.execute("DELETE FROM leaves WHERE id=?", (leave_id,))
    db.commit()


def get_leave(leave_id):
    return _leave(db.execute(f"{SELECT} WHERE id=?", (leave_id,)).fetchone())


def get_pending(uid):
    return _leave(
        db.execute(
            f"{SELECT} WHERE user_id=? AND status='pending' ORDER BY id DESC LIMIT 1", (uid,)
        ).fetchone()
    )


def get_active(uid):
    return _leave(
        db.execute(
            f"{SELECT} WHERE user_id=? AND status='approved' AND end_ts > ? "
            "ORDER BY end_ts DESC LIMIT 1",
            (uid, now_ts()),
        ).fetchone()
    )


def get_all_active():
    rows = db.execute(
        f"{SELECT} WHERE status='approved' AND end_ts > ? ORDER BY end_ts", (now_ts(),)
    ).fetchall()
    return [_leave(r) for r in rows]


def get_recent(uid, limit=5):
    rows = db.execute(
        f"{SELECT} WHERE user_id=? ORDER BY id DESC LIMIT ?", (uid, limit)
    ).fetchall()
    return [_leave(r) for r in rows]


def approve(leave_id, reviewer_id):
    """Approves a pending request; the leave starts now. Returns the leave, or None if it wasn't pending."""
    leave = get_leave(leave_id)
    if not leave or leave["status"] != "pending":
        return None
    start = now_ts()
    db.execute(
        "UPDATE leaves SET status='approved', start_ts=?, end_ts=?, reviewer_id=? WHERE id=?",
        (start, start + leave["days"] * 86400, reviewer_id, leave_id),
    )
    db.commit()
    return get_leave(leave_id)


def deny(leave_id, reviewer_id):
    """Denies a pending request. Returns the leave, or None if it wasn't pending."""
    leave = get_leave(leave_id)
    if not leave or leave["status"] != "pending":
        return None
    db.execute(
        "UPDATE leaves SET status='denied', reviewer_id=? WHERE id=?", (reviewer_id, leave_id)
    )
    db.commit()
    return get_leave(leave_id)


def grant(uid, days, reason, admin_id):
    """Creates an already-approved leave starting now. Returns its ID."""
    now = now_ts()
    cur = db.execute(
        "INSERT INTO leaves (user_id, days, reason, status, requested_ts, start_ts, end_ts, reviewer_id) "
        "VALUES (?, ?, ?, 'approved', ?, ?, ?, ?)",
        (uid, days, reason, now, now, now + days * 86400, admin_id),
    )
    db.commit()
    return cur.lastrowid


def end_early(uid):
    """Ends the member's active leave now. Returns the leave ID, or None if none is active."""
    leave = get_active(uid)
    if not leave:
        return None
    db.execute("UPDATE leaves SET status='ended', end_ts=? WHERE id=?", (now_ts(), leave["id"]))
    db.commit()
    return leave["id"]