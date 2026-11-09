"""Create a local HeadHunter Playwright session for GitHub Actions.

Run locally on a trusted Windows computer. The session is never uploaded.
The generated secret file contains credentials and must not be committed or shared.
"""
import base64
import gzip
import json
from pathlib import Path

from playwright.sync_api import sync_playwright

OUTPUT_DIR = Path.home() / ".job-auto-apply"
STATE_PATH = OUTPUT_DIR / "hh_storage_state.json"
SECRET_PATH = OUTPUT_DIR / "hh_storage_state_secret.txt"


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    print("Откроется Chromium. Войди в свой аккаунт HeadHunter вручную.")
    print("Если появится CAPTCHA или проверка безопасности, пройди её сам.")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(locale="ru-RU")
        page = context.new_page()
        page.goto("https://hh.ru/", wait_until="domcontentloaded")
        input("\nКогда убедишься, что ты вошёл в нужный аккаунт HH, вернись сюда и нажми Enter...")
        # Capture cookies and localStorage only after the user confirms login.
        state = context.storage_state()
        browser.close()

    if not state.get("cookies"):
        raise SystemExit("Сессия не содержит cookies; проверь вход и запусти скрипт ещё раз.")

    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
    compressed = gzip.compress(json.dumps(state, ensure_ascii=False).encode("utf-8"))
    encoded = "gzip-base64:" + base64.b64encode(compressed).decode("ascii")
    SECRET_PATH.write_text(encoded, encoding="utf-8")
    print("\nГотово. Локальные файлы созданы:")
    print(f"  Сессия: {STATE_PATH}")
    print(f"  Значение GitHub Secret: {SECRET_PATH}")
    print("\nНе отправляй эти файлы в чат и не добавляй их в Git.")
    print("Открой secret-файл локально и вставь его содержимое в HH_STORAGE_STATE_JSON на GitHub.")
    print("После сохранения секрета безопасно удали оба локальных файла.")


if __name__ == "__main__":
    main()
