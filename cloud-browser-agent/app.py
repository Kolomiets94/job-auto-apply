import os
from datetime import timedelta
import hmac
import secrets
import time
from collections import defaultdict, deque
from flask import Flask, request, jsonify, render_template_string, redirect, session
from pathlib import Path
from urllib.parse import urlparse
from browserbase_routes import browserbase_bp
from assistant_routes import assistant_bp

app = Flask(__name__)
app.secret_key = os.getenv("APP_SESSION_SECRET")
app.config.update(
    SESSION_COOKIE_SECURE=True,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    PERMANENT_SESSION_LIFETIME=timedelta(days=7),
)
APP_PASSWORD = os.getenv("APP_PASSWORD")
LOGIN_FAILURES = defaultdict(deque)
LOGIN_LIMIT = 5
LOGIN_WINDOW_SECONDS = 15 * 60


def _csrf_token():
    token = session.get("csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        session["csrf_token"] = token
    return token


@app.before_request
def enforce_csrf():
    if request.method not in {"POST", "PUT", "PATCH", "DELETE"}:
        return None
    expected = session.get("csrf_token", "")
    supplied = request.headers.get("X-CSRF-Token") or request.form.get("csrf_token", "")
    if not expected or not supplied or not hmac.compare_digest(expected, supplied):
        return jsonify(error="CSRF validation failed. Reload the page and try again."), 403
    return None


@app.after_request
def add_csrf_meta(response):
    if response.mimetype == "text/html" and session.get("authenticated"):
        body = response.get_data(as_text=True)
        meta = '<meta name="csrf-token" content="' + _csrf_token() + '">'
        if 'name="csrf-token"' not in body:
            body = body.replace("<title>", meta + "<title>", 1)
            body = body.replace('<form action="/logout" method="post">', '<form action="/logout" method="post"><input type="hidden" name="csrf_token" value="' + _csrf_token() + '">')
            response.set_data(body)
    return response

@app.before_request
def require_authentication():
    protected_page = request.path in {"/", "/assistant", "/browser", "/webmcp.js"}
    protected_api = request.path.startswith("/api/")
    if not (protected_page or protected_api):
        return None
    if not APP_PASSWORD or not app.secret_key or len(app.secret_key) < 32:
        message = "Authentication is not configured. Set APP_PASSWORD and APP_SESSION_SECRET (at least 32 characters) in the service environment."
        return (jsonify(error=message), 503) if protected_api else (message, 503)
    if not session.get("authenticated"):
        return (jsonify(error="Authentication required."), 401) if protected_api else redirect("/login")
    return None


LOGIN_PAGE = """<!doctype html><html lang="ru"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Вход — Cloud Job Assistant</title><style>
body{font:16px system-ui;background:#f4f6fb;color:#182033;display:grid;place-items:center;min-height:90vh;margin:0}
main{background:white;border:1px solid #e3e7f0;border-radius:16px;padding:24px;width:min(380px,calc(100% - 48px))}
input,button{box-sizing:border-box;width:100%;padding:12px;border-radius:9px;font:inherit;margin-top:10px}
input{border:1px solid #cbd2e1}button{background:#225de6;color:white;border:0;font-weight:700}
p{color:#596579;font-size:14px}</style><main><h1>Вход</h1><p>Введите пароль приложения, заданный владельцем сервиса.</p>
<form method="post" action="/login"><input type="hidden" name="csrf_token" value="{{ csrf_token }}"><label for="password">Пароль</label><input id="password" name="password" type="password" autocomplete="current-password" required autofocus>
<button type="submit">Войти</button></form></main></html>"""


@app.route("/login", methods=["GET", "POST"])
def login():
    if not APP_PASSWORD or not app.secret_key or len(app.secret_key) < 32:
        return "Authentication is not configured. Set APP_PASSWORD and APP_SESSION_SECRET (at least 32 characters) in the service environment.", 503
    ip = request.remote_addr or "unknown"
    now = time.monotonic()
    failures = LOGIN_FAILURES[ip]
    while failures and now - failures[0] >= LOGIN_WINDOW_SECONDS:
        failures.popleft()
    if request.method == "POST":
        if len(failures) >= LOGIN_LIMIT:
            return ("Слишком много попыток входа. Подождите 15 минут.", 429)
        supplied = request.form.get("password", "")
        if hmac.compare_digest(supplied, APP_PASSWORD):
            LOGIN_FAILURES.pop(ip, None)
            session.clear()
            session["authenticated"] = True
            session.permanent = True
            _csrf_token()
            return redirect("/")
        failures.append(now)
        page = LOGIN_PAGE.replace("{{ csrf_token }}", _csrf_token())
        return page.replace("</main>", "<p role='alert'>Неверный пароль.</p></main>"), 401
    return LOGIN_PAGE.replace("{{ csrf_token }}", _csrf_token())


@app.post("/logout")
def logout():
    session.clear()
    return redirect("/login")


app.register_blueprint(browserbase_bp)
app.register_blueprint(assistant_bp)
PROFILE = {
    "name": os.getenv("CANDIDATE_NAME", "Alexander Kolomiets"),
    "email": os.getenv("CANDIDATE_EMAIL", "kolomiets94@yandex.ru"),
    "github": "https://github.com/Kolomiets94",
    "telegram": "@Kolomiets94",
    "skills": "React, TypeScript, JavaScript, HTML, CSS/SCSS, Redux Toolkit, REST APIs",
    "experience": "Junior frontend developer; personal, learning and open-source projects since 2024. No commercial employment claimed.",
}
TASKS = []

PAGE = """<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Cloud Job Assistant</title>
<style>
body{font:16px system-ui;background:#f4f6fb;color:#182033;margin:0}.wrap{max-width:900px;margin:36px auto;padding:20px}
header,.panel{background:white;border:1px solid #e3e7f0;border-radius:16px;padding:22px;margin-bottom:16px}
h1{margin:0 0 8px}p{line-height:1.5;color:#4c566d}.grid{display:grid;grid-template-columns:1fr 1fr;gap:12px}
label{display:block;font-size:13px;font-weight:700;margin-bottom:6px}input,textarea{width:100%;box-sizing:border-box;border:1px solid #cbd2e1;border-radius:9px;padding:11px;font:inherit}
textarea{min-height:90px}button{background:#225de6;color:white;border:0;border-radius:9px;padding:12px 16px;font-weight:700;cursor:pointer}
.note{background:#fff6df;padding:12px;border-radius:9px;color:#654b00}.muted{font-size:13px;color:#6b7280}
.item{border-top:1px solid #e6eaf2;padding:12px 0;overflow-wrap:anywhere}.pill{font-size:12px;background:#e9efff;padding:4px 8px;border-radius:99px}
@media(max-width:650px){.grid{grid-template-columns:1fr}.wrap{margin:10px;padding:10px}}
</style><div class="wrap">
<header><h1>Cloud Job Assistant</h1><p>Prepare and track job-application tasks. This first version validates target URLs and builds a tailored application brief. It does not submit applications or store passwords.</p><span class="pill">Prototype · free-tier friendly</span><p><a href="/assistant">Универсальный помощник →</a> · <a href="/browser">Тест облачного браузера →</a></p><form action="/logout" method="post"><input type="hidden" name="csrf_token" value="{{ csrf_token }}"><button type="submit">Выйти</button></form><p id="webmcp-status" class="muted" role="status">Проверка поддержки WebMCP…</p></header>
<div class="panel"><h2>New application task</h2><form id="task">
<label>Job posting URL</label><input name="url" type="url" placeholder="https://company.com/careers/job" required>
<div class="grid"><div><label>Role</label><input name="role" value="Junior Frontend Developer (React / TypeScript)"></div><div><label>Company</label><input name="company" placeholder="Company name"></div></div>
<label style="margin-top:12px">Notes / requirements</label><textarea name="notes" placeholder="Remote, junior, React, TypeScript..."></textarea>
<p class="note">Safety: the assistant prepares materials only. Review every answer yourself and submit the application manually. Do not paste passwords, one-time codes, or sensitive documents.</p>
<button type="submit">Prepare application brief</button></form><div id="result"></div></div>
<div class="panel"><h2>Candidate profile</h2><div id="profile"></div></div>
<div class="panel"><h2>Task history</h2><div id="tasks"></div><button id="refresh" type="button">Refresh tasks</button></div>
</div>
<script>
const $=s=>document.querySelector(s);
const csrf=()=>document.querySelector('meta[name="csrf-token"]')?.content || '';
async function load(){
  let p=await fetch('/api/profile').then(r=>r.json());
  const profile=$('#profile');
  profile.replaceChildren();
  const name=document.createElement('b'); name.textContent=p.name; profile.append(name);
  for (const value of [p.skills,p.experience]) {
    const paragraph=document.createElement('p'); paragraph.textContent=value; profile.append(paragraph);
  }
  const links=document.createElement('p');
  const portfolio=document.createElement('a');
  portfolio.href=p.github; portfolio.target='_blank'; portfolio.rel='noreferrer'; portfolio.textContent='GitHub portfolio';
  links.append(portfolio, document.createTextNode(' · '+p.email)); profile.append(links);

  let t=await fetch('/api/tasks').then(r=>r.json());
  $('#tasks').innerHTML=t.length?t.slice().reverse().map(x=>'<div class="item"><b>'+esc(x.role||'Frontend role')+'</b> · '+esc(x.company||'Company not specified')+'<p><a href="'+esc(x.url)+'" target="_blank" rel="noreferrer">'+esc(x.url)+'</a></p><p>'+esc(x.brief)+'</p><span class="pill">Brief prepared · not submitted</span></div>').join(''):'<p class="muted">No tasks yet.</p>';
}
function esc(s){return String(s||'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]))}
$('#task').addEventListener('submit',async e=>{
  e.preventDefault();
  let data=Object.fromEntries(new FormData(e.target));
  let r=await fetch('/api/tasks',{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':csrf()},body:JSON.stringify(data)});
  let d=await r.json();
  const result=$('#result');
  result.replaceChildren();
  const message=document.createElement('p');
  const strong=document.createElement('b'); strong.textContent=d.message || d.error || 'Request completed.';
  message.append(strong); result.append(message);
  if (d.brief) {
    const brief=document.createElement('textarea');
    brief.readOnly=true; brief.value=d.brief; result.append(brief);
  }
  load();
});
$('#refresh').onclick=load;load();
</script><script src="/webmcp.js" defer></script></html>"""

@app.get("/")
def home():
    return render_template_string(PAGE, csrf_token=_csrf_token())

@app.get("/webmcp.js")
def webmcp_script():
    script_path = Path(__file__).resolve().parent / "static" / "webmcp.js"
    if not script_path.is_file():
        return jsonify(error="WebMCP script is missing"), 404
    return app.response_class(script_path.read_bytes(), mimetype="application/javascript")

@app.get("/health")
def health():
    return jsonify(status="ok", service="cloud-job-assistant")

@app.get("/api/profile")
def profile():
    return jsonify(PROFILE)

@app.get("/api/tasks")
def tasks():
    return jsonify(TASKS)

@app.post("/api/tasks")
def create_task():
    data = request.get_json(silent=True) or {}
    url = (data.get("url") or "").strip()
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return jsonify(error="Enter a valid http(s) URL"), 400
    role = (data.get("role") or "Junior Frontend Developer").strip()[:180]
    company = (data.get("company") or "").strip()[:180]
    notes = (data.get("notes") or "").strip()[:1200]
    brief = (
        f"Hello, I am Alexander Kolomiets, a junior frontend developer interested in the {role} role.\n\n"
        "I have hands-on practice through personal, learning and open-source projects using React, TypeScript, "
        "JavaScript, HTML and CSS/SCSS. My experience is non-commercial; I do not claim paid professional employment.\n\n"
        f"Portfolio: {PROFILE['github']}\n"
        f"Relevant skills: {PROFILE['skills']}\n"
        "English: A2; written communication is easiest for me.\n"
        + (f"Role notes to review: {notes}\n" if notes else "")
        + "\nPlease tailor this draft to the actual job description before sending."
    )
    item = {"id": len(TASKS)+1, "url": url, "role": role, "company": company, "notes": notes, "brief": brief}
    TASKS.append(item)
    return jsonify(message="Application brief prepared. Nothing was sent.", brief=brief, task_id=item["id"])

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "10000")))
