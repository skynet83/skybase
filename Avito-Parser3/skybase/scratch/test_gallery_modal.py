import asyncio
from playwright.async_api import async_playwright

async def main():
    print("=== STARTING PRODUCT MODAL & GALLERY E2E TEST ===")
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1400, "height": 900})
        page = await context.new_page()
        page.on('console', lambda msg: print(f'[PAGE LOG] {msg.text}'))
        page.on('pageerror', lambda err: print(f'[PAGE ERROR] {err}'))

        # 1. Set localStorage before loading page
        await page.add_init_script("""
            localStorage.setItem('skybase_device_id', 'EBID-1AEC-084C-7AE5-B16D-FABF');
            localStorage.setItem('skybase_user', JSON.stringify({
                username: 'EBID-1AEC-084C-7AE5-B16D-FABF',
                request_id: 'EBID-1AEC-084C-7AE5-B16D-FABF',
                name: 'ПК-EBID-1AEC-084C',
                role: 'admin',
                permissions: {
                    avito: true,
                    avito_bot: true,
                    is_expired: false,
                    active_key: 'EB30-06AD-FF1F-B9A3-9E97',
                    monitoring: true,
                    tg_bot: true
                }
            }));
            localStorage.setItem('skybase_license_agreed_v2', '1');
            localStorage.setItem('skybase_license_agreed', '1');
        """)

        print("Navigating to http://localhost/ ...")
        await page.goto("http://localhost/", wait_until="domcontentloaded")
        await page.wait_for_timeout(2000)

        # 2. Wait for .avito-card
        await page.wait_for_selector(".avito-card, .avito-card-thumb-wrap", timeout=8000)
        cards = await page.query_selector_all(".avito-card")
        print(f"Found {len(cards)} .avito-card elements on page.")
        assert len(cards) > 0, "No .avito-card found!"

        # 3. Click the thumbnail wrap to open gallery modal
        thumb_wrap = await page.query_selector(".avito-card-thumb-wrap")
        assert thumb_wrap is not None, "Thumb wrap not found!"
        await thumb_wrap.click()

        # 4. Wait for modal to open
        await page.wait_for_selector("#modal-overlay.open", timeout=5000)
        print("Product modal opened successfully.")
        await page.wait_for_timeout(1000)

        # 5. Check close buttons count: there must be EXACTLY 1 close button
        close_buttons = await page.query_selector_all("#modal-overlay button:has-text('✕'), #modal-overlay button:has-text('×'), #modal-overlay #modal-close")
        visible_close_btns = []
        for btn in close_buttons:
            if await btn.is_visible():
                visible_close_btns.append(btn)
        print(f"Visible close buttons in modal: {len(visible_close_btns)}")
        assert len(visible_close_btns) == 1, f"Expected exactly 1 close button, found {len(visible_close_btns)}!"
        print("TEST 1 PASSED: Only 1 close button present (second smaller cross is removed).")

        # 6. Wait for details to load all photos
        print("Waiting for gallery photos to load...")
        try:
            await page.wait_for_selector("#gallery-nav-prev:visible", timeout=12000)
            print("Gallery navigation arrows are now visible!")
        except Exception as e:
            print("Timeout waiting for #gallery-nav-prev:visible, checking active photos...")
            photos_info = await page.evaluate("() => ({ photos: window._activeGalleryPhotos, pill: document.getElementById('gallery-counter-pill')?.innerText })")
            print("Debug photos info:", photos_info)
            raise e

        counter_pill = await page.query_selector("#gallery-counter-pill")
        assert counter_pill is not None, "Counter pill #gallery-counter-pill not found!"
        counter_text = (await counter_pill.inner_text()).strip()
        print(f"Gallery counter text: '{counter_text}'")

        prev_btn = await page.query_selector("#gallery-nav-prev")
        next_btn = await page.query_selector("#gallery-nav-next")
        assert prev_btn is not None, "Prev arrow #gallery-nav-prev not found!"
        assert next_btn is not None, "Next arrow #gallery-nav-next not found!"

        assert await prev_btn.is_visible(), "Prev arrow is not visible!"
        assert await next_btn.is_visible(), "Next arrow is not visible!"
        print("Navigation arrows are visible.")

        # 7. Check arrow styling and positioning
        prev_box = await prev_btn.bounding_box()
        next_box = await next_btn.bounding_box()
        stage_box = await (await page.query_selector("#gallery-stage-box")).bounding_box()

        print(f"Stage box: left={stage_box['x']}, right={stage_box['x']+stage_box['width']}, top={stage_box['y']}, height={stage_box['height']}")
        print(f"Prev arrow box: left={prev_box['x']}, top={prev_box['y']}")
        print(f"Next arrow box: left={next_box['x']}, top={next_box['y']}")

        left_offset = prev_box['x'] - stage_box['x']
        right_offset = (stage_box['x'] + stage_box['width']) - (next_box['x'] + next_box['width'])
        print(f"Left arrow offset from stage edge: {left_offset:.1f}px")
        print(f"Right arrow offset from stage edge: {right_offset:.1f}px")
        assert 5 <= left_offset <= 28, f"Left offset {left_offset} is not within expected range (5-28px)"
        assert 5 <= right_offset <= 28, f"Right offset {right_offset} is not within expected range (5-28px)"

        # Check vertical center alignment
        stage_center_y = stage_box['y'] + stage_box['height'] / 2
        prev_center_y = prev_box['y'] + prev_box['height'] / 2
        assert abs(stage_center_y - prev_center_y) < 15, "Prev arrow is not vertically centered!"
        print("TEST 2A PASSED: Arrows are properly positioned at vertical center with small offset.")

        # Check arrow styles (semi-transparent white)
        prev_bg = await prev_btn.evaluate("el => window.getComputedStyle(el).backgroundColor")
        prev_color = await prev_btn.evaluate("el => window.getComputedStyle(el).color")
        print(f"Arrow computed background: {prev_bg}, color: {prev_color}")
        assert "255, 255, 255" in prev_bg or "rgba(" in prev_bg, "Arrow is not semi-transparent white!"

        # Hover over next arrow and verify hover illumination
        await next_btn.hover()
        await page.wait_for_timeout(300)
        hover_shadow = await next_btn.evaluate("el => window.getComputedStyle(el).boxShadow")
        print(f"Arrow hover box shadow (highlight/illumination): {hover_shadow}")
        assert "rgb(255, 255, 255)" in hover_shadow or "255, 255, 255" in hover_shadow, "Hover illumination effect not found!"
        print("TEST 2B PASSED: Arrow is semi-transparent white and illuminates on hover.")

        # 8. Test sliding right (next photo)
        main_img = await page.query_selector("#gallery-modal-main-img")
        img_src_1 = await main_img.get_attribute("src")

        print("Clicking NEXT arrow...")
        await next_btn.click()
        await page.wait_for_timeout(400)
        counter_text_2 = (await counter_pill.inner_text()).strip()
        img_src_2 = await main_img.get_attribute("src")
        print(f"Counter after next: '{counter_text_2}'")
        assert "Фото 2" in counter_text_2, f"Expected 'Фото 2', got '{counter_text_2}'"
        assert img_src_1 != img_src_2, "Image source did not change after next click!"
        print("TEST 2C PASSED: Sliding right changes photo and updates counter.")

        # 9. Test returning left (prev photo)
        print("Clicking PREV arrow...")
        await prev_btn.click()
        await page.wait_for_timeout(400)
        counter_text_3 = (await counter_pill.inner_text()).strip()
        img_src_3 = await main_img.get_attribute("src")
        print(f"Counter after prev: '{counter_text_3}'")
        assert "Фото 1" in counter_text_3, f"Expected 'Фото 1', got '{counter_text_3}'"
        assert img_src_3 == img_src_1, "Did not return to the first photo!"
        print("TEST 2D PASSED: Sliding left returns to previous photo.")

        # 10. Test keyboard arrow keys
        print("Testing ArrowRight key...")
        await page.keyboard.press("ArrowRight")
        await page.wait_for_timeout(400)
        counter_text_key = (await counter_pill.inner_text()).strip()
        assert "Фото 2" in counter_text_key, f"Expected 'Фото 2' via keyboard, got '{counter_text_key}'"

        print("Testing ArrowLeft key...")
        await page.keyboard.press("ArrowLeft")
        await page.wait_for_timeout(400)
        counter_text_key2 = (await counter_pill.inner_text()).strip()
        assert "Фото 1" in counter_text_key2, f"Expected 'Фото 1' via keyboard, got '{counter_text_key2}'"
        print("TEST 2E PASSED: Keyboard ArrowLeft / ArrowRight navigation works perfectly.")

        # 11. Test thumbnail direct click
        thumbs = await page.query_selector_all(".gallery-thumb-item")
        if len(thumbs) > 2:
            print(f"Testing direct click on 3rd thumbnail (found {len(thumbs)} thumbnails)...")
            await thumbs[2].click()
            await page.wait_for_timeout(300)
            counter_text_t3 = (await counter_pill.inner_text()).strip()
            print(f"Counter after 3rd thumbnail click: '{counter_text_t3}'")
            assert "Фото 3" in counter_text_t3, f"Expected 'Фото 3', got '{counter_text_t3}'"
            print("TEST 2F PASSED: Thumbnail click navigates directly to photo.")

        # 12. Test closing modal
        print("Closing modal with main close button...")
        main_close = await page.query_selector("#modal-close")
        await main_close.click()
        await page.wait_for_timeout(600)
        is_open = await page.evaluate("() => document.getElementById('modal-overlay').classList.contains('open')")
        assert not is_open, "Modal is still open after clicking close!"
        print("TEST 3 PASSED: Modal closes cleanly with single close button.")

        print("=== ALL PRODUCT MODAL & GALLERY E2E TESTS PASSED SUCCESSFULLY! ===")
        await browser.close()

if __name__ == '__main__':
    asyncio.run(main())
