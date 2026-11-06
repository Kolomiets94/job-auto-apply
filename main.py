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
EXCLUDE=("full stack","fullstack","full-stack","vue","angular","react native","react-native","flutter","middle","senior","lead","head of","manager","director")
UA={"User-Agent":"Mozilla/5.0 (compatible; JobFreelanceHunter/1.2; vacancy-feed)"}


class HHAccessUnavailable(RuntimeError):
    """Public HH vacancy feed is unavailable."""


def salary_ok(v):
    """Keep vacancies with explicit RUB salary in the configured 20k-80k band."""
    if is_placement(v.get("name")):
        return placement_is_paid({**v, "title": v.get("name"), "description": " ".join(str(x or "") for x in (v.get("snippet") or {}).values())})
    salary = v.get("salary")
    if not salary:
        return True

    currency = str(salary.get("currency") or "").upper()
    if currency not in ("RUR", "RUB"):
        return True

    minimum = int(os.getenv("HH_MIN_SALARY_RUB", "20000"))
    maximum = int(os.getenv("HH_MAX_SALARY_RUB", "80000"))
    salary_from = salary.get("from")
    salary_to = salary.get("to")
    if isinstance(salary_from, (int, float)) and salary_from < minimum:
        return False
    if isinstance(salary_to, (int, float)) and salary_to > maximum:
        return False
    amount = salary_from if isinstance(salary_from, (int, float)) else salary_to
    if isinstance(amount, (int, float)):
        return minimum <= amount <= maximum
    return True


def workplace_ok(v):
    """HH RSS query is explicitly restricted to remote vacancies."""
    area = str((v.get("area") or {}).get("name") or v.get("location") or "").lower()
    schedule = str((v.get("schedule") or {}).get("name") or v.get("schedule") or "").lower()
    local = any(x in area for x in ("екатеринбург", "yekaterinburg", "ekaterinburg"))
    remote = any(x in schedule for x in ("удален", "удалён", "дистанцион", "remote"))
    return local or remote


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
        })

    # Avoid hammering HH while iterating over the configured keyword list.
    time.sleep(float(os.getenv("HH_RSS_REQUEST_DELAY", "1")))
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

