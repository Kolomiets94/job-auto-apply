import ipaddress
import socket
from urllib.parse import urlparse

from flask import Blueprint, jsonify, request, render_template_string
from playwright.sync_api import sync_playwright

browserbase_bp = Blueprint("browserbase", __name__)

BROWSER_PAGE = """<!doctype html><html lang="ru"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Бесплатный облачный браузер</title><style>body{font:16px system-ui;max-width:760px;margin:28px auto;padding:16px;color:#182033}input,button{font:inherit;padding:10px;box-sizing:border-box;width:100%;margin:6px 0}button{background:#225de6;color:white;border:0;border-radius:8px}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f4f6fb;padding:12px;border-radius:8px}small{color:#555}</style>
<h1>Бесплатный облачный браузер</h1><p>Открывает публичную страницу в Chromium на этом сервере и извлекает заголовок и текст. Не нажимает кнопки и не отправляет формы.</p>
<label>Публичный URL</label><input id="url" type="url" value="https://example.com" required>
<button id="run">Открыть страницу и извлечь текст</button><p id="status"></p><pre id="result"></pre>
<script>document.getElementById('run').onclick=async()=>{const status=document.getElementById('status'),out=document.getElementById('result');status.textContent='Выполняю…';out.textContent='';try{const r=await fetch('/api/browser/inspect',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({url:document.getElementById('url').value})});const d=await r.json();if(!r.ok)throw new Error(d.error||('HTTP '+r.status));out.textContent=JSON.stringify(d,null,2);status.textContent='Готово';}catch(e){status.textContent='Ошибка: '+e.message;}}</script></html>"""


def _validate_public_url(value):
    parsed = urlparse(value or "")
    if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("Укажи публичный URL с http:// или https://.")
    host = parsed.hostname.lower().rstrip(".")
    if host == "localhost" or host.endswith((".localhost", ".local")):
        raise ValueError("Локальные адреса запрещены.")
    try:
        addresses = {item[4][0] for item in socket.getaddrinfo(host, parsed.port or (443 if parsed.scheme == "https" else 80), type=socket.SOCK_STREAM)}
        if not addresses:
            raise ValueError("Не удалось разрешить домен.")
        for address in addresses:
            if not ipaddress.ip_address(address).is_global:
                raise ValueError("Разрешены только публичные адреса.")
    except socket.gaierror:
        raise ValueError("Не удалось разрешить домен.")
    return value


@browserbase_bp.get("/browser")
def browser_page():
    return render_template_string(BROWSER_PAGE)


@browserbase_bp.post("/api/browser/inspect")
def inspect_public_page():
    try:
        data = request.get_json(silent=True) or {}
        target = _validate_public_url((data.get("url") or "").strip())
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True, args=["--no-sandbox"])
            try:
                context = browser.new_context(viewport={"width": 1280, "height": 800}, accept_downloads=False)
                page = context.new_page()
                page.set_default_navigation_timeout(30000)
                page.goto(target, wait_until="domcontentloaded")
                result = {
                    "url": page.url,
                    "title": page.title(),
                    "text": page.locator("body").inner_text(timeout=10000)[:12000],
                    "note": "Локальный Chromium на бесплатном сервере; только просмотр, без отправки форм.",
                }
                context.close()
            finally:
                browser.close()
        return jsonify(result)
    except ValueError as exc:
        return jsonify(error=str(exc)), 400
    except Exception as exc:
        return jsonify(error="Ошибка браузера. Проверь логи Render.", details=str(exc)[:400]), 502
