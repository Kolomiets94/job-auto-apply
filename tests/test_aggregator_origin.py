import unittest
from unittest.mock import patch
from aggregator_origin import parse_origin, is_gorodrabot_advert, resolve_gorodrabot, apply_origin


class OriginTests(unittest.TestCase):
    def test_resolved_vacancy_uses_hh_handler_and_keeps_role(self):
        from unittest.mock import Mock
        send = Mock(return_value={'status': 'SKIPPED', 'reason': 'already_applied_on_hh'})
        lead = {'category': 'qa', 'url': 'https://remote-job.ru/vacancy/show/1',
                'apply_url': 'https://gorodrabot.ru/advert/123/job'}
        with patch('aggregator_origin.resolve_gorodrabot', return_value={'origin_url': 'https://hh.ru/vacancy/123'}):
            result = apply_origin(lead, 'My letter', send)
        self.assertEqual(result['reason'], 'already_applied_on_hh')
        target = send.call_args.args[0]
        self.assertEqual(target['url'], 'https://hh.ru/vacancy/123')
        self.assertEqual(target['category'], 'qa')
        self.assertNotIn('apply_url', target)

    def test_blocked_aggregator_does_not_submit(self):
        from unittest.mock import Mock
        send = Mock()
        with patch('aggregator_origin.resolve_gorodrabot', return_value={'status': 'NEEDS_HUMAN', 'reason': 'aggregator_network_restricted'}):
            result = apply_origin({'apply_url': 'https://gorodrabot.ru/advert/123'}, 'Letter', send)
        send.assert_not_called()
        self.assertEqual(result['status'], 'NEEDS_HUMAN')

    def test_hh_id_deduplicates_regions_and_tracking(self):
        html = '<a href="https://hh.ru/vacancy/123?from=old">Apply</a><a href="https://ekaterinburg.hh.ru/vacancy/123">Apply</a>'
        self.assertEqual(parse_origin(html), {'origin_url': 'https://hh.ru/vacancy/123'})

    def test_two_vacancies_are_ambiguous(self):
        html = '<a href="https://hh.ru/vacancy/123">A</a><a href="https://hh.ru/vacancy/124">B</a>'
        self.assertEqual(parse_origin(html)['reason'], 'aggregator_origin_ambiguous')

    def test_restrictions_and_missing_advert(self):
        self.assertEqual(parse_origin('VPN detected', 423)['reason'], 'aggregator_network_restricted')
        self.assertEqual(parse_origin('missing', 404)['reason'], 'aggregator_advert_unavailable')
        self.assertEqual(parse_origin('cf-turnstile')['reason'], 'aggregator_security_challenge')

    def test_rejects_untrusted_links(self):
        html = '<a href="https://hh.ru.evil.test/vacancy/123">A</a><a href="https://user@hh.ru/vacancy/123">B</a>'
        self.assertEqual(parse_origin(html)['reason'], 'aggregator_origin_not_found')

    def test_invalid_origin_is_never_requested(self):
        with patch('aggregator_origin.build_opener') as opener:
            self.assertEqual(resolve_gorodrabot('https://evil.test/advert/123')['reason'], 'unsupported_aggregator_url')
            opener.assert_not_called()

    def test_exact_advert_host(self):
        self.assertTrue(is_gorodrabot_advert('https://gorodrabot.ru/advert/123/job'))
        for url in ('http://gorodrabot.ru/advert/123', 'https://gorodrabot.ru.evil.test/advert/123',
                    'https://gorodrabot.ru/profile', 'https://gorodrabot.ru:999/advert/123'):
            self.assertFalse(is_gorodrabot_advert(url))


if __name__ == '__main__':
    unittest.main()
