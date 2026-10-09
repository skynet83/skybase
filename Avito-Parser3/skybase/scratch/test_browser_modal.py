import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            executable_path=r'C:\ins\skybase\browsers\chromium-1243\chrome-win64\chrome.exe'
        )
        page = await browser.new_page()
        page.on('console', lambda msg: print(f'[CONSOLE {msg.type}] {msg.text}'))
        page.on('pageerror', lambda err: print(f'[PAGE ERROR] {err}'))

        print('Navigating to http://localhost/ ...')
        resp = await page.goto('http://localhost/', timeout=10000)
        print('HTTP status:', resp.status if resp else 'No response')
        await page.wait_for_timeout(2000)

        # Test opening the modal
        print('Testing openManageSearchesModal()...')
        await page.evaluate('openManageSearchesModal()')
        await page.wait_for_timeout(1000)

        # Check if the modal elements exist
        has_query = await page.evaluate('!!document.getElementById("avito-gen-query")')
        has_pmin = await page.evaluate('!!document.getElementById("avito-gen-pmin")')
        has_pmax = await page.evaluate('!!document.getElementById("avito-gen-pmax")')
        has_btn = await page.evaluate('!!document.getElementById("btn-avito-gen-submit")')
        print(f'Modal elements check: query={has_query}, pmin={has_pmin}, pmax={has_pmax}, btn={has_btn}')

        # Test typing in the generator and checking live preview
        await page.fill('#avito-gen-query', 'RTX 3060')
        await page.fill('#avito-gen-pmin', '15000')
        await page.fill('#avito-gen-pmax', '25000')
        preview_text = await page.evaluate('document.getElementById("avito-gen-preview").innerText')
        print(f'Preview text: {preview_text}')

        # Take a screenshot to verify UI appearance
        await page.screenshot(path='screen_modal_test.png')
        print('Screenshot saved to screen_modal_test.png')

        await browser.close()

asyncio.run(main())
