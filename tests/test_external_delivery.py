import os
import unittest
from unittest.mock import Mock, patch
import external_form_apply as external


class Nodes:
    def __init__(self, items=()):
        self.items = list(items)
    def count(self):
        return len(self.items)
    def nth(self, index):
        return self.items[index]
    @property
    def first(self):
        return self.items[0]


def field(name, kind='text', required=True):
    node = Mock()
    attrs = {'name': name, 'type': kind, 'required': '' if required else None}
    node.get_attribute.side_effect = lambda key: attrs.get(key)
    node.is_visible.return_value = True
    return node


class ExternalDeliveryTests(unittest.TestCase):
    def run_form(self, after, extra=(), upload=False):
        fields = [field('name'), field('email', 'email'), field('cover_letter'), *extra]
        send = Mock()
        form = Mock()
        file = field('resume', 'file')
        def locator(selector):
            if selector == 'input[type="file"]':
                return Nodes([file] if upload else [])
            if selector.startswith('input:not'):
                return Nodes(fields)
            if selector.startswith('button[type="submit"]'):
                return Nodes([send])
            return Nodes()
        form.locator.side_effect = locator
        body = Mock()
        body.inner_text.side_effect = ['Apply here', 'Apply here', after]
        page = Mock()
        page.url = 'https://jobs.lever.co/example/1'
        page.locator.side_effect = lambda selector: body if selector == 'body' else Nodes([form])
        playwright = Mock()
        browser = playwright.chromium.launch.return_value
        browser.new_page.return_value = page
        env = {'AUTO_BROWSER_APPLY': '1', 'REMOTE_JOB_NAME': 'Alexander Kolomiets',
               'REMOTE_JOB_EMAIL': 'candidate@example.org', 'REMOTE_JOB_PHONE': '+70000000000'}
        with patch.dict(os.environ, env), patch.object(external, 'sync_playwright') as start, \
             patch.object(external, 'application_time_allowed', return_value=True):
            start.return_value.__enter__.return_value = playwright
            result = external.apply_external({'apply_url': page.url, 'category': 'frontend'}, 'Personal letter')
        return result, send, fields

    def test_known_ats_submits_optional_fields_and_confirms(self):
        result, send, fields = self.run_form('Application received', [field('company', required=False)])
        self.assertEqual(result['status'], 'SUBMITTED')
        send.click.assert_called_once()
        fields[-1].fill.assert_not_called()

    def test_ambiguous_confirmation_is_not_counted(self):
        result, send, _ = self.run_form('Apply here')
        self.assertEqual(result['status'], 'NEEDS_CONFIRMATION')
        send.click.assert_called_once()

    def test_required_unknown_question_never_submits(self):
        result, send, _ = self.run_form('Apply here', [field('work_authorization')])
        self.assertEqual(result['reason'], 'external_unknown_field')
        send.click.assert_not_called()

    def test_missing_required_cv_never_submits(self):
        with patch.dict(os.environ, {'FRONTEND_CV_FILE': '', 'RESUME_FILE_FOR_UPLOAD': ''}):
            result, send, _ = self.run_form('Apply here', upload=True)
        self.assertEqual(result['reason'], 'external_resume_file_missing')
        send.click.assert_not_called()
