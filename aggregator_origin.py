"""Read GorodRabot adverts and resolve a single original HH vacancy.

This reader never sends candidate data or submits a form.
"""
import re
from html.parser import HTMLParser
from urllib.parse import urlsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler
from urllib.error import HTTPError, URLError

# Avoid hammering an aggregator after it explicitly rate-limits this run.
_GORODRABOT_RATE_LIMITED = False


def is_gorodrabot_advert(url):
    try:
        parts = urlsplit(url)
        return (parts.scheme == 'https' and parts.hostname in ('gorodrabot.ru', 'www.gorodrabot.ru')
                and not parts.username and not parts.password
                and parts.port in (None, 443)
                and bool(re.match(r'^/advert/\d+(?:/|$)', parts.path)))
    except ValueError:
        return False


class _VacancyLinks(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = set()

    def handle_starttag(self, tag, attrs):
        if tag != 'a':
            return
        href = dict(attrs).get('href') or ''
        try:
            parts = urlsplit(href)
            host = parts.hostname or ''
            match = re.fullmatch(r'/vacancy/(\d+)/?', parts.path)
            if (parts.scheme == 'https' and (host == 'hh.ru' or host.endswith('.hh.ru'))
                    and not parts.username and not parts.password
                    and parts.port in (None, 443) and match):
                self.ids.add(match.group(1))
        except ValueError:
            pass


def parse_origin(html, status=200):
    text = html.lower()
    if status == 423 or any(x in text for x in ('vpn detected', 'вы используете vpn')):
        return {'status': 'NEEDS_HUMAN', 'reason': 'aggregator_network_restricted'}
    if status in (404, 410):
        return {'status': 'SKIPPED', 'reason': 'aggregator_advert_unavailable'}
    if status != 200:
        return {'status': 'NEEDS_CONFIRMATION', 'reason': 'aggregator_http_error', 'detail': str(status)}
    if any(x in text for x in ('verify you are human', 'проверка безопасности', 'cf-turnstile')):
        return {'status': 'NEEDS_HUMAN', 'reason': 'aggregator_security_challenge'}
    parser = _VacancyLinks()
    parser.feed(html)
    if len(parser.ids) != 1:
        return {'status': 'NEEDS_CONFIRMATION', 'reason': 'aggregator_origin_ambiguous' if parser.ids
                else 'aggregator_origin_not_found'}
    return {'origin_url': 'https://hh.ru/vacancy/' + next(iter(parser.ids))}


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def direct_hh_origin(lead):
    """Use only an explicit, unambiguous HH vacancy URL already present in lead metadata."""
    ids = set()
    for key in ("origin_url", "original_url", "employer_url", "description", "apply_url"):
        value = lead.get(key)
        if not isinstance(value, str):
            continue
        for match in re.finditer(r"https://(?:[a-z0-9-]+\\.)?hh\\.ru/vacancy/(\\d+)(?!\\d)", value, re.I):
            ids.add(match.group(1))
    return "https://hh.ru/vacancy/" + next(iter(ids)) if len(ids) == 1 else None


def apply_origin(lead, proposal, hh_apply):
    """Use the existing authenticated HH handler, including its duplicate check."""
    origin = direct_hh_origin(lead)
    result = {'origin_url': origin} if origin else resolve_gorodrabot(str(lead.get('apply_url') or ''))
    origin = result.get('origin_url')
    if not origin:
        return {**result, 'apply_url': lead.get('apply_url')}
    original_lead = {**lead, 'source': 'hh', 'url': origin}
    original_lead.pop('apply_url', None)
    return {**hh_apply(original_lead, proposal), 'origin_url': origin}


def resolve_gorodrabot(url):
    global _GORODRABOT_RATE_LIMITED
    if not is_gorodrabot_advert(url):
        return {'status': 'SKIPPED', 'reason': 'unsupported_aggregator_url'}
    if _GORODRABOT_RATE_LIMITED:
        return {'status': 'NEEDS_CONFIRMATION', 'reason': 'aggregator_rate_limited', 'detail': 'HTTP 429 earlier in this run'}
    request = Request(url, headers={'User-Agent': 'Mozilla/5.0', 'Accept': 'text/html'})
    try:
        response = build_opener(_NoRedirect).open(request, timeout=20)
    except HTTPError as exc:
        response = exc
    except (URLError, TimeoutError, OSError):
        return {'status': 'NEEDS_CONFIRMATION', 'reason': 'aggregator_network_error'}
    with response:
        if response.status == 429:
            _GORODRABOT_RATE_LIMITED = True
            return {'status': 'NEEDS_CONFIRMATION', 'reason': 'aggregator_rate_limited', 'detail': 'HTTP 429'}
        data = response.read(2 * 1024 * 1024 + 1)
        if len(data) > 2 * 1024 * 1024:
            return {'status': 'NEEDS_CONFIRMATION', 'reason': 'aggregator_page_too_large'}
        encoding = response.headers.get_content_charset() or 'utf-8'
        try:
            html = data.decode(encoding, errors='replace')
        except LookupError:
            html = data.decode('utf-8', errors='replace')
        return parse_origin(html, response.status)
