import re, json, hashlib, os
from datetime import datetime, timezone
import requests
from freelance_sources import collect_freelance
from entry_level import is_placement, placement_is_paid

HH_API="https://api.hh.ru/vacancies"
QUERIES=[
    ("frontend","junior frontend"),
    ("frontend","junior React"),
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
    ("frontend","стажер frontend"),
    ("frontend","frontend intern"),
    ("frontend","практикант React"),
    ("layout","стажер верстальщик"),
    ("layout","HTML CSS intern"),
    ("layout","практикант верстальщик"),
    ("qa","стажер тестировщик"),
    ("qa","QA intern"),
    ("qa","практикант тестировщик"),
]
EXCLUDE=("full stack","fullstack","full-stack","vue","angular","react native","react-native","flutter","middle","senior","lead","head of","manager","director")
UA={"User-Agent":"JobFreelanceHunter/1.1"}


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
    # The candidate also accepts hybrid and office roles; location is checked
    # against the vacancy before a human approves any draft.
    return True


def hh_search(tag,q):
    items=[]
    for page in range(6):
        r=requests.get(HH_API,params={"text":q,"per_page":50,"page":page,"order_by":"publication_time"},headers=UA,timeout=20)
        if r.status_code == 403:
            from hh_web_search import search_hh_web
            return search_hh_web(tag, q)
        r.raise_for_status()
        payload=r.json()
        items.extend(payload.get("items",[]))
        if page >= int(payload.get("pages",1))-1:
            break
    return [{"source":"hh","category":tag,"title":v["name"],"company":(v.get("employer") or {}).get("name"),"url":v.get("alternate_url"),"published":v.get("published_at"),"salary":v.get("salary"),"description":" ".join(str(x or "") for x in (v.get("snippet") or {}).values()),"experience":(v.get("experience") or {}).get("name"),"location":(v.get("area") or {}).get("name")} for v in items if ok(v)]


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

