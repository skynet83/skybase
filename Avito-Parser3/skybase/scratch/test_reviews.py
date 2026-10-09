import asyncio
import sys
import os

sys.path.insert(0, r'c:\ins\Avito-Parser2\skybase')
from playwright.async_api import async_playwright
from avito_sniper import launch_sniper_browser

async def test_item_reviews():
    async with async_playwright() as p:
        ctx = await launch_sniper_browser(p, headless=True)
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()
        url = 'https://www.avito.ru/himki/tovary_dlya_kompyutera/videokarta_rx570_8gb_gigabyte_8426554616'
        print('Opening item...')
        try:
            await page.goto(url, timeout=20000, wait_until='domcontentloaded')
            print('Page loaded, title:', await page.title())
            
            # Check for reviews section or seller profile link
            seller_link = await page.locator('a[href*="/user/"]').all()
            print('Seller profile links found:', len(seller_link))
            for sl in seller_link[:3]:
                href = await sl.get_attribute('href')
                txt = await sl.inner_text()
                print('  Seller link:', href, 'text:', txt.strip()[:40])
                
            # Look for reviews block
            reviews_blocks = await page.locator('[data-marker*="review"]').all()
            print('Review blocks found:', len(reviews_blocks))
            for rb in reviews_blocks[:5]:
                txt = await rb.inner_text()
                print('  Review block text:', txt.strip()[:80])
        except Exception as e:
            print('Error:', e)
        finally:
            await ctx.close()

if __name__ == '__main__':
    asyncio.run(test_item_reviews())
