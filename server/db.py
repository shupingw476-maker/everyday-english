"""SQLite helpers for the two-person room."""
from __future__ import annotations

import os
import sqlite3
import threading
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
  created_at TEXT NOT NULL
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
"""


def connect() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        _conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        _conn.executescript(SCHEMA)
        _conn.commit()
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
