"""Read GorodRabot adverts and resolve a single original HH vacancy.

This reader never sends candidate data or submits a form.
"""
import re
import time
from html.parser import HTMLParser
from urllib.parse import urlsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler
from urllib.error import HTTPError, URLError

# Space requests out and stop after a bounded 429 retry sequence.
_GORODRABOT_RATE_LIMITED = False
_LAST_REQUEST_AT = None
_RETRY_DELAYS = (60, 120, 240)
_MIN_INTERVAL_SECONDS = 5
_AGGREGATOR_REQUESTS = 0
_FIRST_429 = None
_DEFERRED_ADVERTS = 0


def reset_origin_diagnostics():
    global _GORODRABOT_RATE_LIMITED, _LAST_REQUEST_AT
    global _AGGREGATOR_REQUESTS, _FIRST_429, _DEFERRED_ADVERTS
    _GORODRABOT_RATE_LIMITED = False
    _LAST_REQUEST_AT = None
    _AGGREGATOR_REQUESTS = 0
    _FIRST_429 = None
    _DEFERRED_ADVERTS = 0


def origin_diagnostics():
    return {
        'origin_requests': _AGGREGATOR_REQUESTS,
        'first_429': dict(_FIRST_429) if _FIRST_429 else None,
        'deferred_adverts': _DEFERRED_ADVERTS,
    }


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
        for match in re.finditer(r"https://(?:[a-z0-9-]+\.)?hh\.ru/vacancy/(\d+)(?!\d)", value, re.I):
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


def _paced_open(request):
    """At most one origin request every five seconds in this worker."""
    global _LAST_REQUEST_AT, _AGGREGATOR_REQUESTS
    now = time.monotonic()
    if _LAST_REQUEST_AT is not None:
        remaining = _MIN_INTERVAL_SECONDS - (now - _LAST_REQUEST_AT)
        if remaining > 0:
            time.sleep(remaining)
    _LAST_REQUEST_AT = time.monotonic()
    _AGGREGATOR_REQUESTS += 1
    try:
        return build_opener(_NoRedirect).open(request, timeout=20)
    except HTTPError as exc:
        return exc


def resolve_gorodrabot(url):
    global _GORODRABOT_RATE_LIMITED, _FIRST_429, _DEFERRED_ADVERTS
    if not is_gorodrabot_advert(url):
        return {'status': 'SKIPPED', 'reason': 'unsupported_aggregator_url'}
    if _GORODRABOT_RATE_LIMITED:
        _DEFERRED_ADVERTS += 1
        return {'status': 'NEEDS_CONFIRMATION', 'reason': 'aggregator_rate_limited',
                'detail': 'HTTP 429 after bounded retries earlier in this run'}
    request = Request(url, headers={'User-Agent': 'Mozilla/5.0', 'Accept': 'text/html'})
    for attempt in range(len(_RETRY_DELAYS) + 1):
        try:
            response = _paced_open(request)
        except (URLError, TimeoutError, OSError):
            return {'status': 'NEEDS_CONFIRMATION', 'reason': 'aggregator_network_error'}
        with response:
            if response.status == 429:
                if _FIRST_429 is None:
                    _FIRST_429 = {'advert_path': urlsplit(url).path,
                                  'request_index': _AGGREGATOR_REQUESTS}
                if attempt < len(_RETRY_DELAYS):
                    time.sleep(_RETRY_DELAYS[attempt])
                    continue
                _GORODRABOT_RATE_LIMITED = True
                return {'status': 'NEEDS_CONFIRMATION', 'reason': 'aggregator_rate_limited',
                        'detail': 'HTTP 429 after 4 spaced attempts'}
            data = response.read(2 * 1024 * 1024 + 1)
            if len(data) > 2 * 1024 * 1024:
                return {'status': 'NEEDS_CONFIRMATION', 'reason': 'aggregator_page_too_large'}
            encoding = response.headers.get_content_charset() or 'utf-8'
            try:
                html = data.decode(encoding, errors='replace')
            except LookupError:
                html = data.decode('utf-8', errors='replace')
            return parse_origin(html, response.status)
