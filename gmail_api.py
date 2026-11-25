"""Gmail API client over HTTPS; no SMTP/IMAP sockets are used."""
from __future__ import annotations
import base64, json, os, urllib.error, urllib.parse, urllib.request
from email.message import EmailMessage

class GmailApiError(RuntimeError):
    def __init__(self, status=None):
        self.status=status
        super().__init__("Gmail API request failed" + (f" (HTTP {status})" if status else ""))

def _env(name, fallback=""):
    return os.getenv(name, fallback).strip()

def missing_config():
    """Return names of missing Gmail settings without exposing secret values."""
    missing=[k for k in ("GMAIL_CLIENT_ID","GMAIL_CLIENT_SECRET","GMAIL_REFRESH_TOKEN") if not _env(k)]
    if not _env("GMAIL_API_USER",_env("SMTP_USER")):
        missing.append("GMAIL_API_USER (or SMTP_USER)")
    return missing

def is_configured():
    return not missing_config()

def _request(url, method="GET", data=None, headers=None):
    req=urllib.request.Request(url,data=data,headers=headers or {},method=method)
    try:
        with urllib.request.urlopen(req,timeout=25) as response:
            raw=response.read()
            return json.loads(raw.decode("utf-8")) if raw else {}
    except urllib.error.HTTPError as exc:
        raise GmailApiError(exc.code) from None
    except (urllib.error.URLError,TimeoutError,OSError):
        raise GmailApiError() from None

def _access_token():
    if not is_configured(): raise GmailApiError()
    form=urllib.parse.urlencode({
        "client_id":_env("GMAIL_CLIENT_ID"),
        "client_secret":_env("GMAIL_CLIENT_SECRET"),
        "refresh_token":_env("GMAIL_REFRESH_TOKEN"),
        "grant_type":"refresh_token",
    }).encode("utf-8")
    result=_request("https://oauth2.googleapis.com/token","POST",form,{"Content-Type":"application/x-www-form-urlencoded"})
    token=result.get("access_token")
    if not token: raise GmailApiError()
    return token

def _api(method,path,payload=None):
    token=_access_token()
    data=json.dumps(payload).encode("utf-8") if payload is not None else None
    headers={"Authorization":"Bearer "+token}
    if data is not None: headers["Content-Type"]="application/json"
    return _request("https://gmail.googleapis.com/gmail/v1/users/me/"+path,method,data,headers)

def get_profile():
    p=_api("GET","profile")
    return {"email":p.get("emailAddress"),"messages_total":p.get("messagesTotal"),"threads_total":p.get("threadsTotal")}

def send_message(to,subject,body):
    msg=EmailMessage()
    msg["From"]=_env("GMAIL_API_USER",_env("SMTP_USER"))
    msg["To"]=to
    msg["Subject"]=subject
    msg.set_content(body)
    raw=base64.urlsafe_b64encode(msg.as_bytes()).decode("ascii").rstrip("=")
    return _api("POST","messages/send",{"raw":raw})

def list_unread(limit=25):
    result=_api("GET","messages?q=is%3Aunread&maxResults="+str(max(1,min(limit,100))))
    return [x["id"] for x in result.get("messages",[]) if x.get("id")]

def get_raw_message(message_id):
    result=_api("GET","messages/"+urllib.parse.quote(message_id,safe="")+"?format=raw")
    raw=result.get("raw")
    return base64.urlsafe_b64decode(raw+"="*(-len(raw)%4)) if raw else b""

def mark_read(message_id):
    _api("POST","messages/"+urllib.parse.quote(message_id,safe="")+"/modify",{"removeLabelIds":["UNREAD"]})
