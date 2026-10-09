import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            executable_path=r'c:\ins\skybase\browsers\chromium-1243\chrome-win64\chrome.exe',
            headless=True
        )
        page = await browser.new_page(viewport={'width': 1200, 'height': 800})
        await page.goto('http://127.0.0.1/index.html')
        await page.wait_for_timeout(1000)
        # remove any overlay toast messages
        await page.evaluate('''() => {
            document.querySelectorAll('.toast, .notification, [class*="toast"], [id*="toast"]').forEach(e => e.remove());
        }''')
        footer = await page.query_selector('footer')
        if footer:
            await footer.screenshot(path='c:/ins/skybase/scratch/real_footer.png')
            print('Saved real_footer.png!')
        await browser.close()

asyncio.run(main())
