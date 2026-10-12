"""Extract explicitly labelled application links from vacancy descriptions."""
import re
from html.parser import HTMLParser
from urllib.parse import urlsplit, urljoin, unquote


def hh_vacancy_url(url):
    try:
        parts = urlsplit(str(url or ''))
        host = (parts.hostname or '').lower()
        match = re.fullmatch(r'/vacancy/(\d+)/?', parts.path)
        if (parts.scheme == 'https' and (host == 'hh.ru' or host.endswith('.hh.ru'))
                and not parts.username and not parts.password and parts.port in (None, 443) and match):
            return 'https://hh.ru/vacancy/' + match.group(1)
    except ValueError:
        pass
    return None


class _ApplyLinks(HTMLParser):
    def __init__(self):
        super().__init__()
        self.href = None
        self.label = []
        self.links = []

    def handle_starttag(self, tag, attrs):
        if tag == 'a':
            self.href = dict(attrs).get('href')
            self.label = []

    def handle_data(self, data):
        if self.href:
            self.label.append(data)

    def handle_endtag(self, tag):
        if tag == 'a' and self.href:
            label = ' '.join(self.label).lower()
            if re.search(r'\b(?:apply|application|send (?:your )?(?:cv|resume))\b|отклик|отправ(?:ьте|ить) резюме', label):
                self.links.append(self.href)
            self.href = None
            self.label = []


def application_link(description, source_url):
    """Require a single explicit destination; do not guess from company contacts."""
    parser = _ApplyLinks()
    parser.feed(str(description or ''))
    destinations = set()
    for href in parser.links:
        url = urljoin(source_url, href)
        try:
            parts = urlsplit(url)
            if parts.scheme == 'mailto':
                address = unquote(parts.path)
                if re.fullmatch(r'[^\s@,;<>]+@[^\s@,;<>]+\.[^\s@,;<>]+', address):
                    destinations.add('mailto:' + address)
            elif (parts.scheme == 'https' and parts.hostname and not parts.username
                  and not parts.password and parts.port in (None, 443)):
                destinations.add(hh_vacancy_url(url) or url)
        except ValueError:
            continue
    return next(iter(destinations)) if len(destinations) == 1 else None
