import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            executable_path=r'C:\ins\skybase\browsers\chromium-1243\chrome-win64\chrome.exe'
        )
        page = await browser.new_page(viewport={'width': 1280, 'height': 800})
        print('Navigating to http://localhost:8080/ ...')
        await page.goto('http://localhost:8080/', timeout=10000)
        await page.wait_for_timeout(1500)

        # Open activation modal with unactivated status
        await page.evaluate("""() => {
            window.currentUser = { role: 'user', permissions: {} };
            window.openActivationModal({
                tariff_label: 'Требуется активация',
                duration: 'unactivated',
                expires_at: '',
                active_key: ''
            });
        }""")
        await page.wait_for_timeout(1000)

        modal = await page.query_selector('.modal-content, [id*="activation"], #modal-container')
        if modal:
            await modal.screenshot(path=r'C:\ins\skybase\scratch\current_modal_badge.png')
            print('Modal screenshot saved!')
        else:
            await page.screenshot(path=r'C:\ins\skybase\scratch\current_modal_badge.png')
            print('Full screenshot saved!')

        await browser.close()

asyncio.run(main())
