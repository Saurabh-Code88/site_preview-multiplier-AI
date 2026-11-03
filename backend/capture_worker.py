import json
import os
import sys

from playwright.sync_api import sync_playwright

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
FORCE_HEADED = os.getenv("HEADED") == "1"
ARGS = ["--disable-blink-features=AutomationControlled", "--disable-http2"]


def launch(p, headed):
    # Real Chrome / full Chromium look less like a bot than the headless shell.
    for channel in ("chrome", "chromium"):
        try:
            return p.chromium.launch(channel=channel, headless=not headed, args=ARGS)
        except Exception:
            continue
    return p.chromium.launch(headless=not headed, args=ARGS)


def attempt(p, url, out_path, headed):
    browser = launch(p, headed)
    try:
        ctx = browser.new_context(
            user_agent=USER_AGENT,
            viewport={"width": 1280, "height": 800},
            locale="en-IN",
            timezone_id="Asia/Kolkata",
            extra_http_headers={"Accept-Language": "en-IN,en;q=0.9"},
        )
        ctx.add_init_script("Object.defineProperty(navigator,'webdriver',{get:()=>undefined})")
        page = ctx.new_page()

        status = None
        try:
            resp = page.goto(url, wait_until="domcontentloaded", timeout=25000)
            status = resp.status if resp else None
        except Exception:
            if page.url in ("", "about:blank"):
                raise  # nothing loaded at all
            # otherwise: slow site, use whatever has rendered

        # Wait for real visible content, not just an empty shell.
        try:
            page.wait_for_function(
                "document.body && document.body.innerText.trim().length > 200", timeout=15000
            )
        except Exception:
            pass
        page.wait_for_timeout(1500)

        try:
            text_len = page.evaluate("document.body ? document.body.innerText.trim().length : 0")
        except Exception:
            text_len = 0
        title = page.title()
        page.screenshot(path=out_path, type="jpeg", quality=80)
        return {"title": title, "status": status, "blank": text_len < 50}
    finally:
        browser.close()


def main(url, out_path):
    with sync_playwright() as p:
        result = attempt(p, url, out_path, headed=FORCE_HEADED)
        if result["blank"] and not FORCE_HEADED:
            # Headless got an empty page: retry once with a visible window.
            try:
                retry = attempt(p, url, out_path, headed=True)
                if not retry["blank"]:
                    result = retry
            except Exception:
                pass
        print(json.dumps(result))


if __name__ == "__main__":
    try:
        main(sys.argv[1], sys.argv[2])
    except Exception as e:
        first = (str(e).strip().splitlines() or [type(e).__name__])[0]
        sys.stderr.write(first[:300] + "\n")
        sys.exit(1)