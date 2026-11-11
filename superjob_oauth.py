"""Secure SuperJob applicant OAuth token storage and refresh helpers."""
import os
import time
import requests
from cryptography.fernet import Fernet
from queue_store import _db

API = "https://api.superjob.ru/2.0"


def _settings():
    client_id = os.getenv("SUPERJOB_CLIENT_ID", "").strip()
    client_secret = os.getenv("SUPERJOB_CLIENT_SECRET", "").strip()
    app_key = (os.getenv("SUPERJOB_API_KEY") or client_secret).strip()
    encryption_key = os.getenv("SUPERJOB_TOKEN_ENCRYPTION_KEY", "").strip()
    if not client_id.isdigit() or not client_secret or not app_key or not encryption_key:
        raise RuntimeError("SuperJob OAuth environment is incomplete")
    return client_id, client_secret, app_key, Fernet(encryption_key.encode())


def _table():
    with _db() as c:
        c.execute("""CREATE TABLE IF NOT EXISTS superjob_oauth_tokens (
            id INTEGER PRIMARY KEY, access_token TEXT NOT NULL,
            refresh_token TEXT NOT NULL, expires_at DOUBLE PRECISION NOT NULL,
            updated_at TEXT NOT NULL
        )""")


def exchange_code(code):
    client_id, client_secret, _, _ = _settings()
    redirect_uri = os.getenv("SUPERJOB_REDIRECT_URI", "").strip()
    response = requests.post(
        API + "/oauth2/access_token/",
        data={"code": code, "client_id": client_id,
              "client_secret": client_secret, "redirect_uri": redirect_uri},
        timeout=20,
    )
    response.raise_for_status()
    data = response.json()
    if not data.get("access_token") or not data.get("refresh_token"):
        raise RuntimeError("SuperJob did not return both OAuth tokens")
    return data


def save_tokens(data):
    _, _, _, cipher = _settings()
    _table()
    expires_at = time.time() + max(60, int(data.get("expires_in", 3600)))
    values = (cipher.encrypt(data["access_token"].encode()).decode(),
              cipher.encrypt(data["refresh_token"].encode()).decode(),
              expires_at, time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    with _db() as c:
        c.execute("""INSERT INTO superjob_oauth_tokens
            (id, access_token, refresh_token, expires_at, updated_at)
            VALUES (1, ?, ?, ?, ?)
            ON CONFLICT (id) DO UPDATE SET
            access_token=excluded.access_token,
            refresh_token=excluded.refresh_token,
            expires_at=excluded.expires_at, updated_at=excluded.updated_at""", values)


def _load_tokens():
    _, _, _, cipher = _settings()
    _table()
    with _db() as c:
        row = c.execute("SELECT access_token, refresh_token, expires_at FROM superjob_oauth_tokens WHERE id=1").fetchone()
    if not row:
        raise RuntimeError("SuperJob applicant is not connected")
    return cipher.decrypt(row[0].encode()).decode(), cipher.decrypt(row[1].encode()).decode(), float(row[2])


def get_access_token():
    access, refresh, expires_at = _load_tokens()
    if expires_at > time.time() + 90:
        return access
    client_id, client_secret, _, _ = _settings()
    response = requests.get(API + "/oauth2/refresh_token/",
        params={"refresh_token": refresh, "client_id": client_id,
                "client_secret": client_secret}, timeout=20)
    response.raise_for_status()
    data = response.json()
    if not data.get("access_token") or not data.get("refresh_token"):
        raise RuntimeError("SuperJob token refresh response is incomplete")
    save_tokens(data)
    return data["access_token"]


def get_current_user():
    _, _, app_key, _ = _settings()
    response = requests.get(API + "/user/current/",
        headers={"X-Api-App-Id": app_key,
                 "Authorization": "Bearer " + get_access_token()},
        timeout=20)
    response.raise_for_status()
    return response.json()
