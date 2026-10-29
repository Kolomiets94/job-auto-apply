import ipaddress
import os
import socket
from urllib.parse import urlparse

import requests
from flask import Blueprint, jsonify, request, render_template_string
from playwright.sync_api import sync_playwright

browserbase_bp = Blueprint("browserbase", __name__)

BROWSER_PAGE = """<!doctype html><html lang="ru"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Cloud Browser</title><style>body{font:16px system-ui;max-width:760px;margin:28px auto;padding:16px;color:#182033}input,textarea,button{font:inherit;padding:10px;box-sizing:border-box;width:100%;margin:6px 0}button{background:#225de6;color:white;border:0;border-radius:8px}pre,textarea{white-space:pre-wrap;overflow-wrap:anywhere;background:#f4f6fb;padding:12px;border-radius:8px}small{color:#555}</style>
<h1>Cloud Browser — тест</h1><p>Открывает публичную страницу в удалённом браузере Browserbase и извлекает заголовок и текст. Ничего не отправляет и не нажимает кнопки на сайте.</p>
<label>Токен доступа (не Browserbase API key)</label><input id="token" type="password" autocomplete="off" placeholder="AGENT_ACCESS_TOKEN">
<label>Публичный URL</label><input id="url" type="url" value="https://example.com" required>
<button id="run">Открыть страницу и извлечь текст</button><p id="status"></p><pre id="result"></pre>
<script>document.getElementById('run').onclick=async()=>{const status=document.getElementById('status'),out=document.getElementById('result');status.textContent='Выполняю…';out.textContent='';try{const r=await fetch('/api/browser/inspect',{method:'POST',headers:{'Content-Type':'application/json','X-Agent-Token':document.getElementById('token').value},body:JSON.stringify({url:document.getElementById('url').value})});const d=await r.json();if(!r.ok)throw new Error(d.error||('HTTP '+r.status));out.textContent=JSON.stringify(d,null,2);status.textContent='Готово';}catch(e){status.textContent='Ошибка: '+e.message;}}</script></html>"""


def _validate_public_url(value):
    parsed = urlparse(value or "")
    if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("Укажи публичный URL с http:// или https://.")
    host = parsed.hostname.lower().rstrip(".")
    if host in ("localhost",) or host.endswith(".localhost") or host.endswith(".local"):
        raise ValueError("Локальные адреса запрещены.")
    try:
        addresses = {item[4][0] for item in socket.getaddrinfo(host, parsed.port or (443 if parsed.scheme == "https" else 80), type=socket.SOCK_STREAM)}
        if not addresses:
            raise ValueError("Не удалось разрешить домен.")
        for address in addresses:
            ip = ipaddress.ip_address(address)
            if not ip.is_global:
                raise ValueError("Разрешены только публичные адреса.")
    except socket.gaierror:
        raise ValueError("Не удалось разрешить домен.")
    return value


@browserbase_bp.get("/browser")
def browser_page():
    return render_template_string(BROWSER_PAGE)


@browserbase_bp.post("/api/browser/inspect")
def inspect_public_page():
    expected = os.getenv("AGENT_ACCESS_TOKEN", "")
    supplied = request.headers.get("X-Agent-Token", "")
    if not expected or not supplied or not __import__("hmac").compare_digest(expected, supplied):
        return jsonify(error="Нет доступа. Сначала настрой AGENT_ACCESS_TOKEN в Render."), 401

    api_key = os.getenv("BROWSERBASE_API_KEY", "")
    project_id = os.getenv("BROWSERBASE_PROJECT_ID", "")
    if not api_key or not project_id:
        return jsonify(error="Нужно добавить BROWSERBASE_API_KEY и BROWSERBASE_PROJECT_ID в Render Environment."), 503

    try:
        data = request.get_json(silent=True) or {}
        target = _validate_public_url((data.get("url") or "").strip())
        response = requests.post(
            "https://www.browserbase.com/v1/sessions",
            headers={"X-BB-API-Key": api_key, "Content-Type": "application/json"},
            json={"projectId": project_id, "browserSettings": {"viewport": {"width": 1280, "height": 800}}},
            timeout=20,
        )
        if response.status_code >= 400:
            return jsonify(error=f"Browserbase не создал сессию (HTTP {response.status_code}). Проверь API key и Project ID.", details=response.text[:500]), 502
        session = response.json()
        connect_url = session.get("connectUrl")
        session_id = session.get("id")
        if not connect_url:
            return jsonify(error="Browserbase не вернул connectUrl.", details={k: v for k, v in session.items() if k != "connectUrl"}), 502

        result = {}
        with sync_playwright() as playwright:
            browser = playwright.chromium.connect_over_cdp(connect_url, timeout=30000)
            try:
                context = browser.contexts[0] if browser.contexts else browser.new_context()
                page = context.pages[0] if context.pages else context.new_page()
                page.goto(target, wait_until="domcontentloaded", timeout=45000)
                result = {
                    "url": page.url,
                    "title": page.title(),
                    "text": page.locator("body").inner_text(timeout=10000)[:12000],
                    "session_id": session_id,
                    "note": "Только просмотр и извлечение текста; форма не отправлялась.",
                }
            finally:
                browser.close()
        return jsonify(result)
    except ValueError as exc:
        return jsonify(error=str(exc)), 400
    except requests.RequestException:
        return jsonify(error="Не удалось связаться с Browserbase API."), 502
    except Exception as exc:
        return jsonify(error="Ошибка браузера. Проверь логи Render.", details=str(exc)[:400]), 502
