import asyncio, sys, os
from playwright.async_api import async_playwright

async def main():
    url = "https://www.avito.ru/rostov-na-donu/tovary_dlya_kompyutera/rx_570_8gb_8511297408"
    chrome_path = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
    
    async with async_playwright() as p:
        launch_kwargs = {
            "headless": True,
            "executable_path": chrome_path if os.path.exists(chrome_path) else None,
            "args": [
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--no-first-run",
                "--lang=ru-RU,ru"
            ]
        }
        b = await p.chromium.launch(**launch_kwargs)
        ctx = await b.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36",
            locale="ru-RU"
        )
        page = await ctx.new_page()
        await page.add_init_script("Object.defineProperty(navigator, 'webdriver', { get: () => undefined });")
        
        print("Navigating to URL without storage_state:", url)
        try:
            resp = await page.goto(url, timeout=25000, wait_until="domcontentloaded")
            print("Status:", resp.status if resp else "No resp")
            print("Title:", await page.title())
            desc = await page.evaluate("""() => {
                const el = document.querySelector('[data-marker="item-view/item-description"], [data-marker="item-description/text"], [itemprop="description"], [class*="description-text"]');
                return el ? el.innerText.trim() : '';
            }""")
            print("Description found:", desc)
        except Exception as e:
            print("Navigation error:", e)
        finally:
            await b.close()

asyncio.run(main())
