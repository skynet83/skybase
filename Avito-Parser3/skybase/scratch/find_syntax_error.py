import asyncio
import sys
from playwright.async_api import async_playwright

sys.stdout.reconfigure(encoding='utf-8')

async def main():
    chrome_path = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            executable_path=chrome_path,
            args=["--no-sandbox", "--disable-gpu"]
        )
        page = await browser.new_page()

        cdp = await page.context.new_cdp_session(page)
        await cdp.send("Runtime.enable")

        def on_exception(event):
            details = event.get("exceptionDetails", {})
            print("CDP EXCEPTION:")
            print("  text:", details.get("text"))
            print("  lineNumber:", details.get("lineNumber"))
            print("  columnNumber:", details.get("columnNumber"))
            print("  url:", details.get("url"))
            print("  exception:", details.get("exception", {}).get("description"))

        cdp.on("Runtime.exceptionThrown", on_exception)

        await page.goto("http://127.0.0.1/", wait_until="load")
        await page.wait_for_timeout(2000)

        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
