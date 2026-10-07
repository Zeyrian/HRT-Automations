import os
import sqlite3
import time

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "hrt.db")

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
    if get_open_shift(uid):
        return
    db.execute("INSERT INTO shifts (user_id, start_ts) VALUES (?, ?)", (uid, now_ts()))
    db.commit()


def toggle_break(uid):
    shift = get_open_shift(uid)
    if not shift:
        return
    now = now_ts()
    open_break = get_open_break(shift[0])
    if open_break:
        db.execute("UPDATE breaks SET end_ts=? WHERE id=?", (now, open_break[0]))
    else:
        db.execute("INSERT INTO breaks (shift_id, start_ts) VALUES (?, ?)", (shift[0], now))
    db.commit()


def end_shift(uid):
    """Ends the open shift. Returns (on_duty_seconds, break_seconds), or None if not on shift."""
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
    return now - start - breaks, breaks