"""One-time helper to capture an authenticated hh.ru Playwright session.

Run locally on a trusted computer:
    python scripts/capture_hh_session.py

A browser opens. Log in to hh.ru manually, including SMS/CAPTCHA if shown.
After login, return to the terminal and press Enter. The script saves
Playwright storage state to hh-storage-state.json.

Do NOT commit hh-storage-state.json. Put its JSON content into the
GitHub Actions secret HH_STORAGE_STATE_JSON instead.
"""

from pathlib import Path

from playwright.sync_api import sync_playwright

OUTPUT = Path("hh-storage-state.json")


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()
        page.goto("https://hh.ru/account/login?role=applicant", wait_until="domcontentloaded")

        print("Войдите в hh.ru в открывшемся окне браузера.")
        print("После успешного входа вернитесь в терминал и нажмите Enter.")
        input()

        context.storage_state(path=str(OUTPUT))
        browser.close()

    print(f"Сессия сохранена: {OUTPUT.resolve()}")
    print("Не коммитьте этот файл в Git.")
    print("Скопируйте его JSON в GitHub Secret: HH_STORAGE_STATE_JSON")


if __name__ == "__main__":
    main()
