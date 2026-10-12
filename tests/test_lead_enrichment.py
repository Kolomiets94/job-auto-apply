import unittest
from unittest.mock import Mock, patch
from lead_enrichment import enrich_lead, needs_enrichment


class EnrichmentTests(unittest.TestCase):
    def lead(self):
        return {'source': 'geekjob', 'title': 'Junior React Developer',
                'url': 'https://geekjob.ru/vacancy/123', 'description': 'Junior React Developer'}

    def test_recovers_description_and_original_hh_application(self):
        page = '<nav>Senior SQL jobs</nav><main>Junior React Developer. Remote HTML CSS REST API.<a href="https://hh.ru/vacancy/123">Откликнуться</a></main>'
        with patch('lead_enrichment.requests.get', return_value=Mock(status_code=200, text=page)):
            lead = enrich_lead(self.lead())
        self.assertIn('REST API', lead['description'])
        self.assertNotIn('Senior SQL', lead['description'])
        self.assertEqual(lead['apply_url'], 'https://hh.ru/vacancy/123')

    def test_archived_page_is_unavailable(self):
        with patch('lead_enrichment.requests.get', return_value=Mock(status_code=200, text='Вакансия в архиве')):
            self.assertTrue(enrich_lead(self.lead())['unavailable'])

    def test_remote_job_unpublished_is_unavailable(self):
        page = '<h1>Junior QA (вакансия не опубликована)</h1><div class="panel-body">SQL required</div><div class="panel-footer"></div>'
        lead = {**self.lead(), 'source': 'remote_job_ru', 'title': 'Junior QA',
                'url': 'https://remote-job.ru/vacancy/show/123/qa'}
        with patch('lead_enrichment.requests.get', return_value=Mock(status_code=200, text=page)):
            result = enrich_lead(lead)
        self.assertTrue(result['unavailable'])

    def test_remote_job_description_excludes_recommendations(self):
        from profit_ranker import rank_lead
        page = '<h1>Junior React Developer</h1><div class="panel-body">React HTML CSS</div><div class="panel-footer"></div><aside>SQL required</aside>'
        lead = {**self.lead(), 'source': 'remote_job_ru',
                'url': 'https://remote-job.ru/vacancy/show/123/react'}
        with patch('lead_enrichment.requests.get', return_value=Mock(status_code=200, text=page)):
            result = enrich_lead(lead)
        self.assertNotIn('SQL', result['description'])
        self.assertTrue(rank_lead(result)['eligible'])

    def test_read_failure_is_not_submission(self):
        with patch('lead_enrichment.requests.get', return_value=Mock(status_code=429)):
            lead = enrich_lead(self.lead())
        self.assertEqual(lead['enrichment_error'], 'source_http_429')
        self.assertNotIn('apply_url', lead)

    def test_rejects_cross_host_redirect_before_request(self):
        with patch('lead_enrichment.requests.get', return_value=Mock(status_code=302, headers={'Location': 'https://evil.example/job'})) as request:
            lead = enrich_lead(self.lead())
        self.assertEqual(request.call_count, 1)
        self.assertEqual(lead['enrichment_error'], 'unverified_source_url')

    def test_does_not_fetch_senior_or_unknown_source(self):
        self.assertFalse(needs_enrichment({**self.lead(), 'title': 'Senior React Developer'}))
        self.assertFalse(needs_enrichment({**self.lead(), 'source': 'unknown'}))


if __name__ == '__main__':
    unittest.main()
