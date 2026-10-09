import re

with open('js/app.js', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Let's use Playwright to find which function has syntax error
# We can find all top-level functions or blocks
import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            executable_path=r'C:\ins\skybase\browsers\chromium-1243\chrome-win64\chrome.exe'
        )
        page = await browser.new_page()

        # Let's test chunks
        # Divide file into sections
        step = 500
        for i in range(10000, len(lines), 100):
            chunk = "".join(lines[:i])
            # see if we can close open scopes
            pass

        # Better yet: test each function definition individually!
        func_regex = re.compile(r'^(window\.[a-zA-Z0-9_$]+\s*=\s*(?:async\s+)?function|function\s+[a-zA-Z0-9_$]+)', re.M)
        matches = list(func_regex.finditer("".join(lines)))
        print(f"Total top-level functions found: {len(matches)}")
        
        full_text = "".join(lines)
        for idx in range(len(matches)):
            start = matches[idx].start()
            end = matches[idx+1].start() if idx + 1 < len(matches) else len(full_text)
            fn_code = full_text[start:end].strip()
            # remove trailing semicolons or comments
            res = await page.evaluate('''code => {
                try {
                    new Function(code);
                    return null;
                } catch(e) {
                    return e.message;
                }
            }''', fn_code)
            if res:
                fn_name = matches[idx].group(0)
                line_no = full_text[:start].count('\n') + 1
                print(f"ERROR in {fn_name} at line {line_no}: {res}")
                # print first 5 lines of function
                for l in fn_code.splitlines()[:10]:
                    print("  >", l)
                print("---")

        await browser.close()

asyncio.run(main())
