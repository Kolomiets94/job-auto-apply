from flask import Blueprint, jsonify, request, render_template_string
from browserbase_routes import _validate_public_url
from playwright.sync_api import sync_playwright

assistant_bp = Blueprint("assistant", __name__)

PAGE = """<!doctype html><html lang="ru"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Универсальный облачный помощник</title>
<style>
body{font:16px system-ui;max-width:850px;margin:24px auto;padding:16px;color:#172033;background:#f5f7fb}
header,section{background:#fff;border:1px solid #e1e6ef;border-radius:14px;padding:18px;margin:12px 0}
textarea,input{box-sizing:border-box;width:100%;padding:12px;border:1px solid #cbd5e1;border-radius:8px;font:inherit;margin:6px 0 14px}
button{background:#225de6;color:white;border:0;border-radius:8px;padding:12px 16px;font:inherit;cursor:pointer}
pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f2f5fa;border-radius:8px;padding:12px}
small{color:#596579}.links a{margin-right:12px}
</style><header><h1>Универсальный облачный помощник</h1>
<p>Бесплатный MVP: принимает задачу, при необходимости читает публичную веб-страницу и формирует рабочую сводку. Не входит в аккаунты, не нажимает кнопки отправки и не выполняет необратимые действия.</p>
<div class="links"><a href="/">Задачи</a><a href="/browser">Тест браузера</a></div></header>
<section><form id="form"><label for="goal"><b>Что нужно сделать?</b></label>
<textarea id="goal" required placeholder="Например: изучи эту страницу и выдели главные условия, сроки и следующие шаги"></textarea>
<label for="url"><b>Публичная ссылка (необязательно)</b></label><input id="url" type="url" placeholder="https://example.com">
<button type="submit">Выполнить задачу</button></form><p id="status"></p><div id="result"></div>
<small>Важно: без подключения отдельной языковой модели это первая версия с правилами и извлечением текста, а не полноценный генеративный ИИ. Никакие платные API-ключи не нужны.</small></section>
<script>
const form=document.querySelector('#form'),status=document.querySelector('#status'),result=document.querySelector('#result');
form.addEventListener('submit',async e=>{e.preventDefault();status.textContent='Выполняю задачу…';result.textContent='';
try{const r=await fetch('/api/assistant/run',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({goal:document.querySelector('#goal').value,url:document.querySelector('#url').value})});const d=await r.json();if(!r.ok)throw new Error(d.error||'Ошибка запроса');status.textContent='Готово';const pre=document.createElement('pre');pre.textContent=d.result;result.appendChild(pre);if(d.page){const p=document.createElement('p');p.textContent='Страница: '+d.page.title+' ('+d.page.url+')';result.prepend(p)}}catch(err){status.textContent='Не удалось выполнить: '+err.message}});
</script></html>"""

def _plan(goal, page_text=""):
    g = goal.lower()
    steps = []
    if any(k in g for k in ("сравн", "compare", "vs ", "разниц")):
        steps = ["Собрать сравниваемые варианты и одинаковые критерии.", "Сверить факты и отметить, каких данных не хватает.", "Сформировать таблицу плюсов, минусов и компромиссов."]
    elif any(k in g for k in ("резюме", "ваканс", "работ", "job", "cv", "cover letter", "отклик")):
        steps = ["Извлечь требования и обязательные условия.", "Сопоставить требования с подтверждёнными навыками; не выдумывать опыт.", "Подготовить черновик резюме или отклика для проверки человеком."]
    elif any(k in g for k in ("сумм", "кратко", "главн", "изучи", "анализ", "summary", "summar")):
        steps = ["Выделить основную тему и ключевые факты.", "Отделить явно указанные факты от выводов и неизвестных данных.", "Составить краткую сводку и список следующих шагов."]
    else:
        steps = ["Уточнить ожидаемый результат и ограничения задачи.", "Разбить задачу на небольшие проверяемые шаги.", "Проверить результат и обозначить то, что требует решения пользователя."]
    lines = ["Задача: " + goal.strip(), "", "Рабочий план:"]
    lines.extend(f"{i}. {step}" for i, step in enumerate(steps, 1))
    if page_text:
        text = " ".join(page_text.split())
        lines += ["", "Извлечённый текст страницы (фрагмент):", text[:5000] or "[На странице не найден текст]"]
    lines += ["", "Статус: подготовлен план и собран доступный текст; действия от имени пользователя не выполнялись."]
    return "\n".join(lines)

@assistant_bp.get("/assistant")
def assistant_page():
    return render_template_string(PAGE)

@assistant_bp.post("/api/assistant/run")
def assistant_run():
    data = request.get_json(silent=True) or {}
    goal = (data.get("goal") or "").strip()[:2000]
    url = (data.get("url") or "").strip()
    if not goal:
        return jsonify(error="Опиши задачу."), 400
    page_data = None
    page_text = ""
    if url:
        try:
            target = _validate_public_url(url)
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
                try:
                    context = browser.new_context(accept_downloads=False)
                    page = context.new_page()
                    page.set_default_navigation_timeout(20000)
                    page.goto(target, wait_until="domcontentloaded")
                    page_data = {"url": page.url, "title": page.title()}
                    page_text = page.locator("body").inner_text(timeout=8000)[:5000]
                    context.close()
                finally:
                    browser.close()
        except ValueError as exc:
            return jsonify(error=str(exc)), 400
        except Exception as exc:
            return jsonify(error="Не удалось прочитать страницу. Проверь URL или логи сервера.", details=str(exc)[:250]), 502
    return jsonify(result=_plan(goal, page_text), page=page_data)
