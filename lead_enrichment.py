"""Read full public vacancy descriptions before matching and dispatching."""
import re
from html.parser import HTMLParser
from urllib.parse import urlsplit, urljoin
import requests
from application_links import application_link
from entry_level import is_entry_level

SOURCE_HOSTS = {
    'jobicy': {'jobicy.com'}, 'remotive': {'remotive.com'},
    'weworkremotely': {'weworkremotely.com'}, 'arbeitnow': {'arbeitnow.com', 'www.arbeitnow.com'},
    'geekjob': {'geekjob.ru'}, 'getmatch': {'getmatch.ru'},
    'zarplata': {'zarplata.ru'}, 'remoteok': {'remoteok.com'},
}


class _Text(HTMLParser):
    def __init__(self):
        super().__init__()
        self.depth = 0
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag in ('script', 'style', 'nav', 'header', 'footer'):
            self.depth += 1

    def handle_endtag(self, tag):
        if tag in ('script', 'style', 'nav', 'header', 'footer') and self.depth:
            self.depth -= 1

    def handle_data(self, text):
        if not self.depth:
            self.parts.append(text)


def needs_enrichment(lead):
    source = str(lead.get('source') or '').lower()
    title = str(lead.get('title') or '')
    return (source in SOURCE_HOSTS and is_entry_level(title) and
            (len(str(lead.get('description') or '')) < 300 or
             not (lead.get('apply_url') or lead.get('apply_email'))))


def enrich_lead(lead):
    if not needs_enrichment(lead):
        return lead
    source = str(lead.get('source') or '').lower()
    url = str(lead.get('url') or '')
    try:
        for _ in range(3):
            parts = urlsplit(url)
            if (parts.scheme != 'https' or parts.hostname not in SOURCE_HOSTS[source]
                    or parts.username or parts.password or parts.port not in (None, 443)):
                return {**lead, 'enrichment_error': 'unverified_source_url'}
            response = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'},
                                    timeout=15, allow_redirects=False)
            if response.status_code in (301, 302, 303, 307, 308):
                url = urljoin(url, response.headers.get('Location', ''))
                continue
            if response.status_code in (404, 410):
                return {**lead, 'unavailable': True, 'enrichment_error': 'vacancy_unavailable'}
            if response.status_code != 200:
                return {**lead, 'enrichment_error': 'source_http_' + str(response.status_code)}
            html = response.text
            if len(html) > 2 * 1024 * 1024:
                return {**lead, 'enrichment_error': 'source_page_too_large'}
            parser = _Text()
            parser.feed(html)
            text = re.sub(r'\s+', ' ', ' '.join(parser.parts)).strip()
            if re.search(r'vacancy (?:is )?(?:closed|archived)|job (?:has )?expired|вакансия в архиве|вакансия закрыта', text, re.I):
                return {**lead, 'unavailable': True, 'enrichment_error': 'vacancy_unavailable'}
            from job_sources import explicit_application_email
            result = {**lead, 'description': text[:20000], 'enriched': True}
            if not lead.get('apply_email'):
                email = explicit_application_email(html)
                if email:
                    result['apply_email'] = email
            if not lead.get('apply_url'):
                destination = application_link(html, url)
                if destination:
                    result['apply_url'] = destination
            return result
        return {**lead, 'enrichment_error': 'too_many_source_redirects'}
    except (requests.RequestException, ValueError):
        return {**lead, 'enrichment_error': 'source_read_failed'}

