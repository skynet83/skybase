import asyncio
import os
from playwright.async_api import async_playwright

async def main():
    chrome_path = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
    if not os.path.exists(chrome_path):
        chrome_path = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
        
    url = "https://www.avito.ru/bryansk/tovary_dlya_kompyutera/videokarta_rx580_8425879609"
    async with async_playwright() as p:
        b = await p.chromium.launch(
            executable_path=chrome_path,
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--mute-audio",
                "--lang=ru-RU,ru"
            ]
        )
        ctx = await b.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36",
            locale="ru-RU"
        )
        page = await ctx.new_page()
        await page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            window.chrome = { runtime: {} };
        """)
        try:
            resp = await page.goto(url, timeout=12000, wait_until="domcontentloaded")
            print("Status:", resp.status if resp else "no resp")
            await page.wait_for_timeout(2000)
            
            title = await page.title()
            print("Title:", title)
            
            data = await page.evaluate("""() => {
                const descEl = document.querySelector('[data-marker="item-view/item-description"], [itemprop="description"], [data-marker*="description"]');
                const desc = descEl ? descEl.innerText : '';
                
                const metaDesc = document.querySelector('meta[property="og:description"], meta[name="description"]');
                const mDesc = metaDesc ? metaDesc.getAttribute('content') : '';
                
                const photos = [];
                document.querySelectorAll('[data-marker*="gallery"] img, [data-marker*="image-frame"] img, [class*="gallery"] img, [data-marker*="image-preview"] img').forEach(el => {
                    const src = el.currentSrc || el.src || el.getAttribute('data-src');
                    if (src && src.includes('img.avito.st/image/') && !photos.includes(src)) {
                        if (!src.includes('avatar') && !src.includes('badge') && !src.includes('icon')) {
                            photos.push(src);
                        }
                    }
                });
                return { desc, mDesc, photos };
            }""")
            print("Desc length:", len(data.get("desc", "")))
            print("Desc sample:", data.get("desc", "")[:200])
            print("Meta desc:", data.get("mDesc", "")[:200])
            print("Photos count:", len(data.get("photos", [])))
            print("Photos sample:", data.get("photos", [])[:3])
        except Exception as e:
            print("Error in page:", e)
        finally:
            await b.close()

asyncio.run(main())
