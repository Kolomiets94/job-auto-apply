import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import queue_store as queue


class BacklogTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.patch = patch.object(queue, 'DB_PATH', str(Path(self.temp.name) / 'hunter.db'))
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        self.temp.cleanup()

    def test_recovers_undelivered_and_excludes_sent(self):
        for n, state in ((1, 'NEEDS_CONFIRMATION'), (2, 'NEEDS_HUMAN'), (3, 'SUBMITTED')):
            lid = queue.enqueue({'url': f'https://hh.ru/vacancy/{n}', 'title': 'Junior React'})
            queue.set_state(lid, state)
        self.assertEqual({x['url'] for x in queue.queued_leads()}, {'https://hh.ru/vacancy/1', 'https://hh.ru/vacancy/2'})

    def test_refresh_metadata_does_not_reopen_sent_record(self):
        lead = {'url': 'https://hh.ru/vacancy/1', 'title': 'Junior React', 'description': 'old'}
        lid = queue.enqueue(lead)
        queue.set_state(lid, 'SUBMITTED')
        timestamp = queue.list_queue()[0]['updated_at']
        queue.enqueue({**lead, 'description': 'new'})
        self.assertTrue(queue.was_submitted(lid))
        self.assertEqual(queue.list_queue()[0]['updated_at'], timestamp)
        self.assertEqual(queue.queued_leads(), [])

    def test_refresh_pending_link_is_visible_to_retry(self):
        lead = {'url': 'https://board.example/1', 'title': 'Junior React'}
        lid = queue.enqueue(lead)
        queue.set_state(lid, 'NEEDS_CONFIRMATION')
        queue.enqueue({**lead, 'apply_url': 'https://hh.ru/vacancy/1'})
        self.assertEqual(queue.queued_leads()[0]['apply_url'], 'https://hh.ru/vacancy/1')
        self.assertEqual(queue.get_state(lid), 'NEEDS_CONFIRMATION')
