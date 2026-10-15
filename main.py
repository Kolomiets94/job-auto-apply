import re, json, hashlib, os
from datetime import datetime, timezone
import requests
from freelance_sources import collect_freelance
from entry_level import is_placement, placement_is_paid

HH_API="https://api.hh.ru/vacancies"
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
    ("qa","junior QA tester"),
    ("qa","manual QA junior"),
    ("qa","junior тестировщик"),
]
EXCLUDE=("full stack","fullstack","full-stack","vue","angular","react native","react-native","flutter","middle","senior","lead","head of","manager","director")
UA={"User-Agent":"JobFreelanceHunter/1.1"}


class HHAccessUnavailable(RuntimeError):
    """Public API is blocked and there is no usable browser search session."""


def salary_ok(v):
    """Keep hh.ru vacancies paying at least the configured RUB floor when salary is explicit.

    Regular vacancies without salary remain eligible. Placements require confirmed
    payment and may pay below the regular-job salary floor.
    """
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


def ok(v):
    text=((v.get("name") or "")+" "+" ".join(str(x or "") for x in (v.get("snippet") or {}).values())).lower()
    title = (v.get("name") or "").lower()
    level_terms = ("middle", "senior", "lead", "head of", "manager", "director")
    # Team descriptions may mention senior colleagues or a team lead.
    # The target vacancy's title determines its advertised seniority.
    if any(x in title for x in level_terms): return False
    if any(x in text for x in EXCLUDE if x not in level_terms): return False
    if not salary_ok(v): return False
    if re.search(r"junior\s*\+|джуниор\s*\+|джун\s*\+", title): return False
    if re.search(r"\b(?:intern|internship|trainee)\b|стаж[её]р|стажиров|практикант", title): return False
    if any(x in title for x in ("офис", "гибрид", "hybrid", "onsite", "on-site")): return False
    return True


def hh_search(tag, q):
    """Search official HH public vacancies API, with bounded retry and safe fallback.

    Never treat a blocked API request as proof that no vacancies exist.
    """
    import time
    items = []
    for page in range(6):
        params = {"text": q, "per_page": 50, "page": page,
                  "order_by": "publication_time", "schedule": "remote"}
        response = None
        for attempt in range(3):
            try:
                response = requests.get(HH_API, params=params, headers=UA, timeout=20)
            except (requests.Timeout, requests.ConnectionError) as exc:
                if attempt == 2:
                    raise HHAccessUnavailable("HH API network unavailable") from exc
                time.sleep(2 ** attempt)
                continue
            if response.status_code in (429, 500, 502, 503, 504):
                if attempt == 2:
                    raise HHAccessUnavailable(
                        f"HH API temporarily unavailable: HTTP {response.status_code}"
                    )
                retry_after = response.headers.get("Retry-After", "")
                delay = min(int(retry_after), 10) if retry_after.isdigit() else 2 ** attempt
                time.sleep(delay)
                continue
            break
        if response.status_code == 403:
            # A web-browser fallback requires a real, authorized HH session.
            # Do not use it without a configured session or bypass challenges.
            if not os.getenv("HH_STORAGE_STATE_JSON"):
                raise HHAccessUnavailable("HH API HTTP 403; authenticated browser session unavailable")
            from hh_web_search import search_hh_web
            try:
                return search_hh_web(tag, q)
            except Exception as exc:
                raise HHAccessUnavailable("HH API HTTP 403; browser fallback unavailable") from exc
        if response.status_code in (401, 407):
            raise HHAccessUnavailable(f"HH API access denied: HTTP {response.status_code}")
        response.raise_for_status()
        payload = response.json()
        items.extend(payload.get("items", []))
        if page >= int(payload.get("pages", 1)) - 1:
            break
    return [{"source": "hh", "category": tag, "title": v["name"],
             "company": (v.get("employer") or {}).get("name"),
             "url": v.get("alternate_url"), "published": v.get("published_at"),
             "salary": v.get("salary"),
             "description": " ".join(str(x or "") for x in (v.get("snippet") or {}).values()),
             "experience": (v.get("experience") or {}).get("name"),
             "location": (v.get("area") or {}).get("name")}
            for v in items if ok(v)]


def remoteok():
    try:
        data=requests.get("https://remoteok.com/api",headers=UA,timeout=20).json(); out=[]
        for v in data[1:]:
            text=((v.get("position") or "")+" "+(v.get("description") or "")).lower()
            if any(x in text for x in ("react","typescript","javascript","frontend","front-end","html","css","qa","quality assurance","manual tester")) and not any(x in text for x in EXCLUDE):
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

