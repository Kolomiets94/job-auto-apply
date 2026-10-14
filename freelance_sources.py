"""Public freelance feeds and listings.

Uses public feeds/listings only: no login, CAPTCHA handling, or private endpoints.
Failures are isolated so one source never stops the hunter.
"""
import html, re
from datetime import datetime, timezone
from urllib.parse import urljoin
from xml.etree import ElementTree as ET
import requests

UA={"User-Agent":"Mozilla/5.0 (compatible; JobFreelanceHunter/2.2; +https://github.com/Kolomiets94/-JobAutoApply)"}
FEEDS=(
    ("fl_ru","https://www.fl.ru/rss/all.xml"),
)
PPH_URLS=(
    "https://www.peopleperhour.com/freelance-react-js-jobs?sort=latest",
    "https://www.peopleperhour.com/freelance-front-end-developer-jobs?sort=latest",
)
WEBLANCER_CATEGORIES=(
    "https://www.weblancer.net/freelance/dorabotka-saitov/",
    "https://www.weblancer.net/freelance/sozdanie-saitov/",
    "https://www.weblancer.net/freelance/html/",
    "https://www.weblancer.net/freelance/css/",
    "https://www.weblancer.net/freelance/javascript/",
)
FREELANCER_API="https://www.freelancer.com/api/projects/0.1/projects/active/"

def _clean(s):
    return re.sub(r"\s+"," ",html.unescape(re.sub(r"<[^>]+>"," ",s or ""))).strip()

def _entries(xml, source):
    root=ET.fromstring(xml)
    out=[]
    for item in root.findall(".//item"):
        title=_clean(item.findtext("title"))
        desc=_clean(item.findtext("description"))
        link=(item.findtext("link") or "").strip()
        pub=(item.findtext("pubDate") or "").strip()
        if link and title:
            lead={"source":source,"category":"freelance","title":title,
                  "description":desc[:5000],"url":link,"published":pub}
            if source=="fl_ru":
                # FL.ru has free-to-apply vacancies and "for everyone" orders.
                # RSS does not expose that flag: never label every listing paid.
                lead["bid_access_unknown"]=True
            out.append(lead)
    return out

def collect_freelance():
    leads=[]
    for source,url in FEEDS:
        try:
            r=requests.get(url,headers=UA,timeout=20)
            r.raise_for_status()
            leads.extend(_entries(r.text,source))
        except Exception as exc:
            print(f"[freelance-feed] {source} failed: {type(exc).__name__}: {exc}", flush=True)
            continue
    print(f"[freelance-feed] total: {len(leads)} leads", flush=True)
    return leads

def _parse_prolinker_markdown(md):
    out=[]
    seen=set()
    # Firecrawl markdown preserves project anchors as [title](absolute-url).
    pattern=r'\[([^\]]+)\]\((https://prolinker\.com/projects/(?!s/)[^)]+)\)'
    matches = list(re.finditer(pattern, md, re.I))
    for index, match in enumerate(matches):
        label, href = match.groups()
        title=_clean(label)
        href=html.unescape(href.strip())
        if not title or href in seen:
            continue
        seen.add(href)
        # Keep nearby listing text so the ranker can see budget/location/technology hints.
        # Never borrow skills from the next listing on a search-results page.
        end = matches[index + 1].start() if index + 1 < len(matches) else len(md)
        context = _clean(md[match.end():min(end, match.end() + 700)])
        out.append({
            "source":"prolinker_firecrawl",
            "category":"freelance",
            "title":title,
            "description":context[:1500],
            "url":href,
            "published":"",
        })
    return out

def collect_prolinker(max_pages=3):
    """Collect direct public pages only. Undated leads cannot enter today's run."""
    base="https://prolinker.com"
    out=[]
    seen=set()
    for page in range(1,max_pages+1):
        url=f"{base}/projects/s/frontend?skills=Frontend&page={page}"
        page_leads=[]
        # Direct page only: no Firecrawl traffic.
        if not page_leads:
            try:
                r=requests.get(url,headers=UA,timeout=25)
                r.raise_for_status()
                hrefs=re.findall(r'href=["\']([^"\']*?/projects/[^"\'#?]+)["\']',r.text,re.I)
                for href in hrefs:
                    absolute=urljoin(base,html.unescape(href))
                    path=absolute.split("prolinker.com",1)[-1]
                    if path.startswith("/projects/s/"):
                        continue
                    slug=path.rstrip("/").rsplit("/",1)[-1]
                    title=_clean(re.sub(r"-[A-Z0-9]{5,}$","",slug,flags=re.I).replace("-"," "))
                    if title:
                        page_leads.append({"source":"prolinker","category":"freelance","title":title,
                                           "description":title,"url":absolute,"published":""})
            except Exception as exc:
                print(f"[prolinker] direct page {page} failed: {type(exc).__name__}: {exc}", flush=True)

        print(f"[prolinker] page {page}: {len(page_leads)} leads", flush=True)
        for lead in page_leads:
            if lead["url"] not in seen:
                seen.add(lead["url"])
                out.append(lead)
    return out


def collect_peopleperhour():
    """Collect public PeoplePerHour frontend project cards. Discovery only; no auto-bidding."""
    out=[]
    seen=set()
    for url in PPH_URLS:
        try:
            r=requests.get(url,headers=UA,timeout=25)
            r.raise_for_status()
            # Public project links use /freelance-jobs/... paths; keep only unique project URLs.
            links=re.findall(r'href=["\'](https?://www\.peopleperhour\.com/freelance-jobs/[^"\'#?]+|/freelance-jobs/[^"\'#?]+)["\']',r.text,re.I)
            for href in links:
                absolute=urljoin("https://www.peopleperhour.com",html.unescape(href))
                if absolute in seen:
                    continue
                seen.add(absolute)
                slug=absolute.rstrip("/").rsplit("/",1)[-1]
                title=_clean(slug.replace("-"," "))
                if title:
                    out.append({"source":"peopleperhour","category":"freelance","title":title,
                                "description":title,"url":absolute,"published":"",
                                "apply_email":None})
        except Exception as exc:
            print(f"[peopleperhour] failed: {type(exc).__name__}: {exc}",flush=True)
    print(f"[peopleperhour] {len(out)} leads",flush=True)
    return out


def _parse_weblancer_cards(page):
    """Use the dated public project cards; an undated card cannot pass today's filter."""
    out = []
    for match in re.finditer(r"<article\b[^>]*>(.*?)</article>", page, re.I | re.S):
        card = match.group(1)
        heading = re.search(r"<h2\b[^>]*>\s*<a\b[^>]*href=[\"']([^\"']+)[\"'][^>]*>(.*?)</a>", card, re.I | re.S)
        date_match = re.search(r"\b(\d{2}\.\d{2}\.\d{4})\b", _clean(card))
        if not heading or not date_match:
            continue
        url = urljoin("https://www.weblancer.net", html.unescape(heading.group(1)))
        if not url.startswith("https://www.weblancer.net/freelance/"):
            continue
        try:
            published = datetime.strptime(date_match.group(1), "%d.%m.%Y").date().isoformat()
        except ValueError:
            continue
        description = re.search(r"<p\b[^>]*>(.*?)</p>", card, re.I | re.S)
        out.append({
            "source": "weblancer", "category": "freelance",
            "title": _clean(heading.group(2)),
            "description": _clean(description.group(1))[:5000] if description else "",
            "url": url, "published": published,
        })
    return out


def collect_weblancer():
    """Public Weblancer category listings; discovery only, with verified card dates."""
    out, seen = [], set()
    for url in WEBLANCER_CATEGORIES:
        try:
            response = requests.get(url, headers=UA, timeout=20)
            response.raise_for_status()
            for lead in _parse_weblancer_cards(response.text):
                if lead["url"] not in seen:
                    seen.add(lead["url"])
                    out.append(lead)
        except (requests.RequestException, ValueError) as exc:
            status = getattr(getattr(exc, "response", None), "status_code", None)
            print(f"[weblancer] {url}: HTTP {status or type(exc).__name__}", flush=True)
            if status in (403, 429):
                break
    print(f"[weblancer] {len(out)} dated leads", flush=True)
    return out


def _parse_freelancer_projects(payload):
    """Parse public active projects without inventing a bid channel or publication date."""
    if payload.get("status") != "success":
        return []
    out = []
    for item in (payload.get("result") or {}).get("projects") or []:
        slug = str(item.get("seo_url") or "")
        timestamp = item.get("submitdate")
        if (item.get("status") != "active" or not slug or
                not re.fullmatch(r"[a-zA-Z0-9/_-]+", slug) or
                not isinstance(timestamp, (int, float))):
            continue
        try:
            published = datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat()
        except (OSError, OverflowError, ValueError):
            continue
        out.append({
            "source": "freelancer_com", "category": "freelance",
            "title": str(item.get("title") or "").strip(),
            "description": str(item.get("description") or item.get("preview_description") or "")[:5000],
            "url": "https://www.freelancer.com/projects/" + slug,
            "published": published, "language": item.get("language"),
            "budget": item.get("budget"),
        })
    return [lead for lead in out if lead["title"]]


def collect_freelancer_com():
    """Official public active-project endpoint; discovery only, no automatic bids."""
    out, seen = [], set()
    for query in ("React", "TypeScript", "HTML CSS"):
        try:
            response = requests.get(
                FREELANCER_API, headers=UA,
                params={"query": query, "limit": 50, "full_description": "true"},
                timeout=20,
            )
            response.raise_for_status()
            for lead in _parse_freelancer_projects(response.json()):
                if lead["url"] not in seen:
                    seen.add(lead["url"])
                    out.append(lead)
        except (requests.RequestException, ValueError) as exc:
            print(f"[freelancer.com] {query}: {type(exc).__name__}", flush=True)
    print(f"[freelancer.com] {len(out)} dated leads", flush=True)
    return out
