import asyncio
import sys
from playwright.async_api import async_playwright

sys.stdout.reconfigure(encoding='utf-8')

async def main():
    proxy = 'http://31.133.32.102:3128'
    url = 'https://www.avito.ru/kanevskaya/tovary_dlya_kompyutera/msi_rx_570_8447829543'
    print(f"Launching playwright with proxy {proxy}...")
    
    launch_args = [
        "--disable-blink-features=AutomationControlled",
        "--no-sandbox",
        "--no-first-run",
        "--no-default-browser-check",
        "--mute-audio",
        "--lang=ru-RU,ru"
    ]
    
    async with async_playwright() as p:
        b = await p.chromium.launch(
            headless=True,
            executable_path=r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            args=launch_args,
            proxy={"server": proxy}
        )
        ctx = await b.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36",
            locale="ru-RU"
        )
        page = await ctx.new_page()
        await page.add_init_script("Object.defineProperty(navigator, 'webdriver', { get: () => undefined });")
        
        print("Navigating to item page...")
        t0 = asyncio.get_event_loop().time()
        try:
            resp = await page.goto(url, timeout=15000, wait_until="domcontentloaded")
            print(f"Initial status: {resp.status if resp else 'none'}, title: {await page.title()}")
            
            # Wait for PoW challenge if present
            for i in range(12):
                title = (await page.title() or "").lower()
                cur_url = page.url
                print(f"  [{i}s] title: {title} | url: {cur_url}")
                if "loading " in title or "доступ ограничен" in title or "проблема с ip" in title or "проверка" in title or "qrator" in title:
                    await page.wait_for_timeout(1000)
                    continue
                print("  Challenge passed & loaded!")
                await page.wait_for_timeout(1000)
                break
            
            final_title = await page.title()
            print(f"Final title: {final_title}")
            
            desc = await page.evaluate("""() => {
                const el = document.querySelector('[data-marker="item-view/item-description"], [data-marker="item-description/text"], [itemprop="description"], [class*="description-text"], [class*="style-item-description"]');
                if (el && el.innerText.trim()) return el.innerText.trim();
                const meta = document.querySelector('meta[property="og:description"], meta[name="description"]');
                if (meta && meta.content && meta.content.trim()) return meta.content.trim();
                return '';
            }""")
            print(f"Description found ({len(desc)} chars): {desc[:100]}")
            
            photos = await page.evaluate("""() => {
                const list = [];
                const imgs = document.querySelectorAll('img[src*="img.avito.st/image/"]');
                imgs.forEach(img => {
                    const src = img.currentSrc || img.src;
                    if (src && !list.includes(src)) list.push(src);
                });
                return list;
            }""")
            print(f"Photos count: {len(photos)}")
            for ph in photos[:3]:
                print(f"  {ph}")
        except Exception as e:
            print("Error during navigation:", e)
        finally:
            await b.close()

if __name__ == "__main__":
    asyncio.run(main())
