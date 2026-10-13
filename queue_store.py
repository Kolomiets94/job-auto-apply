"""Persistent lead queue using SQLite locally or Neon PostgreSQL in production."""

import hashlib
import json
import os
import re
from urllib.parse import urlsplit
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo

DB_PATH = os.getenv("HUNTER_DB", "hunter.db")
STATES = (
    "FOUND", "SHORTLISTED", "APPLYING", "SUBMITTED", "NEEDS_CONFIRMATION",
    "REPLIED", "WON", "SKIPPED", "FAILED", "NEEDS_HUMAN",
)


class _PgConnection:
    def __init__(self, conn):
        self.conn = conn
        self.row_factory = None

    def execute(self, sql, params=()):
        from psycopg.rows import dict_row
        sql = sql.replace("INSERT OR IGNORE INTO leads", "INSERT INTO leads")
        if sql.lstrip().startswith("INSERT INTO leads"):
            sql += " ON CONFLICT (id) DO NOTHING"
        sql = sql.replace("?", "%s")
        cur = self.conn.cursor(row_factory=dict_row if self.row_factory else None)
        cur.execute(sql, params)
        if self.row_factory:
            class _Result:
                def __init__(self, cursor): self.cursor = cursor
                def fetchall(self): return list(self.cursor.fetchall())
                def fetchone(self): return self.cursor.fetchone()
            return _Result(cur)
        return cur

    def __enter__(self):
        self.conn.__enter__()
        return self

    def __exit__(self, *args):
        return self.conn.__exit__(*args)


def _db():
    url = os.getenv("DATABASE_URL", "").strip()
    if url:
        import psycopg
        conn = psycopg.connect(url, connect_timeout=10)
        conn.execute("""CREATE TABLE IF NOT EXISTS leads(
          id TEXT PRIMARY KEY, url TEXT, source TEXT, title TEXT, state TEXT,
          score INTEGER DEFAULT 0, payload TEXT, updated_at TEXT)""")
        conn.commit()
        return _PgConnection(conn)
    c = sqlite3.connect(DB_PATH)
    c.execute("""CREATE TABLE IF NOT EXISTS leads(
      id TEXT PRIMARY KEY, url TEXT, source TEXT, title TEXT, state TEXT,
      score INTEGER DEFAULT 0, payload TEXT, updated_at TEXT)""")
    c.commit()
    return c


def _vacancy_key(url):
    """Identify HH vacancies by ID, independent of region and tracking parameters."""
    try:
        parts = urlsplit(str(url or ""))
        host = (parts.hostname or "").lower()
        match = re.fullmatch(r"/vacancy/(\d+)/?", parts.path)
        if (host == "hh.ru" or host.endswith(".hh.ru")) and match:
            return "hh:" + match.group(1)
    except ValueError:
        pass
    return str(url or "")


def lead_id(lead):
    raw = _vacancy_key(lead.get("url")) or json.dumps(lead, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode()).hexdigest()


def enqueue(lead):
    lid = lead_id(lead)
    now = datetime.now(timezone.utc).isoformat()
    with _db() as c:
        c.execute("""INSERT OR IGNORE INTO leads
        (id,url,source,title,state,score,payload,updated_at)
        VALUES(?,?,?,?,?,?,?,?)""", (
            lid, lead.get("url"), lead.get("source"), lead.get("title"),
            "FOUND", int(lead.get("profit_score", 0)),
            json.dumps(lead, ensure_ascii=False), now,
        ))
    # Refresh metadata without reopening a delivered application or changing its
    # submission timestamp (daily counts depend on that timestamp).
    with _db() as c:
        c.execute("""UPDATE leads SET url=?,source=?,title=?,score=?,payload=?
                     WHERE id=? AND state NOT IN ('SUBMITTED','REPLIED','WON')""", (
            lead.get("url"), lead.get("source"), lead.get("title"),
            int(lead.get("profit_score", 0)), json.dumps(lead, ensure_ascii=False), lid,
        ))
    return lid


def queued_leads(limit=1000):
    """Recover previously discovered, undelivered leads for matching again."""
    with _db() as c:
        rows = c.execute(
            """SELECT payload FROM leads
               WHERE state NOT IN ('SUBMITTED','REPLIED','WON')
               ORDER BY updated_at DESC LIMIT ?""", (limit,)
        ).fetchall()
    leads = []
    for (payload,) in rows:
        try:
            lead = json.loads(payload)
        except (ValueError, TypeError):
            continue
        if isinstance(lead, dict) and lead.get("url"):
            leads.append(lead)
    return leads


def set_state(lid, state):
    if state not in STATES:
        raise ValueError("invalid state")
    with _db() as c:
        c.execute(
            "UPDATE leads SET state=?,updated_at=? WHERE id=?",
            (state, datetime.now(timezone.utc).isoformat(), lid),
        )


def get_state(lid):
    with _db() as c:
        row = c.execute("SELECT state FROM leads WHERE id=?", (lid,)).fetchone()
    return row[0] if row else None


def was_submitted(lid):
    sent_states = ("SUBMITTED", "REPLIED", "WON")
    with _db() as c:
        row = c.execute("SELECT url,state FROM leads WHERE id=?", (lid,)).fetchone()
        if not row:
            return False
        if row[1] in sent_states:
            return True
        key = _vacancy_key(row[0])
        if not key.startswith("hh:"):
            return False
        # Older releases hashed the full URL. Keep those records usable,
        # including records written through another region or search link.
        history = c.execute(
            "SELECT url FROM leads WHERE state IN ('SUBMITTED','REPLIED','WON')"
        ).fetchall()
        return any(_vacancy_key(url) == key for (url,) in history)


def submitted_today(bucket=None):
    """Count each category separately using the candidate's local calendar day."""
    from profit_ranker import FREELANCE_SOURCES
    local = datetime.now(ZoneInfo("Asia/Yekaterinburg"))
    start = local.replace(hour=0, minute=0, second=0, microsecond=0)
    start_utc = start.astimezone(timezone.utc).isoformat()
    end_utc = (start + timedelta(days=1)).astimezone(timezone.utc).isoformat()
    with _db() as c:
        rows = c.execute(
            """SELECT source FROM leads
               WHERE state IN ('SUBMITTED','REPLIED','WON')
               AND updated_at>=? AND updated_at<?""",
            (start_utc, end_utc),
        ).fetchall()
    if bucket is None:
        return len(rows)
    if bucket not in ("jobs", "freelance"):
        raise ValueError("invalid daily limit bucket")
    return sum(1 for (source,) in rows
               if ((str(source or "").lower() in FREELANCE_SOURCES) == (bucket == "freelance")))


def list_queue(limit=100):
    with _db() as c:
        c.row_factory = sqlite3.Row
        rows = c.execute(
            "SELECT * FROM leads ORDER BY score DESC,updated_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(x) for x in rows]

