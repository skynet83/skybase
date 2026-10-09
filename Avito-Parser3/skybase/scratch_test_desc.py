import asyncio
import os
import avito_sniper
from playwright.async_api import async_playwright

async def run():
    chrome_path = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
    if not os.path.exists(chrome_path):
        chrome_path = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"

    async with async_playwright() as p:
        ctx = await p.chromium.launch_persistent_context(
            user_data_dir=avito_sniper.PROFILE_DIR,
            executable_path=chrome_path,
            headless=True,
            args=['--disable-blink-features=AutomationControlled', '--no-sandbox']
        )
        page = await ctx.new_page()
        await page.add_init_script("Object.defineProperty(navigator, 'webdriver', { get: () => undefined });")
        url = 'https://www.avito.ru/kuznetsk/tovary_dlya_kompyutera/radeon_rx_570_8gb_sappfire_1931251647'
        r = await page.goto(url, timeout=20000, wait_until="domcontentloaded")
        print('Status:', r.status if r else None)
        title = await page.title()
        print('Title:', title)
        desc = await page.evaluate("() => { const el = document.querySelector('[data-marker=\"item-view/item-description\"], [itemprop=\"description\"], [class*=\"description-text\"]'); return el ? el.innerText.trim() : ''; }")
        print('Desc:', repr(desc[:150]))
        await ctx.close()

if __name__ == '__main__':
    asyncio.run(run())
