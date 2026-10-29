import os
from flask import Flask, request, jsonify, render_template_string
from urllib.parse import urlparse
from browserbase_routes import browserbase_bp

app = Flask(__name__)
app.register_blueprint(browserbase_bp)
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
<header><h1>Cloud Job Assistant</h1><p>Prepare and track job-application tasks. This first version validates target URLs and builds a tailored application brief. It does not submit applications or store passwords.</p><span class="pill">Prototype · free-tier friendly</span><p><a href="/browser">Open cloud browser test →</a></p></header>
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
async function load(){let p=await fetch('/api/profile').then(r=>r.json());$('#profile').innerHTML='<b>'+p.name+'</b><p>'+p.skills+'</p><p>'+p.experience+'</p><p><a href="'+p.github+'" target="_blank" rel="noreferrer">GitHub portfolio</a> · '+p.email+'</p>';let t=await fetch('/api/tasks').then(r=>r.json());$('#tasks').innerHTML=t.length?t.slice().reverse().map(x=>'<div class="item"><b>'+esc(x.role||'Frontend role')+'</b> · '+esc(x.company||'Company not specified')+'<p><a href="'+x.url+'" target="_blank" rel="noreferrer">'+esc(x.url)+'</a></p><p>'+esc(x.brief)+'</p><span class="pill">Brief prepared · not submitted</span></div>').join(''):'<p class="muted">No tasks yet.</p>'}
function esc(s){return String(s||'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]))}
$('#task').addEventListener('submit',async e=>{e.preventDefault();let data=Object.fromEntries(new FormData(e.target));let r=await fetch('/api/tasks',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});let d=await r.json();$('#result').innerHTML='<p><b>'+esc(d.message)+'</b></p><textarea readonly>'+d.brief+'</textarea>';load()});
$('#refresh').onclick=load;load();
</script></html>"""

@app.get("/")
def home():
    return render_template_string(PAGE)

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
