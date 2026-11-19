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
        sql = sql.replace("INSERT OR IGNORE INTO outreach", "INSERT INTO outreach")
        if sql.lstrip().startswith(("INSERT INTO leads", "INSERT INTO outreach")):
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
          score INTEGER DEFAULT 0, payload TEXT, updated_at TEXT, submitted_at TEXT)""")
        conn.execute("ALTER TABLE leads ADD COLUMN IF NOT EXISTS submitted_at TEXT")
        conn.execute("""CREATE TABLE IF NOT EXISTS outreach(
          id TEXT PRIMARY KEY, company TEXT, opportunity_type TEXT, vacancy_url TEXT,
          status TEXT, payload TEXT, created_at TEXT, updated_at TEXT,
          contacted_at TEXT, replied_at TEXT, follow_up_at TEXT,
          feedback_reason TEXT, feedback_recorded_at TEXT)""")
        conn.execute("ALTER TABLE outreach ADD COLUMN IF NOT EXISTS feedback_reason TEXT")
        conn.execute("ALTER TABLE outreach ADD COLUMN IF NOT EXISTS feedback_recorded_at TEXT")
        conn.execute("""UPDATE leads SET submitted_at=updated_at
                        WHERE submitted_at IS NULL AND state IN ('SUBMITTED','REPLIED','WON')""")
        conn.commit()
        return _PgConnection(conn)
    c = sqlite3.connect(DB_PATH)
    c.execute("""CREATE TABLE IF NOT EXISTS leads(
      id TEXT PRIMARY KEY, url TEXT, source TEXT, title TEXT, state TEXT,
      score INTEGER DEFAULT 0, payload TEXT, updated_at TEXT, submitted_at TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS outreach(
      id TEXT PRIMARY KEY, company TEXT, opportunity_type TEXT, vacancy_url TEXT,
      status TEXT, payload TEXT, created_at TEXT, updated_at TEXT,
      contacted_at TEXT, replied_at TEXT, follow_up_at TEXT,
      feedback_reason TEXT, feedback_recorded_at TEXT)""")
    for column, sql_type in (("feedback_reason", "TEXT"), ("feedback_recorded_at", "TEXT")):
        try:
            c.execute(f"ALTER TABLE outreach ADD COLUMN {column} {sql_type}")
        except sqlite3.OperationalError:
            pass
    try:
        c.execute("ALTER TABLE leads ADD COLUMN submitted_at TEXT")
    except Exception:
        # Existing databases already have the column.
        pass
    # Backfill legacy delivered rows once; future state changes retain this timestamp.
    c.execute("""UPDATE leads SET submitted_at=updated_at
                 WHERE submitted_at IS NULL AND state IN ('SUBMITTED','REPLIED','WON')""")
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
    return enqueue_many([lead])[0]


def enqueue_many(leads):
    """Refresh a discovery batch in one transaction/connection."""
    ids = []
    with _db() as c:
        for lead in leads:
            lid = lead_id(lead)
            ids.append(lid)
            payload = json.dumps(lead, ensure_ascii=False)
            c.execute("""INSERT OR IGNORE INTO leads
            (id,url,source,title,state,score,payload,updated_at)
            VALUES(?,?,?,?,?,?,?,?)""", (
                lid, lead.get("url"), lead.get("source"), lead.get("title"),
                "FOUND", int(lead.get("profit_score", 0)), payload,
                datetime.now(timezone.utc).isoformat(),
            ))
            # Preserve delivered states and their submission timestamps.
            c.execute("""UPDATE leads SET url=?,source=?,title=?,score=?,payload=?
                         WHERE id=? AND state NOT IN ('SUBMITTED','REPLIED','WON')""", (
                lead.get("url"), lead.get("source"), lead.get("title"),
                int(lead.get("profit_score", 0)), payload, lid,
            ))
    return ids


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
            """UPDATE leads SET state=?,updated_at=?,
               submitted_at=CASE
                 WHEN ?='SUBMITTED' AND submitted_at IS NULL THEN ?
                 ELSE submitted_at END
               WHERE id=?""",
            (state, datetime.now(timezone.utc).isoformat(), state,
             datetime.now(timezone.utc).isoformat(), lid),
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
    local = datetime.now(ZoneInfo(os.getenv("APPLICATION_TIMEZONE", "Asia/Yekaterinburg")))
    start = local.replace(hour=0, minute=0, second=0, microsecond=0)
    start_utc = start.astimezone(timezone.utc).isoformat()
    end_utc = (start + timedelta(days=1)).astimezone(timezone.utc).isoformat()
    with _db() as c:
        rows = c.execute(
            """SELECT source FROM leads
               WHERE state IN ('SUBMITTED','REPLIED','WON')
               AND submitted_at>=? AND submitted_at<?""",
            (start_utc, end_utc),
        ).fetchall()
    if bucket is None:
        return len(rows)
    if bucket not in ("jobs", "freelance"):
        raise ValueError("invalid daily limit bucket")
    return sum(1 for (source,) in rows
               if ((str(source or "").lower() in FREELANCE_SOURCES) == (bucket == "freelance")))



def submitted_this_week(bucket=None):
    """Count confirmed submissions since Monday 00:00 in the configured application timezone."""
    from profit_ranker import FREELANCE_SOURCES
    local = datetime.now(ZoneInfo(os.getenv("APPLICATION_TIMEZONE", "Asia/Yekaterinburg")) )
    monday = (local - timedelta(days=local.weekday())).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    start_utc = monday.astimezone(timezone.utc).isoformat()
    with _db() as c:
        rows = c.execute(
            """SELECT source FROM leads
               WHERE state IN ('SUBMITTED','REPLIED','WON') AND submitted_at>=?""",
            (start_utc,),
        ).fetchall()
    if bucket is None:
        return len(rows)
    if bucket not in ("jobs", "freelance"):
        raise ValueError("invalid weekly limit bucket")
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



OUTREACH_STATES = ("DRAFT", "CONTACTED", "REPLIED", "INTERVIEW", "REJECTED", "OFFER", "NO_RESPONSE", "SUPPRESSED")


def _outreach_id(draft):
    raw = "|".join(str(draft.get(k) or "").strip().casefold()
                   for k in ("company", "opportunity_type", "vacancy_url"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def save_outreach_drafts(drafts):
    """Persist deduplicated company outreach drafts without sending them."""
    now = datetime.now(timezone.utc).isoformat()
    ids = []
    with _db() as c:
        for draft in drafts:
            oid = _outreach_id(draft)
            ids.append(oid)
            payload = json.dumps(draft, ensure_ascii=False)
            c.execute("""INSERT OR IGNORE INTO outreach
              (id,company,opportunity_type,vacancy_url,status,payload,created_at,updated_at)
              VALUES(?,?,?,?,?,?,?,?)""",
              (oid, draft.get("company"), draft.get("opportunity_type"),
               draft.get("vacancy_url"), "DRAFT", payload, now, now))
            # Refresh content only while it is still a draft; never reset a sent/replied record.
            c.execute("""UPDATE outreach SET payload=?,updated_at=?
                         WHERE id=? AND status='DRAFT'""", (payload, now, oid))
    return ids


FEEDBACK_REASONS = (
    "skills_gap", "experience_gap", "location_restriction", "work_authorization",
    "language", "salary", "role_mismatch", "position_filled", "other",
)


def update_outreach_status(outreach_id, status, follow_up_days=7, feedback_reason=None):
    """Record a confirmed human/platform event; never sends messages or stores raw replies."""
    if status not in OUTREACH_STATES:
        raise ValueError("invalid outreach status")
    if feedback_reason is not None:
        if status != "REJECTED":
            raise ValueError("feedback_reason is only valid for REJECTED status")
        if feedback_reason not in FEEDBACK_REASONS:
            raise ValueError("invalid feedback_reason")
    now = datetime.now(timezone.utc).isoformat()
    follow_up = None
    if status == "CONTACTED":
        follow_up = (datetime.now(timezone.utc) + timedelta(days=max(1, min(int(follow_up_days), 30)))).isoformat()
    with _db() as c:
        c.execute("""UPDATE outreach SET status=?,updated_at=?,
          contacted_at=CASE WHEN ?='CONTACTED' AND contacted_at IS NULL THEN ? ELSE contacted_at END,
          replied_at=CASE WHEN ? IN ('REPLIED','INTERVIEW','REJECTED','OFFER') THEN ? ELSE replied_at END,
          follow_up_at=CASE WHEN ?='CONTACTED' THEN ? ELSE follow_up_at END,
          feedback_reason=CASE WHEN ?='REJECTED' THEN ? ELSE feedback_reason END,
          feedback_recorded_at=CASE WHEN ?='REJECTED' AND ? IS NOT NULL THEN ? ELSE feedback_recorded_at END
          WHERE id=?""", (
            status, now, status, now, status, now, status, follow_up,
            status, feedback_reason, status, feedback_reason, now, outreach_id,
        ))


def build_outcome_feedback_report(records=None):
    """Summarize categorized employer outcomes; never auto-tunes matching weights."""
    from collections import Counter
    items = list_outreach(limit=1000) if records is None else list(records)
    rejected = [item for item in items if item.get("status") == "REJECTED"]
    reasons = Counter(item.get("feedback_reason") for item in rejected if item.get("feedback_reason"))
    responses = sum(item.get("status") in ("REPLIED", "INTERVIEW", "REJECTED", "OFFER") for item in items)
    interviews = sum(item.get("status") == "INTERVIEW" for item in items)
    offers = sum(item.get("status") == "OFFER" for item in items)
    labels = {
        "skills_gap": "Не совпали навыки",
        "experience_gap": "Недостаточно опыта",
        "location_restriction": "Ограничение по локации",
        "work_authorization": "Нет права/возможности найма в стране",
        "language": "Язык",
        "salary": "Зарплатные ожидания",
        "role_mismatch": "Несовпадение роли",
        "position_filled": "Позиция уже закрыта",
        "other": "Другая причина",
    }
    lines = [
        "ОБРАТНАЯ СВЯЗЬ ПО ОТКЛИКАМ",
        f"Записей в журнале: {len(items)}; ответы работодателей: {responses}; интервью: {interviews}; предложения: {offers}.",
        f"Отказы с указанной категорией причины: {sum(reasons.values())}.",
    ]
    if reasons:
        lines.append("Причины отказов:")
        lines.extend(f"- {labels.get(reason, reason)}: {count}" for reason, count in reasons.most_common())
    else:
        lines.append("Пока недостаточно размеченных отказов для анализа причин.")
    lines.append("Эти данные показывают наблюдаемые причины; веса ATS автоматически не меняются.")
    return "\\n".join(lines)


def list_outreach(limit=100, status=None):
    """Return persisted outreach records, optionally filtered by lifecycle status."""
    with _db() as c:
        c.row_factory = sqlite3.Row
        if status:
            if status not in OUTREACH_STATES:
                raise ValueError("invalid outreach status")
            rows = c.execute("SELECT * FROM outreach WHERE status=? ORDER BY updated_at DESC LIMIT ?",
                             (status, limit)).fetchall()
        else:
            rows = c.execute("SELECT * FROM outreach ORDER BY updated_at DESC LIMIT ?",
                             (limit,)).fetchall()
    return [dict(row) for row in rows]


def due_outreach_followups(limit=100):
    """List contacted companies whose one follow-up window has elapsed without a reply."""
    now = datetime.now(timezone.utc).isoformat()
    with _db() as c:
        c.row_factory = sqlite3.Row
        rows = c.execute("""SELECT * FROM outreach
          WHERE status='CONTACTED' AND follow_up_at IS NOT NULL AND follow_up_at<=?
          ORDER BY follow_up_at ASC LIMIT ?""", (now, limit)).fetchall()
    return [dict(row) for row in rows]
