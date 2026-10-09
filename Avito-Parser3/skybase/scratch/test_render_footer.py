import os
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options

svg_blue_circle_white_plane = '''<svg width="18" height="18" viewBox="0 0 24 24" fill="none" style="vertical-align:-3px;margin-right:4px;display:inline-block;" xmlns="http://www.w3.org/2000/svg">
  <circle cx="12" cy="12" r="12" fill="#24A1DE"/>
  <path fill="#ffffff" d="M5.4 12.015l3.962 1.48 1.536 4.704a.434.434 0 00.702.17l2.17-2.128 4.382 3.235c.483.356 1.159.102 1.266-.492L22.18 5.76c.113-.53-.423-.984-.943-.783L3.25 10.959c-.572.23-.554 1.052.067 1.252l2.077-.196zm4.12 1.047l8.28-5.187c.18-.113.37.14.21.284l-6.868 6.208-.28 3.525-1.342-4.83z"/>
</svg>'''

html_content = f'''<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <style>
    body {{
      background: #0f172a;
      color: #94a3b8;
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
      padding: 30px;
      font-size: 14px;
    }}
    .footer-preview {{
      background: #1e293b;
      border: 1px solid #334155;
      border-radius: 12px;
      padding: 16px 20px;
      text-align: center;
    }}
    a {{
      color: #38bdf8;
      text-decoration: none;
      font-weight: 700;
    }}
    .red-label {{
      color: #ef4444;
      font-weight: 700;
    }}
  </style>
</head>
<body>
  <div class="footer-preview">
    <p style="margin:0 0 8px 0;">
      Avito Bot &amp; Parser &copy; 2026. Мониторинг объявлений и Telegram-уведомления. Связь с администратором в {svg_blue_circle_white_plane}<span class="red-label">Telegram:</span> <a href="https://t.me/skynet19081983" target="_blank">@skynet19081983</a>
    </p>
    <p style="margin:0;">
      📬 <span class="red-label">Резервная почта:</span> <a href="mailto:skynet-system83@mail.ru">skynet-system83@mail.ru</a>
    </p>
  </div>
</body>
</html>'''

with open('scratch_footer_test.html', 'w', encoding='utf-8') as f:
    f.write(html_content)

opts = Options()
opts.binary_location = r'c:\ins\skybase\browsers\chromium-1243\chrome-win64\chrome.exe'
opts.add_argument('--headless')
opts.add_argument('--no-sandbox')
opts.add_argument('--disable-gpu')
opts.add_argument('--window-size=900,400')

driver = webdriver.Chrome(options=opts)
try:
    abs_path = os.path.abspath('scratch_footer_test.html')
    driver.get(f'file:///{abs_path}')
    driver.save_screenshot('scratch_footer_test.png')
    print('Screenshot saved successfully!')
finally:
    driver.quit()
