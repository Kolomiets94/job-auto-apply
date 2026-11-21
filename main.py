import re, json, hashlib, os
from datetime import datetime, timezone
import requests
from freelance_sources import collect_freelance
from entry_level import is_placement
from salary_policy import salary_decision

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
    ("frontend","стажер React"),
    ("frontend","стажёр React"),
    ("frontend","React intern"),
    ("frontend","Next.js junior"),
    ("frontend","React Next.js"),
    ("frontend","React AI"),
    ("frontend","React LLM"),
    ("frontend","React AI agents"),
    ("frontend","React MCP"),
    ("frontend","Next.js AI"),
    ("frontend","frontend AI интеграции"),
    ("frontend","React интеграция нейросетей"),
    ("layout","junior верстальщик"),
    ("layout","junior HTML CSS"),
    ("layout","младший верстальщик"),
    ("layout","junior HTML"),
]

# Hybrid is searched separately and only inside Yekaterinburg.
HYBRID_QUERIES=[
    ("frontend","junior frontend"),
    ("frontend","junior React"),
    ("frontend","React TypeScript"),
    ("frontend","junior JavaScript"),
    ("layout","junior верстальщик"),
    ("layout","junior HTML CSS"),
]
EXCLUDE=("full stack","fullstack","full-stack","vue","angular","react native","react-native","flutter","middle","senior","lead","head of","manager","director")
UA={"User-Agent":"JobFreelanceHunter/1.1"}


class HHAccessUnavailable(RuntimeError):
    """Public API is blocked and there is no usable browser search session."""


def salary_ok(v):
    """Keep in-range offers; ambiguous salary stays visible for manual review."""
    lead = {**v, "title": v.get("name") or v.get("title"),
            "description": " ".join(str(x or "") for x in (v.get("snippet") or {}).values())}
    return salary_decision(lead) != "rejected"


def ok(v):
    text=((v.get("name") or "")+" "+" ".join(str(x or "") for x in (v.get("snippet") or {}).values())).lower()
    title = (v.get("name") or "").lower()
    level_terms = ("middle", "senior", "lead", "head of", "manager", "director")
    # Team descriptions may mention senior colleagues or a team lead.
    # The target vacancy's title determines its advertised seniority.
    if any(x in title for x in level_terms): return False
    if any(x in text for x in EXCLUDE if x not in level_terms): return False
    if not salary_ok(v): return False
    # Paid placements are intentionally retained for ranking; salary_ok rejects unpaid or unclear ones.
    return True


_HH_YEKATERINBURG_AREA_ID = None


def hh_yekaterinburg_area_id():
    """Resolve Yekaterinburg's current HH area ID instead of hard-coding it."""
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


def _hh_search(tag, q, work_format, area=None, max_pages=6):
    """Fetch HH vacancies for one explicit work format and optional region."""
    import time

    items = []
    for page in range(max_pages):
        params = {
            "text": q, "per_page": 50, "page": page,
            "order_by": "publication_time",
        }
        if work_format:
            params["work_format"] = work_format
        if area:
            params["area"] = str(area)
        for attempt in range(3):
            try:
                r = requests.get(HH_API, params=params, headers=UA, timeout=20)
            except (requests.Timeout, requests.ConnectionError) as exc:
                if attempt == 2:
                    raise HHAccessUnavailable("HH API network unavailable") from exc
                time.sleep(2 ** attempt)
                continue
            if r.status_code in (401, 403):
                raise HHAccessUnavailable(f"HH API HTTP {r.status_code}; stop queries")
            if r.status_code == 429 or 500 <= r.status_code < 600:
                if attempt == 2:
                    raise HHAccessUnavailable(f"HH API HTTP {r.status_code} after retries")
                retry_after = r.headers.get("Retry-After", "")
                try:
                    delay = min(30, max(1, float(retry_after)))
                except (TypeError, ValueError):
                    delay = 2 ** attempt
                time.sleep(delay)
                continue
            r.raise_for_status()
            break
        payload = r.json()
        items.extend(payload.get("items", []))
        if page >= int(payload.get("pages", 1)) - 1:
            break

    return [{
        "source": "hh",
        "category": tag,
        "title": v.get("name"),
        "company": (v.get("employer") or {}).get("name"),
        "url": v.get("alternate_url"),
        "published": v.get("published_at"),
        "salary": v.get("salary") or v.get("salary_range"),
        "description": " ".join(str(x or "") for x in (v.get("snippet") or {}).values()),
        "experience": (v.get("experience") or {}).get("name"),
        "location": (v.get("area") or {}).get("name"),
        "work_format": v.get("work_format") or [],
        "schedule": v.get("schedule") or {},
        "work_mode": work_format or "",
    } for v in items if ok(v)]


def hh_search(tag, q):
    """Search fully remote HH vacancies across Russia."""
    return _hh_search(tag, q, work_format="REMOTE")


def hh_search_hybrid(tag, q):
    """Search hybrid HH vacancies only in Yekaterinburg."""
    area_id = hh_yekaterinburg_area_id()
    return _hh_search(tag, q, work_format="HYBRID", area=area_id, max_pages=2)


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

