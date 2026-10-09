import os
import sqlite3
import time

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "hrt.db")
BACKUP_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "backups")

db = sqlite3.connect(DB_PATH)
db.execute("""CREATE TABLE IF NOT EXISTS shifts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    start_ts INTEGER NOT NULL,
    end_ts INTEGER
)""")
db.execute("""CREATE TABLE IF NOT EXISTS breaks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    shift_id INTEGER NOT NULL,
    start_ts INTEGER NOT NULL,
    end_ts INTEGER
)""")
db.commit()


def now_ts():
    return int(time.time())


def get_open_shift(uid):
    return db.execute(
        "SELECT id, start_ts FROM shifts WHERE user_id=? AND end_ts IS NULL", (uid,)
    ).fetchone()


def get_open_break(shift_id):
    return db.execute(
        "SELECT id, start_ts FROM breaks WHERE shift_id=? AND end_ts IS NULL", (shift_id,)
    ).fetchone()


def break_total(shift_id, now):
    return db.execute(
        "SELECT COALESCE(SUM(COALESCE(end_ts, ?) - start_ts), 0) FROM breaks WHERE shift_id=?",
        (now, shift_id),
    ).fetchone()[0]


def total_time(uid, now):
    worked = db.execute(
        "SELECT COALESCE(SUM(COALESCE(end_ts, ?) - start_ts), 0) FROM shifts WHERE user_id=?",
        (now, uid),
    ).fetchone()[0]
    brk = db.execute(
        """SELECT COALESCE(SUM(COALESCE(b.end_ts, ?) - b.start_ts), 0)
           FROM breaks b JOIN shifts s ON s.id = b.shift_id WHERE s.user_id=?""",
        (now, uid),
    ).fetchone()[0]
    return worked - brk


def count_shifts(uid):
    return db.execute("SELECT COUNT(*) FROM shifts WHERE user_id=?", (uid,)).fetchone()[0]


def get_active_shifts():
    return db.execute(
        "SELECT id, user_id, start_ts FROM shifts WHERE end_ts IS NULL ORDER BY start_ts"
    ).fetchall()


def start_shift(uid):
    """Starts a shift. Returns the new shift ID, or None if already on shift."""
    if get_open_shift(uid):
        return None
    cur = db.execute("INSERT INTO shifts (user_id, start_ts) VALUES (?, ?)", (uid, now_ts()))
    db.commit()
    return cur.lastrowid


def toggle_break(uid):
    """Starts or ends a break. Returns (shift_id, 'started' | 'ended', break_seconds), or None if not on shift."""
    shift = get_open_shift(uid)
    if not shift:
        return None
    shift_id = shift[0]
    now = now_ts()
    open_break = get_open_break(shift_id)
    if open_break:
        db.execute("UPDATE breaks SET end_ts=? WHERE id=?", (now, open_break[0]))
        db.commit()
        return shift_id, "ended", now - open_break[1]
    db.execute("INSERT INTO breaks (shift_id, start_ts) VALUES (?, ?)", (shift_id, now))
    db.commit()
    return shift_id, "started", None


def end_shift(uid):
    """Ends the open shift. Returns (shift_id, on_duty_seconds, break_seconds), or None if not on shift."""
    shift = get_open_shift(uid)
    if not shift:
        return None
    shift_id, start = shift
    now = now_ts()
    open_break = get_open_break(shift_id)
    if open_break:
        db.execute("UPDATE breaks SET end_ts=? WHERE id=?", (now, open_break[0]))
    db.execute("UPDATE shifts SET end_ts=? WHERE id=?", (now, shift_id))
    db.commit()
    breaks = break_total(shift_id, now)
    return shift_id, now - start - breaks, breaks


def all_totals(now):
    """Returns {user_id: total on-duty seconds} for everyone with logged shifts."""
    totals = {}
    for uid, secs in db.execute(
        "SELECT user_id, SUM(COALESCE(end_ts, ?) - start_ts) FROM shifts GROUP BY user_id",
        (now,),
    ):
        totals[uid] = secs
    for uid, secs in db.execute(
        """SELECT s.user_id, SUM(COALESCE(b.end_ts, ?) - b.start_ts)
           FROM breaks b JOIN shifts s ON s.id = b.shift_id GROUP BY s.user_id""",
        (now,),
    ):
        totals[uid] = totals.get(uid, 0) - secs
    return totals

def get_recent_shifts(uid, limit=25):
    return db.execute(
        "SELECT id, start_ts, end_ts FROM shifts WHERE user_id=? ORDER BY id DESC LIMIT ?",
        (uid, limit),
    ).fetchall()


def shift_on_duty(shift_id, start, end, now):
    return (end or now) - start - break_total(shift_id, now)


def delete_shift(shift_id, uid):
    """Deletes a shift and its breaks. Returns the deleted shift's on-duty seconds, or None if not found."""
    row = db.execute(
        "SELECT start_ts, end_ts FROM shifts WHERE id=? AND user_id=?", (shift_id, uid)
    ).fetchone()
    if not row:
        return None
    start, end = row
    on_duty = shift_on_duty(shift_id, start, end, now_ts())
    db.execute("DELETE FROM breaks WHERE shift_id=?", (shift_id,))
    db.execute("DELETE FROM shifts WHERE id=?", (shift_id,))
    db.commit()
    return on_duty


def modify_shift(shift_id, uid, minutes):
    """Adds (or removes, if negative) minutes by moving the shift's start time.
    Returns (new_on_duty_seconds, None) on success, or (None, error_message)."""
    row = db.execute(
        "SELECT start_ts, end_ts FROM shifts WHERE id=? AND user_id=?", (shift_id, uid)
    ).fetchone()
    if not row:
        return None, "That shift no longer exists."
    start, end = row
    new_start = start - minutes * 60
    new_on_duty = shift_on_duty(shift_id, new_start, end, now_ts())
    if new_on_duty < 0:
        return None, "That would make the shift's time negative."
    db.execute("UPDATE shifts SET start_ts=? WHERE id=?", (new_start, shift_id))
    db.commit()
    return new_on_duty, None

def count_all_shifts():
    return db.execute("SELECT COUNT(*) FROM shifts").fetchone()[0]


def backup_database():
    """Copies hrt.db into backups/ with a timestamp. Returns the backup file path."""
    os.makedirs(BACKUP_DIR, exist_ok=True)
    path = os.path.join(BACKUP_DIR, f"hrt-{time.strftime('%Y%m%d-%H%M%S')}.db")
    dest = sqlite3.connect(path)
    try:
        db.backup(dest)
    finally:
        dest.close()
    return path


def wipe_all_shifts():
    """Deletes every shift and break. Returns the user IDs that had an open shift."""
    open_users = [
        row[0] for row in db.execute("SELECT user_id FROM shifts WHERE end_ts IS NULL")
    ]
    db.execute("DELETE FROM breaks")
    db.execute("DELETE FROM shifts")
    db.commit()
    return open_users