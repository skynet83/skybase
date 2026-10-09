import asyncio, sys, os
sys.path.insert(0, r"E:\ins\skybase\Avito-Parser3\skybase")
from playwright.async_api import async_playwright
import avito_sniper

async def main():
    url = "https://www.avito.ru/rostov-na-donu/tovary_dlya_kompyutera/rx_570_8gb_8511297408"
    async with async_playwright() as p:
        try:
            ctx = await avito_sniper.launch_sniper_browser(p, headless=True)
            page = ctx.pages[0] if ctx.pages else await ctx.new_page()
            print("Navigating via sniper persistent browser to:", url)
            resp = await page.goto(url, timeout=25000, wait_until="domcontentloaded")
            print("Status:", resp.status if resp else "No resp")
            print("Page title:", await page.title())
            desc = await page.evaluate("""() => {
                const el = document.querySelector('[data-marker="item-view/item-description"], [data-marker="item-description/text"], [itemprop="description"], [class*="description-text"]');
                return el ? el.innerText.trim() : '';
            }""")
            print("Description:", repr(desc))
            photos = await page.evaluate("""() => {
                const list = [];
                const container = document.querySelector('[data-marker="item-view/gallery"], [data-marker="item-view/main-gallery"]');
                if (container) {
                    const galleryEls = container.querySelectorAll('img');
                    galleryEls.forEach(el => {
                        const src = el.currentSrc || el.src || el.getAttribute('data-src');
                        if (src && src.includes('img.avito.st/image/') && !list.includes(src)) {
                            list.push(src);
                        }
                    });
                }
                return list;
            }""")
            print("Photos:", photos)
            await ctx.close()
        except Exception as e:
            print("Error:", e)

asyncio.run(main())
