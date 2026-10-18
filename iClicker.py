"""
Open a Chrome tab and alert when its visible content changes.

Usage:
    python iClicker.py                      # opens the iClicker student site
    python iClicker.py https://example.com  # opens any URL you pass in

Log in / navigate normally in the window that opens. The script watches
whatever page that tab is on and beeps + pops up a message box whenever
the visible text changes.
"""
import ctypes
import hashlib
import os
import sys
import threading
import time
import winsound
from pathlib import Path

from dotenv import load_dotenv
from playwright.sync_api import sync_playwright, Error as PlaywrightError

# Loads ICLICKER_EMAIL / ICLICKER_PASSWORD from the .env file into os.environ
load_dotenv()

DEFAULT_URL = "https://student.iclicker.com/"
CHECK_EVERY_SECONDS = 2
# Saved Chrome profile so your login survives between runs
PROFILE_DIR = Path(__file__).parent / ".iclicker_chrome_profile"


def page_fingerprint(page):
    """Return a hash of the page's visible text (None if the page isn't ready)."""
    try:
        text = page.inner_text("body", timeout=5000)
    except PlaywrightError:
        return None
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def alert(message):
    """Beep and show a Windows message box without blocking the watcher."""
    winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
    # 0x40000 = MB_TOPMOST, 0x30 = MB_ICONWARNING
    threading.Thread(
        target=ctypes.windll.user32.MessageBoxW,
        args=(None, message, "iClicker watcher", 0x40000 | 0x30),
        daemon=True,
    ).start()


def login(page, email, password):
    """Fill in the iClicker student login form on an already-open page."""
    page.fill("#input-email", email)
    page.fill("#input-password", password)
    page.click("#sign-in-button")
    # The app is a single-page site (#/login -> #/courses), so wait for the hash to change
    page.wait_for_url(lambda u: "login" not in u, timeout=15000)


def main():
    url = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_URL

    with sync_playwright() as p:
        # channel="chrome" uses your installed Google Chrome instead of Playwright's Chromium
        browser = p.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR),
            channel="chrome",
            headless=False,
            no_viewport=True,
        )
        page = browser.pages[0] if browser.pages else browser.new_page()
        page.goto(url)

        # student.iclicker.com redirects to #/login only when you're logged out,
        # so check where we actually landed rather than the URL we asked for
        page.wait_for_load_state("networkidle")
        if "login" in page.url:
            email = os.environ.get("ICLICKER_EMAIL")
            password = os.environ.get("ICLICKER_PASSWORD")
            if email and password:
                login(page, email, password)
            else:
                print("Add ICLICKER_EMAIL and ICLICKER_PASSWORD to .env to auto-login, or log in manually in the window.")

        print(f"Watching {url} (checking every {CHECK_EVERY_SECONDS}s). Close the browser or Ctrl+C to stop.")
        last_url = page.url
        last_hash = page_fingerprint(page)

        try:
            while not page.is_closed():
                time.sleep(CHECK_EVERY_SECONDS)
                current_hash = page_fingerprint(page)
                if current_hash is None:
                    continue  # page mid-navigation; try again next tick

                if page.url != last_url:
                    # You navigated somewhere new (e.g. after logging in) - start
                    # tracking the new page instead of alerting on it.
                    print(f"[{time.strftime('%H:%M:%S')}] Now watching {page.url}")
                    last_url = page.url
                elif current_hash != last_hash:
                    print(f"[{time.strftime('%H:%M:%S')}] Content changed!")
                    alert(f"The page content changed:\n{page.url}")

                last_hash = current_hash
        except KeyboardInterrupt:
            pass
        finally:
            try:
                browser.close()
            except PlaywrightError:
                pass


if __name__ == "__main__":
    main()
