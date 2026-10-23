"""One-time helper to save an authenticated hh.ru Playwright session.

Run locally:
    python scripts/save_hh_session.py

A Chromium window opens. Log in to hh.ru manually, complete SMS/CAPTCHA if needed,
then return to the terminal and press Enter. The script writes hh_storage_state.json.

Never commit hh_storage_state.json to git.
"""

from pathlib import Path

from playwright.sync_api import sync_playwright


OUT = Path("hh_storage_state.json")


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()
        page.goto("https://hh.ru/account/login?role=applicant&backurl=%2F")
        print("Войдите в hh.ru в открывшемся окне.")
        print("После успешного входа вернитесь в терминал и нажмите Enter.")
        input()
        context.storage_state(path=str(OUT))
        browser.close()

    print(f"Сессия сохранена: {OUT}")
    print("Добавьте содержимое этого файла в GitHub Secret HH_STORAGE_STATE_JSON.")
    print("Не публикуйте и не коммитьте этот файл.")


if __name__ == "__main__":
    main()
