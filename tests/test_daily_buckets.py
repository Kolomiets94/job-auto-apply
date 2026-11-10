from datetime import datetime, timezone
import queue_store


def test_daily_counts_separate_jobs_and_freelance(tmp_path, monkeypatch):
    monkeypatch.setattr(queue_store, 'DB_PATH', str(tmp_path / 'history.db'))
    for source in ('hh', 'habr_career', 'habr_freelance'):
        lid = queue_store.enqueue({'url': 'https://example.com/' + source, 'source': source})
        queue_store.set_state(lid, 'SUBMITTED')
    assert queue_store.submitted_today('jobs') == 2
    assert queue_store.submitted_today('freelance') == 1
    assert queue_store.submitted_today() == 3



def test_reply_status_change_preserves_original_submission_day(tmp_path, monkeypatch):
    monkeypatch.setattr(queue_store, 'DB_PATH', str(tmp_path / 'history.db'))
    lid = queue_store.enqueue({'url': 'https://example.com/submitted', 'source': 'hh'})
    queue_store.set_state(lid, 'SUBMITTED')
    with queue_store._db() as conn:
        row = conn.execute('SELECT submitted_at FROM leads WHERE id=?', (lid,)).fetchone()
        original_submitted_at = row[0]
        conn.execute(
            "UPDATE leads SET updated_at=?,state='REPLIED' WHERE id=?",
            ('2999-01-01T00:00:00+00:00', lid),
        )
    queue_store.set_state(lid, 'REPLIED')
    with queue_store._db() as conn:
        row = conn.execute('SELECT submitted_at FROM leads WHERE id=?', (lid,)).fetchone()
    assert row[0] == original_submitted_at
