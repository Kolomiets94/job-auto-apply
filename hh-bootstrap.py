"""Create a local HeadHunter Playwright session for GitHub Actions.

Run locally on a trusted Windows computer. The session is never uploaded.
The generated file contains authentication cookies: keep it private.
"""
import base64
import gzip
import json
from pathlib import Path

from playwright.sync_api import sync_playwright

OUTPUT_DIR = Path.home() / ".job-auto-apply"
SECRET_PATH = OUTPUT_DIR / "hh_storage_state_secret.txt"


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    print("Откроется Chromium. Войди в свой аккаунт HeadHunter вручную.")
    print("Если появится CAPTCHA или проверка безопасности, пройди её сам.")
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=False)
            try:
                context = browser.new_context(locale="ru-RU")
                page = context.new_page()
                page.goto("https://hh.ru/", wait_until="domcontentloaded")
                input("\nКогда убедишься, что ты вошёл в нужный аккаунт HH, вернись сюда и нажми Enter...")
                # Capture cookies and localStorage only after the user confirms login.
                state = context.storage_state()
            finally:
                browser.close()
    except Exception as exc:
        message = str(exc).lower()
        if "executable doesn't exist" in message or "browser_type.launch" in message:
            raise SystemExit(
                "Chromium не установлен. Выполни в терминале: python -m playwright install chromium"
            ) from None
        raise

    if not state.get("cookies"):
        raise SystemExit("Сессия не содержит cookies; проверь вход и запусти скрипт ещё раз.")

    compressed = gzip.compress(json.dumps(state, ensure_ascii=False).encode("utf-8"))
    encoded = "gzip-base64:" + base64.b64encode(compressed).decode("ascii")
    SECRET_PATH.write_text(encoded, encoding="utf-8")
    print("\nГотово. Файл со значением GitHub Secret создан:")
    print(f"  {SECRET_PATH}")
    print("\nЭтот файл даёт доступ к аккаунту HH. Не отправляй его в чат, не публикуй и не добавляй в Git.")
    print("Открой файл локально и вставь всё его содержимое в GitHub Secret HH_STORAGE_STATE_JSON.")
    print("После сохранения секрета удали локальный файл. Если он утечёт, выйди из аккаунта HH и обнови сессию.")


if __name__ == "__main__":
    main()
