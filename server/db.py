"""SQLite helpers for the two-person room."""
from __future__ import annotations

import os
import re
import sqlite3
import threading
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("JINBU_DATA", str(ROOT / "var")))
DB_PATH = DATA_DIR / "jinbu.db"

_lock = threading.Lock()
_conn: sqlite3.Connection | None = None


SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS rooms (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  code TEXT NOT NULL UNIQUE,
  punishment_text TEXT NOT NULL,
  friend_placeholder TEXT,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS members (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  room_id INTEGER NOT NULL REFERENCES rooms(id),
  name TEXT NOT NULL,
  token TEXT NOT NULL UNIQUE,
  daily_new INTEGER NOT NULL DEFAULT 20,
  review_cap INTEGER NOT NULL DEFAULT 40,
  points_total INTEGER NOT NULL DEFAULT 0,
  streak INTEGER NOT NULL DEFAULT 0,
  last_checkin TEXT,
  streak_bonuses TEXT NOT NULL DEFAULT '{"3":false,"7":false,"14":false}',
  punishment_pending INTEGER NOT NULL DEFAULT 0,
  missed_yesterday INTEGER NOT NULL DEFAULT 0,
  miss_processed_on TEXT,
  joined_date TEXT NOT NULL,
  created_at TEXT NOT NULL,
  study_plan TEXT NOT NULL DEFAULT 'cet4',
  carry_new INTEGER NOT NULL DEFAULT 0,
  carry_review INTEGER NOT NULL DEFAULT 0,
  ko_carry_new INTEGER NOT NULL DEFAULT 0,
  ko_carry_review INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS daily (
  member_id INTEGER NOT NULL REFERENCES members(id),
  date TEXT NOT NULL,
  review_target INTEGER,
  new_target INTEGER,
  quiz_target INTEGER NOT NULL DEFAULT 1,
  reviewed_due_json TEXT NOT NULL DEFAULT '[]',
  new_introduced_json TEXT NOT NULL DEFAULT '[]',
  reviewed_all_json TEXT NOT NULL DEFAULT '[]',
  vocab_done INTEGER NOT NULL DEFAULT 0,
  quizzes_done INTEGER NOT NULL DEFAULT 0,
  checkin INTEGER NOT NULL DEFAULT 0,
  punishment INTEGER NOT NULL DEFAULT 0,
  points INTEGER NOT NULL DEFAULT 0,
  ko_review_target INTEGER,
  ko_new_target INTEGER,
  ko_quiz_target INTEGER NOT NULL DEFAULT 0,
  ko_reviewed_due_json TEXT NOT NULL DEFAULT '[]',
  ko_new_introduced_json TEXT NOT NULL DEFAULT '[]',
  ko_reviewed_all_json TEXT NOT NULL DEFAULT '[]',
  ko_vocab_done INTEGER NOT NULL DEFAULT 0,
  ko_quizzes_done INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (member_id, date)
);

CREATE TABLE IF NOT EXISTS word_progress (
  member_id INTEGER NOT NULL REFERENCES members(id),
  word_id TEXT NOT NULL,
  interval_days INTEGER NOT NULL DEFAULT 0,
  due_ts INTEGER NOT NULL DEFAULT 0,
  reps INTEGER NOT NULL DEFAULT 0,
  lapses INTEGER NOT NULL DEFAULT 0,
  status TEXT NOT NULL DEFAULT 'new',
  last_rating TEXT,
  last_reviewed INTEGER,
  introduced_on TEXT,
  round_correct INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (member_id, word_id)
);

CREATE TABLE IF NOT EXISTS custom_words (
  id TEXT PRIMARY KEY,
  member_id INTEGER NOT NULL REFERENCES members(id),
  word TEXT NOT NULL,
  ipa TEXT NOT NULL DEFAULT '',
  meaning TEXT NOT NULL,
  example TEXT NOT NULL DEFAULT '',
  example_zh TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS quiz_stats (
  member_id INTEGER PRIMARY KEY REFERENCES members(id),
  taken INTEGER NOT NULL DEFAULT 0,
  correct INTEGER NOT NULL DEFAULT 0,
  answered INTEGER NOT NULL DEFAULT 0,
  recent_json TEXT NOT NULL DEFAULT '[]',
  wrong_book_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS app_meta (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
"""

# One-time assignment: the live room's partner keeps CET-4 and also gets Korean.
_KOO_PLAN_KEY = "koo_korean_plan_v1"
_CURVE_KEY = "review_curve_v1"
_NAME_PUNCT = re.compile(r"[\s_\-–—·•.。,，、'\"`~～!！?？:：;；()（）\[\]【】／/\\|]+")


def normalize_display_name(name: str) -> str:
    """Ignore case, width, and light punctuation so koo陸_ still matches."""
    text = unicodedata.normalize("NFKC", name or "").strip().lower()
    text = text.replace("陸", "陆")
    return _NAME_PUNCT.sub("", text)


def is_koo_partner_name(name: str) -> bool:
    folded = normalize_display_name(name)
    return folded in {"koo陆", "koolu"}


def _table_cols(con: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in con.execute(f"PRAGMA table_info({table})")}


def _add_col(con: sqlite3.Connection, table: str, name: str, decl: str) -> None:
    if name not in _table_cols(con, table):
        con.execute(f"ALTER TABLE {table} ADD COLUMN {name} {decl}")


def _migrate(con: sqlite3.Connection) -> None:
    """Add new columns without touching existing progress, then assign Korean once."""
    _add_col(con, "members", "study_plan", "TEXT NOT NULL DEFAULT 'cet4'")
    _add_col(con, "daily", "ko_review_target", "INTEGER")
    _add_col(con, "daily", "ko_new_target", "INTEGER")
    _add_col(con, "daily", "ko_quiz_target", "INTEGER NOT NULL DEFAULT 0")
    _add_col(con, "daily", "ko_reviewed_due_json", "TEXT NOT NULL DEFAULT '[]'")
    _add_col(con, "daily", "ko_new_introduced_json", "TEXT NOT NULL DEFAULT '[]'")
    _add_col(con, "daily", "ko_reviewed_all_json", "TEXT NOT NULL DEFAULT '[]'")
    _add_col(con, "daily", "ko_vocab_done", "INTEGER NOT NULL DEFAULT 0")
    _add_col(con, "daily", "ko_quizzes_done", "INTEGER NOT NULL DEFAULT 0")
    _add_col(con, "word_progress", "round_correct", "INTEGER NOT NULL DEFAULT 0")
    _add_col(con, "members", "carry_new", "INTEGER NOT NULL DEFAULT 0")
    _add_col(con, "members", "carry_review", "INTEGER NOT NULL DEFAULT 0")
    _add_col(con, "members", "ko_carry_new", "INTEGER NOT NULL DEFAULT 0")
    _add_col(con, "members", "ko_carry_review", "INTEGER NOT NULL DEFAULT 0")
    con.execute(
        "CREATE TABLE IF NOT EXISTS app_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
    )
    done = con.execute("SELECT value FROM app_meta WHERE key=?", (_KOO_PLAN_KEY,)).fetchone()
    if done is None:
        # Existing members are on CET-4. Add Korean beside that plan for koo陸_
        # only. Run once so a later settings change is not overwritten on restart.
        for row in con.execute("SELECT id, name, study_plan FROM members"):
            if not is_koo_partner_name(row["name"] if isinstance(row, sqlite3.Row) else row[1]):
                continue
            current = (row["study_plan"] if isinstance(row, sqlite3.Row) else row[2]) or "cet4"
            if current == "korean":
                updated = "korean"
            elif current == "both":
                updated = "both"
            else:
                updated = "both"
            member_id = row["id"] if isinstance(row, sqlite3.Row) else row[0]
            con.execute("UPDATE members SET study_plan=? WHERE id=?", (updated, member_id))
        con.execute(
            "INSERT INTO app_meta (key, value) VALUES (?, ?)",
            (_KOO_PLAN_KEY, "1"),
        )
    # Fold older intervals onto 1, 2, 4, 7, 15, 30 without moving due dates,
    # points, reps, or check-ins. Values already on the curve stay put.
    curved = con.execute("SELECT value FROM app_meta WHERE key=?", (_CURVE_KEY,)).fetchone()
    if curved is None:
        con.execute(
            """UPDATE word_progress
               SET interval_days = CASE
                 WHEN interval_days IS NULL OR interval_days <= 0 THEN 0
                 WHEN interval_days < 2 THEN 1
                 WHEN interval_days < 4 THEN 2
                 WHEN interval_days < 7 THEN 4
                 WHEN interval_days < 15 THEN 7
                 WHEN interval_days < 30 THEN 15
                 ELSE 30
               END"""
        )
        con.execute(
            "INSERT INTO app_meta (key, value) VALUES (?, ?)",
            (_CURVE_KEY, "1,2,4,7,15,30"),
        )
    # Words already recalled 3+ times, back when a round needed 5, now count as passed.
    from .logic import apply_round_need_migration

    apply_round_need_migration(con)
    con.commit()


def connect() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        _conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        _conn.executescript(SCHEMA)
        _conn.commit()
        _migrate(_conn)
    return _conn


def lock():
    return _lock


def row_to_dict(row: sqlite3.Row | None) -> dict | None:
    if row is None:
        return None
    return {k: row[k] for k in row.keys()}


def execute(sql: str, params=(), commit: bool = False):
    con = connect()
    cur = con.execute(sql, params)
    if commit:
        con.commit()
    return cur


def fetchone(sql: str, params=()):
    return row_to_dict(execute(sql, params).fetchone())


def fetchall(sql: str, params=()):
    return [row_to_dict(r) for r in execute(sql, params).fetchall()]
