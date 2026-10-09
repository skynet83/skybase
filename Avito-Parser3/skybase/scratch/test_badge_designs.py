import asyncio
from playwright.async_api import async_playwright

DESIGNS = {
    # Design 1: Digital Segmented LCD with clean sub-labels (ДД.ММ.ГГГГ • ЧЧ:ММ:СС)
    "design_1_lcd_sub": """<div style="display:inline-flex;flex-direction:column;align-items:center;justify-content:center;line-height:1.2;padding:2px 4px;">
      <div style="font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;font-size:13.5px;font-weight:800;letter-spacing:1px;color:#fbbf24;display:flex;align-items:center;text-shadow:0 0 8px rgba(251,191,36,0.3);">
        <span style="background:rgba(251,191,36,0.1);padding:1px 5px;border-radius:4px;border:1px solid rgba(251,191,36,0.25);">--</span>
        <span style="color:#64748b;margin:0 2px;font-weight:900;">.</span>
        <span style="background:rgba(251,191,36,0.1);padding:1px 5px;border-radius:4px;border:1px solid rgba(251,191,36,0.25);">--</span>
        <span style="color:#64748b;margin:0 2px;font-weight:900;">.</span>
        <span style="background:rgba(251,191,36,0.1);padding:1px 6px;border-radius:4px;border:1px solid rgba(251,191,36,0.25);">----</span>
        <span style="color:#38bdf8;margin:0 6px;font-size:11px;">•</span>
        <span style="background:rgba(251,191,36,0.1);padding:1px 5px;border-radius:4px;border:1px solid rgba(251,191,36,0.25);">--</span>
        <span style="color:#64748b;margin:0 2px;font-weight:900;">:</span>
        <span style="background:rgba(251,191,36,0.1);padding:1px 5px;border-radius:4px;border:1px solid rgba(251,191,36,0.25);">--</span>
        <span style="color:#64748b;margin:0 2px;font-weight:900;">:</span>
        <span style="background:rgba(251,191,36,0.1);padding:1px 5px;border-radius:4px;border:1px solid rgba(251,191,36,0.25);">--</span>
      </div>
      <div style="font-size:8px;font-weight:800;color:#94a3b8;letter-spacing:1.8px;text-transform:uppercase;margin-top:4px;">
        ДД . ММ . ГГГГ &nbsp;&bull;&nbsp; ЧЧ : ММ : СС
      </div>
    </div>""",

    # Design 2: Calendar & Clock pill with format hints
    "design_2_pill": """<div style="display:inline-flex;align-items:center;gap:6px;padding:2px 2px;">
      <span style="font-size:13px;opacity:0.9;">⏳</span>
      <div style="display:inline-flex;align-items:center;font-family:ui-monospace,Consolas,monospace;font-size:13px;font-weight:800;">
        <span style="color:#fbbf24;background:rgba(251,191,36,0.12);padding:2px 6px;border-radius:4px;border:1px solid rgba(251,191,36,0.25);">ДД.ММ.ГГГГ</span>
        <span style="color:#64748b;margin:0 5px;font-size:10px;">•</span>
        <span style="color:#fbbf24;background:rgba(251,191,36,0.12);padding:2px 6px;border-radius:4px;border:1px solid rgba(251,191,36,0.25);">ЧЧ:ММ:СС</span>
      </div>
    </div>""",

    # Design 3: Hybrid: "--" dashes with mini micro-badges (ДД, ММ, ГГГГ, ЧЧ, ММ, СС)
    "design_3_micro_slots": """<div style="display:inline-flex;align-items:center;gap:3px;padding:1px 2px;">
      <div style="display:flex;flex-direction:column;align-items:center;"><span style="font-family:ui-monospace,Consolas,monospace;font-size:12.5px;font-weight:800;color:#fbbf24;background:rgba(15,23,42,0.9);border:1px solid rgba(251,191,36,0.3);border-radius:4px;padding:1px 5px;">--</span><span style="font-size:7px;font-weight:800;color:#64748b;text-transform:uppercase;margin-top:2px;">ДД</span></div>
      <span style="color:#64748b;font-weight:900;font-size:12px;margin-bottom:9px;">.</span>
      <div style="display:flex;flex-direction:column;align-items:center;"><span style="font-family:ui-monospace,Consolas,monospace;font-size:12.5px;font-weight:800;color:#fbbf24;background:rgba(15,23,42,0.9);border:1px solid rgba(251,191,36,0.3);border-radius:4px;padding:1px 5px;">--</span><span style="font-size:7px;font-weight:800;color:#64748b;text-transform:uppercase;margin-top:2px;">ММ</span></div>
      <span style="color:#64748b;font-weight:900;font-size:12px;margin-bottom:9px;">.</span>
      <div style="display:flex;flex-direction:column;align-items:center;"><span style="font-family:ui-monospace,Consolas,monospace;font-size:12.5px;font-weight:800;color:#fbbf24;background:rgba(15,23,42,0.9);border:1px solid rgba(251,191,36,0.3);border-radius:4px;padding:1px 6px;">----</span><span style="font-size:7px;font-weight:800;color:#64748b;text-transform:uppercase;margin-top:2px;">ГГГГ</span></div>
      <span style="color:#38bdf8;font-size:10px;margin:0 3px;margin-bottom:9px;">•</span>
      <div style="display:flex;flex-direction:column;align-items:center;"><span style="font-family:ui-monospace,Consolas,monospace;font-size:12.5px;font-weight:800;color:#fbbf24;background:rgba(15,23,42,0.9);border:1px solid rgba(251,191,36,0.3);border-radius:4px;padding:1px 5px;">--</span><span style="font-size:7px;font-weight:800;color:#64748b;text-transform:uppercase;margin-top:2px;">ЧЧ</span></div>
      <span style="color:#64748b;font-weight:900;font-size:12px;margin-bottom:9px;">:</span>
      <div style="display:flex;flex-direction:column;align-items:center;"><span style="font-family:ui-monospace,Consolas,monospace;font-size:12.5px;font-weight:800;color:#fbbf24;background:rgba(15,23,42,0.9);border:1px solid rgba(251,191,36,0.3);border-radius:4px;padding:1px 5px;">--</span><span style="font-size:7px;font-weight:800;color:#64748b;text-transform:uppercase;margin-top:2px;">ММ</span></div>
      <span style="color:#64748b;font-weight:900;font-size:12px;margin-bottom:9px;">:</span>
      <div style="display:flex;flex-direction:column;align-items:center;"><span style="font-family:ui-monospace,Consolas,monospace;font-size:12.5px;font-weight:800;color:#fbbf24;background:rgba(15,23,42,0.9);border:1px solid rgba(251,191,36,0.3);border-radius:4px;padding:1px 5px;">--</span><span style="font-size:7px;font-weight:800;color:#64748b;text-transform:uppercase;margin-top:2px;">СС</span></div>
    </div>"""
}

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            executable_path=r'C:\ins\skybase\browsers\chromium-1243\chrome-win64\chrome.exe'
        )
        page = await browser.new_page(viewport={'width': 1280, 'height': 800})
        await page.goto('http://localhost:8080/', timeout=10000)
        await page.wait_for_timeout(1000)

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
        await page.wait_for_timeout(600)

        for name, html in DESIGNS.items():
            await page.evaluate(f"""(htmlContent) => {{
                const el = document.getElementById('modal-tariff-display-text');
                if (el) {{
                    el.innerHTML = htmlContent;
                    el.style.background = '#0d1522';
                    el.style.border = '1.5px solid #24354c';
                    el.style.padding = '0.35rem 0.75rem';
                }}
            }}""", html)
            await page.wait_for_timeout(300)
            
            # Screenshot modal header or element
            target = await page.query_selector('#modal-tariff-display-text')
            if target:
                await target.screenshot(path=f'C:\\ins\\skybase\\scratch\\{name}_badge.png')
            modal = await page.query_selector('#modal-container')
            if modal:
                await modal.screenshot(path=f'C:\\ins\\skybase\\scratch\\{name}_modal.png')
            print(f'Screenshots saved for {name}')

        await browser.close()

asyncio.run(main())
