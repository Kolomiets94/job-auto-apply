import express from "express";
import { chromium } from "playwright";

const app = express();
app.use(express.json({ limit: "32kb" }));
app.use(express.urlencoded({ extended: false }));

const TOKEN = process.env.BOOTSTRAP_TOKEN;
if (!TOKEN) throw new Error("BOOTSTRAP_TOKEN is required");

const CHROME_ARGS = ["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"];
let context;
let page;

function ok(req) {
  return req.query.t === TOKEN || req.body?.t === TOKEN || req.get("x-bootstrap-token") === TOKEN;
}
function guard(req, res, next) {
  if (!ok(req)) return res.status(403).send("Forbidden");
  next();
}
async function ensureBrowser() {
  if (page && !page.isClosed()) return page;
  context = await chromium.launchPersistentContext("/tmp/hh-profile", {
    headless: true,
    args: CHROME_ARGS,
    viewport: { width: 390, height: 844 },
    locale: "ru-RU",
  });
  page = context.pages()[0] || await context.newPage();
  await page.goto("https://hh.ru/applicant/profile/me", { waitUntil: "domcontentloaded", timeout: 60000 });
  return page;
}


app.get("/prepare-session", (_req, res) => {
  res.setHeader("Cache-Control", "no-store");
  res.type("html").send(`<!doctype html>
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Подготовить сессию HH</title>
<style>body{font-family:system-ui;max-width:600px;margin:24px auto;padding:16px}button,input,textarea{font-size:18px;margin:12px 0;width:100%;box-sizing:border-box}button{padding:14px}textarea{height:140px}</style>
<h1>Подготовить сессию HH</h1>
<p>Выбери сохранённый hh-state.json. Файл обрабатывается только в браузере телефона и никуда не отправляется.</p>
<input id="file" type="file" accept=".json,application/json">\n<label><input id="cookiesOnly" type="checkbox" style="width:auto"> Только cookies HH (если полный файл слишком большой)</label>\n<p>Этот вариант исключает локальные данные страниц. После переноса нужно проверить вход в HH. Исходный файл не меняется.</p>
<p id="status" role="status"></p>
<textarea id="result" readonly placeholder="Здесь появится сжатое значение для Render"></textarea>
<button id="copy" disabled>Скопировать для GitHub</button>
<p>Переменная Render: <b>HH_STORAGE_STATE_JSON</b>. Вставь скопированное значение в Environment основного сервиса job-auto-apply. Сжатая строка тоже содержит данные доступа: не публикуй её.</p>
<script>
const file=document.getElementById('file'), result=document.getElementById('result'), status=document.getElementById('status'), copy=document.getElementById('copy');
const cookiesOnly=document.getElementById('cookiesOnly');\nasync function prepare(){
 result.value='';copy.disabled=true;
 try{
  const chosen=file.files[0];if(!chosen)return;
  if(chosen.size>5*1024*1024)throw new Error('Файл больше 5 МБ.');
  let state=JSON.parse(await chosen.text());
  if(!Array.isArray(state.cookies)||!Array.isArray(state.origins))throw new Error('Нужен JSON сессии Playwright с cookies и origins.');
  if(cookiesOnly.checked){
   state={cookies:state.cookies.filter(c=>{const domain=String(c.domain||'').replace(/^\\./,'').toLowerCase();return domain==='hh.ru'||domain.endsWith('.hh.ru');}),origins:[]};
   if(!state.cookies.length)throw new Error('В файле нет cookies HH. Нужна новая сессия после входа.');
  }
  const raw=new TextEncoder().encode(JSON.stringify(state));
  let value=new TextDecoder().decode(raw);
  if(raw.byteLength>48000){
   if(typeof CompressionStream==='undefined')throw new Error('Сжатие недоступно. Открой страницу в обновлённом Safari.');
   const compressed=new Uint8Array(await new Response(new Blob([raw]).stream().pipeThrough(new CompressionStream('gzip'))).arrayBuffer());
   let binary='';for(const byte of compressed)binary+=String.fromCharCode(byte);
   value='gzip-base64:'+btoa(binary);
  }
  const size=new TextEncoder().encode(value).byteLength;
  if(size>48000)throw new Error('После сжатия осталось '+Math.ceil(size/1024)+' КБ. В один секрет не помещается. Нужен другой способ хранения; не обрезай текст.');
  result.value=value;copy.disabled=false;status.textContent='Готово: '+Math.ceil(size/1024)+' КБ. Нажми «Скопировать для GitHub».';
 }catch(e){status.textContent=e.message;}
};
file.onchange=prepare;cookiesOnly.onchange=prepare;\ncopy.onclick=async()=>{
 try{await navigator.clipboard.writeText(result.value);status.textContent='Скопировано. Вставь в поле Secret на GitHub.';}
 catch(e){result.focus();result.select();status.textContent='Выделен весь текст. Выбери «Скопировать» в меню телефона.';}
};
</script>`);
});

app.get("/health", (_req, res) => res.send("ok"));

app.get("/", guard, async (_req, res, next) => {
  try {
    await ensureBrowser();
    const t = encodeURIComponent(TOKEN);
    res.type("html").send(`<!doctype html>
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1">
<title>HH Session Bootstrap</title>
<style>
body{font-family:-apple-system,sans-serif;margin:0;background:#111;color:#fff}#bar{position:sticky;top:0;background:#222;padding:8px;z-index:2}
button,input{font-size:16px;padding:10px;margin:3px}#shot{width:100%;display:block;touch-action:manipulation}#txt{width:55%}.hint{font-size:13px;color:#bbb;padding:6px}.pad{display:grid;grid-template-columns:repeat(3,1fr);gap:5px;margin-top:6px}.pad button{font-size:22px;min-height:48px}
</style>
<div id="bar">
<button onclick="nav()">HH</button><button onclick="back()">←</button><button onclick="key('Enter')">Enter</button>
<input id="txt" autocomplete="off" inputmode="numeric" placeholder="Текст для выбранного поля"><button onclick="typeText()">Ввести</button>
<div class="pad">
<button onclick="digit('1')">1</button><button onclick="digit('2')">2</button><button onclick="digit('3')">3</button>
<button onclick="digit('4')">4</button><button onclick="digit('5')">5</button><button onclick="digit('6')">6</button>
<button onclick="digit('7')">7</button><button onclick="digit('8')">8</button><button onclick="digit('9')">9</button>
<button onclick="key('Backspace')">⌫</button><button onclick="digit('0')">0</button><button onclick="key('Enter')">OK</button>
</div>
<a href="/state?t=${t}"><button>Скачать сессию</button></a>
<div class="hint">Нажми поле на снимке HH, затем используй цифровые кнопки выше. Клавиатура iPhone не нужна.</div>
</div>
<img id="shot" src="/shot?t=${t}&n=0">
<script>
const T=${JSON.stringify(TOKEN)}; let n=1;
const shot=document.getElementById('shot');
async function post(path,data={}){await fetch(path,{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({...data,t:T})}); refresh()}
function refresh(){shot.src='/shot?t='+encodeURIComponent(T)+'&n='+(n++)}
shot.onclick=async e=>{const r=shot.getBoundingClientRect(); const x=(e.clientX-r.left)*390/r.width; const y=(e.clientY-r.top)*844/r.height; await post('/click',{x,y})}
async function typeText(){const el=document.getElementById('txt'); await post('/type',{text:el.value}); el.value=''}
async function digit(d){await post('/key',{key:d})}
async function key(k){await post('/key',{key:k})}
async function nav(){await post('/nav')}
async function back(){await post('/back')}
let refreshing=false;
async function safeRefresh(){if(refreshing)return; refreshing=true; try{await new Promise((resolve)=>{shot.onload=shot.onerror=resolve; refresh(); setTimeout(resolve,8000)});}finally{refreshing=false}}
setInterval(safeRefresh,10000);
</script>`);
  } catch (e) { next(e); }
});

app.get("/shot", guard, async (_req, res, next) => {
  try {
    const p = await ensureBrowser();
    const buf = await p.screenshot({ type: "jpeg", quality: 65, animations: "disabled", timeout: 8000 });
    res.type("jpg").send(buf);
  } catch (e) { next(e); }
});
app.post("/click", guard, async (req, res, next) => {
  try { const p = await ensureBrowser(); await p.mouse.click(Number(req.body.x), Number(req.body.y)); res.json({ ok: true }); }
  catch (e) { next(e); }
});
app.post("/type", guard, async (req, res, next) => {
  try { const p = await ensureBrowser(); const text = String(req.body.text || ""); await p.keyboard.insertText(text); res.json({ ok: true }); }
  catch (e) { next(e); }
});
app.post("/key", guard, async (req, res, next) => {
  try { const p = await ensureBrowser(); await p.keyboard.press(String(req.body.key || "Enter")); res.json({ ok: true }); }
  catch (e) { next(e); }
});
app.post("/nav", guard, async (_req, res, next) => {
  try { const p = await ensureBrowser(); await p.goto("https://hh.ru/applicant/profile/me", { waitUntil: "domcontentloaded", timeout: 60000 }); res.json({ ok: true }); }
  catch (e) { next(e); }
});
app.post("/back", guard, async (_req, res, next) => {
  try { const p = await ensureBrowser(); await p.goBack({ waitUntil: "domcontentloaded", timeout: 30000 }).catch(()=>{}); res.json({ ok: true }); }
  catch (e) { next(e); }
});
app.get("/state", guard, async (_req, res, next) => {
  try {
    await ensureBrowser();
    const state = await context.storageState();
    res.setHeader("Content-Disposition", 'attachment; filename="hh-state.json"');
    res.type("application/json").send(JSON.stringify(state));
  } catch (e) { next(e); }
});

app.use((err, _req, res, _next) => {
  console.error("request_error", err);
  res.status(500).send("Browser service error");
});

const port = process.env.PORT || 10000;
try {
  const probe = await chromium.launch({ headless: true, args: CHROME_ARGS });
  await probe.close();
  console.log("Chromium self-test passed");
  app.listen(port, "0.0.0.0", () => console.log("HH bootstrap ready"));
} catch (e) {
  console.error("Chromium self-test failed", e);
  process.exit(1);
}
