import unittest
from application_links import application_link, hh_vacancy_url


class ApplicationLinkTests(unittest.TestCase):
    def test_description_link_reaches_authenticated_hh_handler(self):
        from unittest.mock import patch
        import job_sources
        import browser_apply
        lead = job_sources.job('jobicy', 'Junior React Developer', 'https://board.example/job/1',
                               '<a href="https://hh.ru/vacancy/123?from=board">Apply</a>')
        with patch.object(browser_apply, 'apply_hh', return_value={'status': 'SUBMITTED', 'reason': 'browser_hh_sent'}) as submit:
            result = browser_apply.dispatch_browser(lead, 'Individual letter')
        self.assertEqual(result['status'], 'SUBMITTED')
        self.assertEqual(submit.call_args.args[0]['url'], 'https://hh.ru/vacancy/123')
        self.assertEqual(submit.call_args.args[1], 'Individual letter')

    def test_mailto_description_reaches_gmail_api(self):
        import os
        from unittest.mock import patch
        import job_sources
        import application_dispatcher
        lead = job_sources.job('jobicy', 'Junior React Developer', 'https://board.example/job/1',
                               '<a href="mailto:jobs@example.org">Отправьте резюме</a>')
        with patch.dict(os.environ, {'AUTO_SEND_EMAIL': '1'}), \
             patch.object(application_dispatcher, 'application_time_allowed', return_value=True), \
             patch('gmail_api.is_configured', return_value=True), \
             patch('gmail_api.send_message') as send:
            result = application_dispatcher.dispatch(lead, 'Individual letter')
            args = send.call_args.args
        self.assertEqual(result['status'], 'SUBMITTED')
        self.assertEqual(args[0], 'jobs@example.org')
        self.assertEqual(args[1], 'Отклик: Junior React Developer')

    def test_explicit_hh_link_preserves_original_vacancy(self):
        description = '<a href="https://ekaterinburg.hh.ru/vacancy/123?from=board"><b>Откликнуться</b></a>'
        self.assertEqual(application_link(description, 'https://board.example/job/1'), 'https://hh.ru/vacancy/123')

    def test_explicit_email_and_relative_form(self):
        self.assertEqual(application_link('<a href="mailto:jobs@example.org">Send your CV</a>', 'https://board.example/job/1'), 'mailto:jobs@example.org')
        self.assertEqual(application_link('<a href="/apply/1">Apply now</a>', 'https://board.example/job/1'), 'https://board.example/apply/1')

    def test_contacts_and_multiple_forms_are_not_guessed(self):
        self.assertIsNone(application_link('<a href="mailto:privacy@example.org">Privacy</a>', 'https://board.example/job/1'))
        self.assertIsNone(application_link('<a href="https://a.example/apply">Apply</a><a href="https://b.example/apply">Apply</a>', 'https://board.example/job/1'))

    def test_malformed_hh_destination_is_rejected(self):
        for url in ('https://hh.ru.evil.test/vacancy/123', 'https://user@hh.ru/vacancy/123', 'http://hh.ru/vacancy/123', 'https://hh.ru/vacancy/123/responses'):
            self.assertIsNone(hh_vacancy_url(url))

    def test_dangerous_schemes_are_not_application_links(self):
        self.assertIsNone(application_link('<a href="javascript:alert(1)">Apply</a>', 'https://board.example/job/1'))


if __name__ == '__main__':
    unittest.main()
