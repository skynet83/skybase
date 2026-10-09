import asyncio
import json
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            executable_path=r'C:\ins\Avito-Parser2\skybase\browsers\chromium-1243\chrome-win64\chrome.exe'
        )
        page = await browser.new_page(viewport={'width': 1600, 'height': 900})
        
        user_data = {
            "username": "EBID-1AEC-084C-7AE5-B16D-FABF",
            "request_id": "EBID-1AEC-084C-7AE5-B16D-FABF",
            "role": "admin",
            "permissions": {
                "avito": True,
                "avito_bot": True,
                "avito_duration": "30_days",
                "avito_expires_at": "2026-10-03 23:59:00",
                "is_expired": False,
                "monitoring": True,
                "tg_bot": True
            },
            "session_token": "ea19269b75404aa9a4791e747a67f302"
        }
        
        await page.add_init_script(f"""
            localStorage.setItem('skybase_user', JSON.stringify({json.dumps(user_data)}));
            localStorage.setItem('skybase_session_token', 'ea19269b75404aa9a4791e747a67f302');
        """)
        
        await page.goto('http://localhost/', timeout=10000)
        await page.wait_for_timeout(2500)
        
        info = await page.evaluate("""() => {
            const getBox = id => {
                const el = document.getElementById(id);
                if (!el) return null;
                const r = el.getBoundingClientRect();
                const cs = window.getComputedStyle(el);
                return {
                    id,
                    left: Math.round(r.left),
                    right: Math.round(r.right),
                    width: Math.round(r.width),
                    marginLeft: cs.marginLeft,
                    marginRight: cs.marginRight
                };
            };
            const parent = document.querySelector('.avito-dashboard-banner-stats');
            const parentCs = parent ? window.getComputedStyle(parent) : null;
            const parentRect = parent ? parent.getBoundingClientRect() : null;
            
            const bannerHeader = document.querySelector('.avito-dashboard-banner-header');
            const bannerHeaderRect = bannerHeader ? bannerHeader.getBoundingClientRect() : null;
            
            const switchesBar = document.querySelector('.avito-switches-bar');
            const switchesBarRect = switchesBar ? switchesBar.getBoundingClientRect() : null;

            return {
                parentGap: parentCs ? parentCs.gap : null,
                parentRect: parentRect ? { left: Math.round(parentRect.left), right: Math.round(parentRect.right), width: Math.round(parentRect.width) } : null,
                bannerHeaderRect: bannerHeaderRect ? { left: Math.round(bannerHeaderRect.left), right: Math.round(bannerHeaderRect.right), width: Math.round(bannerHeaderRect.width) } : null,
                switchesBarRect: switchesBarRect ? { left: Math.round(switchesBarRect.left), right: Math.round(switchesBarRect.right), width: Math.round(switchesBarRect.width) } : null,
                cart: getBox('btn-avito-cart'),
                sniper: getBox('btn-avito-sniper-main'),
                tariff: getBox('pill-avito-tariff'),
                activate: getBox('btn-avito-activate'),
                total: getBox('pill-avito-total'),
                searches: getBox('pill-avito-searches'),
                timer: getBox('btn-avito-timer')
            };
        }""")
        print('INFO:', json.dumps(info, indent=2))
        
        banner = await page.query_selector('.avito-dashboard-banner')
        if banner:
            await banner.screenshot(path=r'C:\ins\Avito-Parser2\skybase\scratch\scratch_banner.png')
            print('Banner screenshot saved')
        else:
            await page.screenshot(path=r'C:\ins\Avito-Parser2\skybase\scratch\scratch_full2.png')
            print('Full screenshot saved')
        await browser.close()

asyncio.run(main())
