"""Public job sources. Discovery and delivery capabilities stay separate."""
import html
import re
from urllib.parse import urljoin
from xml.etree import ElementTree as ET
import requests
import os

UA = {'User-Agent': 'Mozilla/5.0 (compatible; JobFreelanceHunter/3.0)'}


def clean(value):
    return re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]+>', ' ', str(value or '')))).strip()


def response(url, **params):
    r = requests.get(url, params=params or None, headers=UA, timeout=20)
    r.raise_for_status()
    return r



def explicit_application_email(description):
    """Extract only explicit application addresses, not general company contacts."""
    raw = html.unescape(str(description or ""))
    mailto_links = re.findall(
        r"""href\s*=\s*["']mailto:([^?"'\s<>]+)[^"']*["'][^>]*>(.*?)</a>""",
        raw, flags=re.I | re.S,
    )
    for address, label in mailto_links:
        label_text = clean(label)
        is_apply = re.search(
            r"\b(apply|application|send (?:your )?(?:cv|resume)|submit (?:your )?(?:cv|resume))\b|отклик|отправить резюме",
            label_text, re.I,
        )
        if is_apply and re.fullmatch(r"[^\s@,;<>]+@[^\s@,;<>]+\.[^\s@,;<>]+", address):
            return address
    plain = clean(raw)
    match = re.search(
        r"(?:apply (?:by |via )?(?:email(?:ing)?|to)|send (?:your )?(?:cv|resume) to|отправ(?:ьте|ить) резюме (?:на|по адресу))\s*:?\s*([\w.+-]+@[\w.-]+\.[A-Za-z]{2,})",
        plain, re.I,
    )
    return match.group(1) if match else None


def job(source, title, url, description='', **extra):
    from application_links import application_link
    if 'apply_email' not in extra:
        extra['apply_email'] = explicit_application_email(description)
    if not extra.get('apply_url'):
        destination = application_link(description, url)
        if destination:
            extra['apply_url'] = destination
    return {'source': source, 'title': clean(title), 'url': url,
            'description': clean(description), 'remote': True, **extra}


JOBICY_SEARCH_TAGS = ('react', 'frontend', 'typescript', 'html css')
REMOTIVE_SEARCH_TERMS = ('react', 'frontend')


def jobicy():
    """Search current Jobicy listings by relevant frontend keywords, not the global feed."""
    out, seen = [], set()
    for tag in JOBICY_SEARCH_TAGS:
        data = response('https://jobicy.com/api/jobs', count=100, tag=tag).json()
        for v in data.get('jobs', []):
            url = v.get('url')
            if not url or url in seen:
                continue
            seen.add(url)
            out.append(job(
                'jobicy', v.get('jobTitle'), url,
                v.get('jobDescription') or v.get('jobExcerpt'),
                company=v.get('companyName'), location=v.get('jobGeo'),
                published=v.get('pubDate'), experience=v.get('jobLevel'),
                job_type=v.get('jobType'), language='en',
                salary={'from': v.get('salaryMin'), 'to': v.get('salaryMax'),
                        'currency': v.get('salaryCurrency'), 'period': v.get('salaryPeriod')},
            ))
    return out


def remotive():
    """Use Remotive's documented title/description search instead of its unfiltered feed."""
    out, seen = [], set()
    for term in REMOTIVE_SEARCH_TERMS:
        data = response(
            'https://remotive.com/api/remote-jobs', search=term, limit=100
        ).json()
        for v in data.get('jobs', []):
            url = v.get('url')
            if not url or url in seen:
                continue
            seen.add(url)
            out.append(job(
                'remotive', v.get('title'), url, v.get('description'),
                company=v.get('company_name'), location=v.get('candidate_required_location'),
                published=v.get('publication_date'), language='en',
            ))
    return out


def arbeitnow():
    data = response('https://www.arbeitnow.com/api/job-board-api').json()
    return [job('arbeitnow', v.get('title'), v.get('url'), v.get('description'),
                company=v.get('company_name'), location=v.get('location'), language='en')
            for v in data.get('data', []) if v.get('remote') and v.get('url')]


def feed(source, url, language):
    root = ET.fromstring(response(url).content)
    out = []
    for item in root.findall('.//item'):
        link = item.findtext('link') or ''
        desc = item.findtext('description') or ''
        # Habr RSS includes onsite positions; keep only explicitly remote ones.
        text = clean(desc).lower()
        if source == 'habr_career' and not any(s in text for s in ('удалён', 'удален', 'remote')):
            continue
        if link:
            out.append(job(source, item.findtext('title'), link, desc,
                           published=item.findtext('pubDate'), language=language))
    return out


def habr_career():
    return feed('habr_career', 'https://career.habr.com/vacancies/rss', 'ru')


def weworkremotely():
    return feed('weworkremotely', 'https://weworkremotely.com/remote-jobs.rss', 'en')


def trudvsem():
    out = []
    for query in ('junior frontend', 'верстальщик', 'junior тестировщик',
                  'стажер frontend', 'практикант верстальщик', 'стажер тестировщик'):
        data = response('https://opendata.trudvsem.ru/api/v1/vacancies', text=query, limit=100, offset=0).json()
        for wrapper in (data.get('results') or {}).get('vacancies', []):
            v = wrapper.get('vacancy', wrapper)
            desc = ' '.join(str(v.get(k) or '') for k in ('duty', 'requirements', 'requirement', 'schedule', 'employment'))
            if not any(s in clean(desc).lower() for s in ('удалён', 'удален', 'дистанцион', 'remote')):
                continue
            url = v.get('vac_url')
            if not url:
                continue
            out.append(job('trudvsem', v.get('job-name'), url, desc,
                           company=(v.get('company') or {}).get('name'), language='ru',
                           apply_email=next((c.get('contact_value') for c in v.get('contact_list', [])
                                             if c.get('contact_type') == 'Эл. почта'), None),
                           salary={'from': v.get('salary_min'), 'to': v.get('salary_max'), 'currency': 'RUB'}))
    return out


def public_listing(source, url, link_pattern, language='ru'):
    """Collect public vacancy links from HTML, without assuming application support."""
    page = response(url).text
    out, seen = [], set()
    for href, label in re.findall(link_pattern, page, re.I | re.S):
        absolute = urljoin(url, html.unescape(href))
        title = clean(label)
        if not title or absolute in seen:
            continue
        seen.add(absolute)
        out.append(job(source, title, absolute, title, language=language))
    return out


def _vacancy_listing(source, url, language='ru'):
    """Parse links with stable HTML attributes instead of over-escaped patterns."""
    from html.parser import HTMLParser

    class Links(HTMLParser):
        def __init__(self):
            super().__init__()
            self.href = None
            self.parts = []
            self.items = []

        def handle_starttag(self, tag, attrs):
            if tag == 'a':
                self.href = dict(attrs).get('href')
                self.parts = []

        def handle_data(self, data):
            if self.href:
                self.parts.append(data)

        def handle_endtag(self, tag):
            if tag == 'a' and self.href:
                self.items.append((self.href, ' '.join(self.parts)))
                self.href = None
                self.parts = []

    parser = Links()
    parser.feed(response(url).text)
    out, seen = [], set()
    for href, label in parser.items:
        absolute = urljoin(url, html.unescape(href))
        path = __import__('urllib.parse', fromlist=['urlsplit']).urlsplit(absolute).path
        if not re.search(r'/vacanc(?:y|ies)/|/vacancy/|/vacancies/', path, re.I):
            continue
        title = clean(label)
        if not title or absolute in seen:
            continue
        seen.add(absolute)
        out.append(job(source, title, absolute, title, language=language))
    return out


def geekjob():
    return _vacancy_listing('geekjob', 'https://geekjob.ru/vacancies')


def getmatch():
    return _vacancy_listing('getmatch', 'https://getmatch.ru/vacancies/js_frontend/remote/junior')


def zarplata():
    return _vacancy_listing('zarplata', 'https://zarplata.ru/vacancies/junior-developer/udalennaya_rabota')


REMOTE_JOB_RU_QUERIES = (
    'junior frontend', 'junior react', 'верстальщик html css', 'junior qa',
    'стажер frontend', 'frontend intern', 'стажер верстальщик',
    'практикант верстальщик', 'стажер тестировщик', 'QA intern',
    # Broader role-first searches catch listings that omit "junior" from the title.
    'React Frontend разработчик', 'Frontend-разработчик',
    'HTML CSS верстальщик',
)
REMOTE_JOB_RU_PAGES = {
    'React Frontend разработчик': 3,
    'Frontend-разработчик': 2,
}


def remote_job_ru():
    out = []
    seen = set()
    from html.parser import HTMLParser

    class Links(HTMLParser):
        def __init__(self):
            super().__init__()
            self.href = None
            self.parts = []
            self.items = []

        def handle_starttag(self, tag, attrs):
            if tag == 'a':
                self.href = dict(attrs).get('href')
                self.parts = []

        def handle_data(self, data):
            if self.href:
                self.parts.append(data)

        def handle_endtag(self, tag):
            if tag == 'a' and self.href:
                self.items.append((self.href, ' '.join(self.parts)))
                self.href = None
                self.parts = []

    url = 'https://remote-job.ru/search'
    for query in REMOTE_JOB_RU_QUERIES:
        for page_number in range(1, REMOTE_JOB_RU_PAGES.get(query, 1) + 1):
            params = {'search[query]': query, 'search[searchType]': 'vacancy'}
            if page_number > 1:
                params['page'] = page_number
            page = response(url, **params).text
            parser = Links()
            parser.feed(page)
            for href, label in parser.items:
                absolute = urljoin(url, html.unescape(href))
                parts = __import__('urllib.parse', fromlist=['urlsplit']).urlsplit(absolute)
                if (parts.scheme != 'https' or parts.hostname not in ('remote-job.ru', 'www.remote-job.ru')
                        or not re.search(r'/vacancy/show/\\d+', parts.path, re.I)):
                    continue
                title = clean(label)
                if title and absolute not in seen:
                    seen.add(absolute)
                    out.append(job('remote_job_ru', title, absolute, title, language='ru'))
                if len(out) >= 120:
                    return out
    return out

def superjob():
    """Official SuperJob API when its app key is configured."""
    key = os.getenv('SUPERJOB_API_KEY', '').strip()
    if not key:
        return []
    r = requests.get(
        'https://api.superjob.ru/2.0/vacancies/',
        headers={**UA, 'X-Api-App-Id': key},
        params={'keyword': 'junior frontend react', 'count': 100, 'page': 0},
        timeout=20,
    )
    r.raise_for_status()
    out = []
    for v in r.json().get('objects', []):
        if not v.get('is_archive') and v.get('link'):
            out.append(job(
                'superjob', v.get('profession'), v.get('link'),
                v.get('candidat') or '', company=(v.get('client') or {}).get('title'),
                language='ru',
                salary={'from': v.get('payment_from'), 'to': v.get('payment_to'), 'currency': 'RUB'},
            ))
    return out


def jooble():
    """Official Jooble API when a key is configured."""
    key = os.getenv('JOOBLE_API_KEY', '').strip()
    if not key:
        return []
    r = requests.post(
        f'https://jooble.org/api/{key}',
        headers={'Content-Type': 'application/json', **UA},
        json={'keywords': 'junior frontend react remote', 'location': ''},
        timeout=20,
    )
    r.raise_for_status()
    out = []
    for v in r.json().get('jobs', []):
        if v.get('link'):
            out.append(job(
                'jooble', v.get('title'), v.get('link'), v.get('snippet') or '',
                company=v.get('company'), location=v.get('location'), language='en',
                salary=v.get('salary'),
            ))
    return out


JOB_COLLECTORS = (('habr_career', habr_career), ('trudvsem', trudvsem),
                  ('jobicy', jobicy), ('remotive', remotive),
                  ('weworkremotely', weworkremotely), ('arbeitnow', arbeitnow),
                  ('geekjob', geekjob), ('getmatch', getmatch), ('zarplata', zarplata), ('remote_job_ru', remote_job_ru),
                  ('superjob', superjob), ('jooble', jooble))

