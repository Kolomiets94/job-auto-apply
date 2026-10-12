"""Freelancehunt API adapter. Token stays in environment, never in git."""
import os, requests
import math
import re
from application_schedule import application_time_allowed

BASE="https://api.freelancehunt.com/v2"

def _headers():
    token=os.getenv("FREELANCEHUNT_TOKEN")
    if not token: return None
    return {"Authorization":f"Bearer {token}","Accept-Language":"ru"}

def collect_freelancehunt():
    h=_headers()
    if not h: return []
    r=requests.get(f"{BASE}/projects",headers=h,params={"filter[only_my_skills]":1},timeout=20)
    r.raise_for_status()
    out=[]
    for row in r.json().get("data",[]):
        a=row.get("attributes") or {}
        budget=a.get("budget") or {}
        out.append({"source":"freelancehunt","category":"freelance",
          "external_id":str(row.get("id")),"title":a.get("name"),
          "description":a.get("description_html") or a.get("description") or "",
          "budget":budget,"published":a.get("published_at"),
          "url":f"https://freelancehunt.com/project/{row.get('id')}.html",
          "is_only_for_plus":bool(a.get("is_only_for_plus")),
          "is_premium":bool(a.get("is_premium")),
          "can_api_bid":True})
    return out

def estimate_quote(lead):
    """Estimate only narrowly scoped jobs, with a user-configured hourly rate.

    A missing budget is not evidence of a client's willingness to pay.
    """
    try:
        rate = float(os.getenv("FREELANCE_QUOTE_HOURLY_RATE", "750"))
    except ValueError:
        return None
    currency = os.getenv("FREELANCE_QUOTE_CURRENCY", "UAH").strip().upper()
    if not math.isfinite(rate) or rate <= 0 or not re.fullmatch(r"[A-Z]{3}", currency):
        return None
    title = str(lead.get("title") or "").lower()
    description = re.sub(r"<[^>]+>", " ", str(lead.get("description") or "")).lower()
    if not description.strip() or len(description.strip()) < 40:
        return None
    if any(term in title for term in ("нескольк", "декільк", "several", "multiple", "комплекс", "full website")):
        return None
    if any(term in title for term in ("исправ", "правк", "fix", "bug")):
        hours, days = 4, 2
    elif any(term in title for term in ("лендинг", "landing", "верст", "вёрст", "верстк")):
        hours, days = 16, 4
    else:
        return None
    return {"amount": round(rate * hours, 2), "currency": currency, "days": days}


def add_bid(lead, proposal, days=None):
    if os.getenv("AUTO_FREELANCE_APPLY", "0") != "1":
        return {"status": "SHORTLISTED", "reason": "freelance_apply_disabled"}
    if not application_time_allowed():
        return {"status": "SKIPPED", "reason": "outside_application_hours"}
    h = _headers()
    if not h:
        return {"status": "NEEDS_HUMAN", "reason": "freelancehunt_token_missing"}
    if lead.get("paid_bid") or lead.get("is_only_for_plus") or lead.get("is_premium"):
        return {"status": "SKIPPED", "reason": "paid_bid"}
    budget = lead.get("budget") or {}
    amount, currency = budget.get("amount"), budget.get("currency")
    # No minimum budget; the API still requires a concrete positive quote.
    valid_amount = (isinstance(amount, (int, float)) and not isinstance(amount, bool)
                    and math.isfinite(amount) and amount > 0)
    valid_currency = isinstance(currency, str) and bool(re.fullmatch(r"[A-Z]{3}", currency))
    if not valid_amount or not valid_currency:
        estimate = estimate_quote(lead)
        if estimate and os.getenv("AUTO_FREELANCE_ESTIMATED_BIDS") == "1":
            amount, currency = estimate["amount"], estimate["currency"]
            if days is None:
                days = estimate["days"]
        else:
            return {"status": "NEEDS_CONFIRMATION", "reason": "bid_price_missing_or_invalid",
                    "detail": (f"quote_amount={amount!r}; quote_currency={currency!r}")[:180],
                    "suggested_quote": estimate,
                    "apply_url": lead.get("url"),
                    "next_action": "Configure hourly rate and explicitly enable estimated bids, or review scope manually"}
    title = str(lead.get("title") or "").lower()
    if days is None:
        if any(x in title for x in ("исправ", "правк", "fix", "bug")):
            days = 1
        elif any(x in title for x in ("верст", "вёрст", "landing", "лендинг")):
            days = 3
    if days is None:
        return {"status": "NEEDS_CONFIRMATION", "reason": "project_duration_requires_review"}
    project_id = str(lead.get("external_id") or "")
    if not project_id.isdigit():
        return {"status": "FAILED", "reason": "invalid_project_id"}
    comment = proposal + f"\nСтоимость: {amount} {currency}. Срок: {days} дн."
    body = {"days": days, "safe_type": "employer",
            "budget": {"amount": amount, "currency": currency},
            "comment": comment, "is_hidden": False}
    if not application_time_allowed():
        return {"status": "SKIPPED", "reason": "outside_application_hours"}
    r = requests.post(f"{BASE}/projects/{project_id}/bids",
                      headers={**h, "Content-Type": "application/json"}, json=body, timeout=20)
    if r.status_code in (404, 410):
        return {"status": "SKIPPED", "reason": "project_unavailable"}
    if r.status_code not in (200, 201):
        return {"status": "FAILED", "reason": f"freelancehunt_http_{r.status_code}"}
    try:
        data = r.json().get("data") or {}
    except ValueError:
        data = {}
    if not data.get("id") or (data.get("attributes") or {}).get("comment") != comment:
        return {"status": "NEEDS_CONFIRMATION", "reason": "freelancehunt_bid_not_confirmed"}
    return {"status": "SUBMITTED", "reason": "freelancehunt_api_bid", "bid_id": str(data["id"])}
