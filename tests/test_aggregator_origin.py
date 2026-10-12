import unittest
from unittest.mock import patch
import aggregator_origin
from aggregator_origin import parse_origin, is_gorodrabot_advert, resolve_gorodrabot, apply_origin, direct_hh_origin


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

    def test_explicit_hh_origin_needs_unique_vacancy_id(self):
        self.assertEqual(direct_hh_origin({'description': 'https://hh.ru/vacancy/123?from=remote'}),
                         'https://hh.ru/vacancy/123')
        self.assertIsNone(direct_hh_origin({'description': 'https://hh.ru/vacancy/123 https://hh.ru/vacancy/124'}))

    def test_rate_limit_retries_with_bound_and_stops_other_adverts(self):
        from unittest.mock import Mock
        response = Mock()
        response.status = 429
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=None)
        with patch.object(aggregator_origin, '_GORODRABOT_RATE_LIMITED', False), \
             patch.object(aggregator_origin, '_FIRST_429', None), \
             patch.object(aggregator_origin, '_DEFERRED_ADVERTS', 0), \
             patch.object(aggregator_origin, '_AGGREGATOR_REQUESTS', 8), \
             patch.object(aggregator_origin, '_paced_open', return_value=response) as open_request, \
             patch('aggregator_origin.time.sleep') as sleep:
            result = resolve_gorodrabot('https://gorodrabot.ru/advert/123/job')
            again = resolve_gorodrabot('https://gorodrabot.ru/advert/124/job')
            diagnostics = aggregator_origin.origin_diagnostics()
        self.assertEqual(result['reason'], 'aggregator_rate_limited')
        self.assertEqual(again['reason'], 'aggregator_rate_limited')
        self.assertEqual(open_request.call_count, 4)
        self.assertEqual(diagnostics['first_429'], {
            'advert_path': '/advert/123/job', 'request_index': 8})
        self.assertEqual(diagnostics['deferred_adverts'], 1)
        self.assertEqual([x.args[0] for x in sleep.call_args_list], [60, 120, 240])

    def test_second_origin_request_waits_for_five_second_spacing(self):
        from unittest.mock import Mock
        reply = Mock(status=200)
        reply.read.return_value = b'<a href="https://hh.ru/vacancy/123">Apply</a>'
        reply.headers.get_content_charset.return_value = 'utf-8'
        reply.__enter__ = Mock(return_value=reply)
        reply.__exit__ = Mock(return_value=None)
        opener = Mock()
        opener.open.return_value = reply
        with patch.object(aggregator_origin, '_GORODRABOT_RATE_LIMITED', False), \
             patch.object(aggregator_origin, '_LAST_REQUEST_AT', None), \
             patch('aggregator_origin.build_opener', return_value=opener), \
             patch('aggregator_origin.time.monotonic', side_effect=[0, 0, 1, 5]) as monotonic, \
             patch('aggregator_origin.time.sleep') as sleep:
            self.assertIn('origin_url', resolve_gorodrabot('https://gorodrabot.ru/advert/123/job'))
            self.assertIn('origin_url', resolve_gorodrabot('https://gorodrabot.ru/advert/124/job'))
        sleep.assert_called_once_with(4)

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
