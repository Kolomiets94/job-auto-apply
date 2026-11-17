import re, json, hashlib, os
from datetime import datetime, timezone
import requests
from freelance_sources import collect_freelance
from entry_level import is_placement, placement_is_paid

HH_RSS_URL="https://hh.ru/search/vacancy/rss"
QUERIES=[
    ("frontend","junior frontend"),
    ("frontend","junior React"),
    ("frontend","React разработчик"),
    ("frontend","React TypeScript"),
    ("frontend","младший React разработчик"),
    ("frontend","frontend React"),
    ("frontend","React frontend developer"),
    ("frontend","junior фронтенд"),
    ("frontend","junior JavaScript"),
    ("frontend","младший frontend"),
    ("layout","junior верстальщик"),
    ("layout","junior HTML CSS"),
    ("layout","младший верстальщик"),
    ("layout","junior HTML"),
]

HYBRID_QUERIES=[
    ("frontend","junior frontend"),
    ("frontend","junior React"),
    ("frontend","React TypeScript"),
    ("frontend","junior JavaScript"),
    ("layout","junior верстальщик"),
    ("layout","junior HTML CSS"),
]
EXCLUDE=("full stack","fullstack","full-stack","vue","angular","react native","react-native","flutter","middle","senior","lead","head of","manager","director")
UA={"User-Agent":"Mozilla/5.0 (compatible; JobFreelanceHunter/1.2; vacancy-feed)"}


class HHAccessUnavailable(RuntimeError):
    """Public HH vacancy feed is unavailable."""


def salary_ok(v):
    """Reject explicit RUB salaries below the configured floor; do not cap high salaries."""
    if is_placement(v.get("name")):
        return placement_is_paid({**v, "title": v.get("name"), "description": " ".join(str(x or "") for x in (v.get("snippet") or {}).values())})
    salary = v.get("salary")
    if not salary:
        return True

    currency = str(salary.get("currency") or "").upper()
    if currency not in ("RUR", "RUB"):
        return True

    minimum = int(os.getenv("HH_MIN_SALARY_RUB", "60000"))
    salary_from = salary.get("from")
    salary_to = salary.get("to")
    if isinstance(salary_from, (int, float)):
        return salary_from >= minimum
    if isinstance(salary_to, (int, float)):
        return salary_to >= minimum
    return True


def _format_text(value):
    if isinstance(value, dict):
        return " ".join(str(value.get(key) or "") for key in ("id", "name", "title", "value"))
    if isinstance(value, (list, tuple, set)):
        return " ".join(_format_text(item) for item in value)
    return str(value or "")


def workplace_ok(v):
    """Allow remote everywhere; hybrid only in Yekaterinburg; never office."""
    area = str((v.get("area") or {}).get("name") or v.get("location") or "").lower()
    local = any(x in area for x in ("екатеринбург", "yekaterinburg", "ekaterinburg"))
    title = str(v.get("name") or v.get("title") or "").lower()
    if re.search(r"\boffice\b|офис", title):
        return False

    remote = r"\bremote\b|удал[её]н|дистанцион"
    hybrid = r"\bhybrid\b|гибрид"
    office = (
        r"\bon[\s_-]?site\b|\bin[\s_-]?office\b|\boffice[\s-]?(?:only|based)\b|"
        r"работа\s+в\s+офисе|только\s+в\s+офисе|офисн(?:ый|ая|ое)\s+формат|"
        r"на\s+месте\s+работодателя"
    )

    explicit_mode = _format_text(v.get("work_mode")).lower()
    if explicit_mode:
        if re.search(hybrid, explicit_mode):
            return local
        if re.search(office, explicit_mode) or re.search(
            r"\b(?:on[_ -]?site|onsite|office)\b", explicit_mode
        ):
            return False
        if re.search(remote, explicit_mode):
            return True

    formats = " ".join(
        _format_text(v.get(key))
        for key in ("work_format", "work_formats", "workplace_type", "workplace")
    ).lower()
    if formats:
        if re.search(hybrid, formats):
            return local
        if re.search(office, formats) or re.search(
            r"\b(?:on[_ -]?site|onsite|office)\b", formats
        ):
            return False
        if re.search(remote, formats):
            return True

    schedule = _format_text(v.get("schedule")).lower()
    details = " ".join(str(x or "") for x in (v.get("snippet") or {}).values()).lower()
    text = " ".join((title, schedule, details))
    if re.search(hybrid, text):
        return local
    if re.search(office, text):
        return False
    if re.search(remote, text):
        return True
    return False


def ok(v):
    text=((v.get("name") or "")+" "+" ".join(str(x or "") for x in (v.get("snippet") or {}).values())).lower()
    title = (v.get("name") or "").lower()
    level_terms = ("middle", "senior", "lead", "head of", "manager", "director")
    if any(x in title for x in level_terms): return False
    if any(x in text for x in EXCLUDE if x not in level_terms): return False
    if not salary_ok(v): return False
    if not workplace_ok(v): return False
    return True


def _hh_rss_text(value):
    import html
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", str(value or "")))).strip()


def _hh_rss_salary(description):
    match = re.search(
        r"Предполагаемый уровень месячного дохода:\s*(.*?)(?:$|\n)",
        description, re.I,
    )
    value = (match.group(1) if match else "").replace("\xa0", " ").strip()
    if not value or "не указан" in value.lower():
        return None
    currency = "RUR" if re.search(r"₽|руб", value, re.I) else (
        "USD" if "$" in value else ("EUR" if "€" in value else None)
    )
    if not currency:
        return None
    nums = [int(x.replace(" ", "")) for x in re.findall(r"\d[\d\s]*", value)]
    if not nums:
        return None
    return {
        "from": nums[0],
        "to": nums[1] if len(nums) > 1 else None,
        "currency": currency,
    }


def hh_search(tag, q):
    """Collect public remote HH listings from the site's RSS search feed."""
    import time
    import xml.etree.ElementTree as ET

    params = {"text": q, "schedule": "remote"}
    for attempt in range(3):
        try:
            response = requests.get(
                HH_RSS_URL, params=params, headers=UA, timeout=25,
            )
        except (requests.Timeout, requests.ConnectionError) as exc:
            if attempt == 2:
                raise HHAccessUnavailable("HH RSS network unavailable") from exc
            time.sleep(2 ** attempt)
            continue

        if response.status_code == 429 or 500 <= response.status_code < 600:
            if attempt == 2:
                raise HHAccessUnavailable(f"HH RSS HTTP {response.status_code} after retries")
            retry_after = response.headers.get("Retry-After", "")
            try:
                delay = min(30, max(1, float(retry_after)))
            except (TypeError, ValueError):
                delay = 2 ** attempt
            time.sleep(delay)
            continue
        if response.status_code in (401, 403):
            raise HHAccessUnavailable(f"HH RSS HTTP {response.status_code}")
        response.raise_for_status()
        break

    try:
        root = ET.fromstring(response.content)
    except ET.ParseError as exc:
        raise HHAccessUnavailable("HH RSS returned invalid XML") from exc

    results = []
    for item in root.findall(".//item"):
        title = _hh_rss_text(item.findtext("title"))
        url = (item.findtext("link") or "").strip()
        description = _hh_rss_text(item.findtext("description"))
        published = (item.findtext("pubDate") or "").strip()
        if not title or not url.startswith("https://hh.ru/vacancy/"):
            continue

        company_match = re.search(r"Вакансия компании:\s*(.*?)(?=\s+Создана:|\s+Регион:|$)", description, re.I)
        location_match = re.search(r"Регион:\s*(.*?)(?=\s+Предполагаемый уровень|$)", description, re.I)
        salary = _hh_rss_salary(description)
        vacancy = {
            "name": title,
            "snippet": {"description": description},
            "salary": salary,
            "location": location_match.group(1).strip() if location_match else "",
            "schedule": {"name": "Удаленная работа"},
        }
        if not ok(vacancy):
            continue
        results.append({
            "source": "hh",
            "category": tag,
            "title": title,
            "company": company_match.group(1).strip() if company_match else None,
            "url": url,
            "published": published,
            "salary": salary,
            "description": description,
            "experience": None,
            "schedule": "Удаленная работа",
            "location": vacancy["location"],
            "work_mode": "REMOTE",
        })

    # Avoid hammering HH while iterating over the configured keyword list.
    time.sleep(float(os.getenv("HH_RSS_REQUEST_DELAY", "1")))
    return results


def hh_yekaterinburg_area_id():
    """Resolve the current HH area ID for Yekaterinburg; allow an explicit env override."""
    global _HH_YEKATERINBURG_AREA_ID
    configured = os.getenv("HH_YEKATERINBURG_AREA_ID", "").strip()
    if configured:
        return configured
    if _HH_YEKATERINBURG_AREA_ID:
        return _HH_YEKATERINBURG_AREA_ID
    response = requests.get("https://api.hh.ru/areas/113", headers=UA, timeout=20)
    response.raise_for_status()
    stack = [response.json()]
    while stack:
        area = stack.pop()
        if str(area.get("name") or "").strip().casefold() == "екатеринбург":
            _HH_YEKATERINBURG_AREA_ID = str(area.get("id"))
            return _HH_YEKATERINBURG_AREA_ID
        stack.extend(area.get("areas") or [])
    raise HHAccessUnavailable("Could not resolve Yekaterinburg area ID from HH directory")


_HH_YEKATERINBURG_AREA_ID = None


def hh_hybrid_search(tag, q):
    """Use HH's vacancy API to search hybrid vacancies only in Yekaterinburg."""
    import time

    area_id = hh_yekaterinburg_area_id()
    params = {
        "text": q,
        "area": area_id,
        "work_format": "HYBRID",
        "per_page": 50,
        "page": 0,
        "order_by": "publication_time",
    }
    for attempt in range(3):
        try:
            response = requests.get(
                "https://api.hh.ru/vacancies", params=params, headers=UA, timeout=25,
            )
        except (requests.Timeout, requests.ConnectionError) as exc:
            if attempt == 2:
                raise HHAccessUnavailable("HH API network unavailable") from exc
            time.sleep(2 ** attempt)
            continue
        if response.status_code in (401, 403):
            raise HHAccessUnavailable(f"HH API HTTP {response.status_code}")
        if response.status_code == 429 or 500 <= response.status_code < 600:
            if attempt == 2:
                raise HHAccessUnavailable(f"HH API HTTP {response.status_code} after retries")
            retry_after = response.headers.get("Retry-After", "")
            try:
                delay = min(30, max(1, float(retry_after)))
            except (TypeError, ValueError):
                delay = 2 ** attempt
            time.sleep(delay)
            continue
        response.raise_for_status()
        break

    results = []
    for vacancy in response.json().get("items", []):
        lead = {
            "source": "hh",
            "category": tag,
            "title": vacancy.get("name"),
            "company": (vacancy.get("employer") or {}).get("name"),
            "url": vacancy.get("alternate_url"),
            "published": vacancy.get("published_at"),
            "salary": vacancy.get("salary"),
            "description": " ".join(str(x or "") for x in (vacancy.get("snippet") or {}).values()),
            "experience": (vacancy.get("experience") or {}).get("name"),
            "location": (vacancy.get("area") or {}).get("name"),
            "work_format": vacancy.get("work_format") or [],
            "schedule": vacancy.get("schedule") or {},
            "work_mode": "HYBRID",
        }
        if ok({**lead, "name": lead["title"], "snippet": {"description": lead["description"]}}):
            results.append(lead)
    return results


def remoteok():
    try:
        data=requests.get("https://remoteok.com/api",headers=UA,timeout=20).json(); out=[]
        for v in data[1:]:
            text=((v.get("position") or "")+" "+(v.get("description") or "")).lower()
            if any(x in text for x in ("react","typescript","javascript","frontend","front-end","html","css")) and not any(x in text for x in EXCLUDE):
                out.append({"source":"remoteok","category":"frontend","title":v.get("position"),"company":v.get("company"),"url":v.get("url"),"apply_url":v.get("apply_url"),"apply_email":v.get("apply_email"),"description":v.get("description"),"location":v.get("location"),"salary_min":v.get("salary_min"),"salary_max":v.get("salary_max"),"published":v.get("date")})
        return out[:50]
    except Exception:return []


def collect():
    jobs=[]
    for tag,q in QUERIES:
        try:jobs+=hh_search(tag,q)
        except Exception:pass
    for tag,q in HYBRID_QUERIES:
        try:jobs+=hh_hybrid_search(tag,q)
        except Exception:pass
    jobs+=remoteok()
    try: jobs+=collect_freelance()
    except Exception: pass
    seen=set(); unique=[]
    for j in jobs:
        k=hashlib.sha256((j.get("url") or json.dumps(j,sort_keys=True)).encode()).hexdigest()
        if k not in seen:seen.add(k);unique.append(j)
    unique.sort(key=lambda x:x.get("published") or "",reverse=True)
    return {"generated_at":datetime.now(timezone.utc).isoformat(),"count":len(unique),"items":unique[:100]}


if __name__=="__main__":print(json.dumps(collect(),ensure_ascii=False,indent=2))

