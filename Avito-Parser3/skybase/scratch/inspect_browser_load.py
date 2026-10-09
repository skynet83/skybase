import asyncio
import sys
from playwright.async_api import async_playwright

sys.stdout.reconfigure(encoding='utf-8')

async def main():
    console_logs = []
    page_errors = []
    failed_requests = []

    chrome_path = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            executable_path=chrome_path,
            args=["--no-sandbox", "--disable-gpu"]
        )
        page = await browser.new_page()

        page.on("console", lambda msg: console_logs.append(f"[{msg.type}] {msg.text} (loc: {msg.location})"))
        page.on("pageerror", lambda err: page_errors.append(f"{err} | stack: {getattr(err, 'stack', '')}"))
        page.on("requestfailed", lambda req: failed_requests.append(f"{req.url} -> {req.failure}"))

        print("Navigating to http://127.0.0.1/ ...")
        try:
            resp = await page.goto("http://127.0.0.1/", wait_until="networkidle", timeout=10000)
            print("Status code:", resp.status if resp else "None")
        except Exception as e:
            print("Goto error / timeout:", e)

        await page.wait_for_timeout(3000)

        print("\n--- Page Title ---")
        print(await page.title())

        print("\n--- Page Errors (Uncaught JS Exceptions) ---")
        if page_errors:
            for err in page_errors:
                print("ERROR:", err)
        else:
            print("No uncaught page errors.")

        print("\n--- Failed Requests ---")
        if failed_requests:
            for fr in failed_requests:
                print("FAILED REQ:", fr)
        else:
            print("No failed network requests.")

        print("\n--- Console Logs (Warnings & Errors) ---")
        for log in console_logs:
            if any(k in log.lower() for k in ["error", "warn", "uncaught", "syntax", "fail"]):
                print(log)

        # Check DOM visibility of key components
        body_text = await page.evaluate("() => document.body.innerText.substring(0, 500)")
        print("\n--- Body text preview (first 500 chars) ---")
        print(repr(body_text))

        # Check loading overlay or spinner
        loading_visible = await page.evaluate("""() => {
            const els = document.querySelectorAll('#loading-overlay, .spinner, [id*="loading"], [class*="loading"]');
            return Array.from(els).map(el => ({
                id: el.id,
                class: el.className,
                display: window.getComputedStyle(el).display,
                visibility: window.getComputedStyle(el).visibility,
                opacity: window.getComputedStyle(el).opacity
            }));
        }""")
        print("\n--- Loading Elements ---")
        print(loading_visible)

        # Save screenshot
        screenshot_path = r"D:\ins\skybase\Avito-Parser3\skybase\scratch\site_screenshot.png"
        await page.screenshot(path=screenshot_path, full_page=True)
        print(f"\nScreenshot saved to {screenshot_path}")

        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
