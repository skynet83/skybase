"""
Конфигурация Telegram-бота мониторинга Avito.
"""
import os

# Токен вашего Telegram-бота (из help.txt / BotFather)
BOT_TOKEN = os.getenv("BOT_TOKEN", "8501191397:AAHwEhKIn745c2XocTq-WX_lcXMEEqsSjeg")

# Ваш Telegram Chat ID для получения уведомлений и управления (из program/data.ini)
# Если 0 или None - бот автоматически привяжет ID первого пользователя, приславшего /start
ADMIN_CHAT_ID = int(os.getenv("ADMIN_CHAT_ID", "5680198246"))
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "skynet19081983").lstrip("@")

# Интервал проверки поисковых ссылок: по умолчанию 1 секунда (максимальная скорость)
CHECK_INTERVAL_SECONDS = 1

# Случайный разброс (джиттер) для интервала проверки в секундах
CHECK_INTERVAL_JITTER = 0

# Пауза между проверкой отдельных поисковых ссылок (секунды)
PAUSE_BETWEEN_REQUESTS = 0.5

# Прокси для парсинга Avito (None, если не используется, либо "http://user:pass@host:port")
AVITO_PROXY = None

# Путь к файлу со списком прокси для ротации (каждый прокси с новой строки: http://user:pass@ip:port)
PROXIES_FILE = os.path.join(os.path.dirname(__file__), "proxies.txt")

# Прокси для Telegram (None для прямого подключения, либо задать через переменную TELEGRAM_PROXY)
TELEGRAM_PROXY = os.getenv("TELEGRAM_PROXY", "http://85.8.47.207:7080")

# Базовые поисковые ссылки по умолчанию (видеокарты из help.txt)
DEFAULT_SEARCH_URLS = [
    {
        "name": "RX 580 (500-2000р)",
        "url": "https://www.avito.ru/all/tovary_dlya_kompyutera/komplektuyuschie/videokarty-ASgBAgICAkTGB~pm7gmmZw?cd=1&f=ASgBAgECAkTGB~pm7gmmZwFFxpoMFnsiZnJvbSI6NTAwLCJ0byI6MjAwMH0&q=rx580"
    },
    {
        "name": "RX 570 (500-2000р)",
        "url": "https://www.avito.ru/all/tovary_dlya_kompyutera/komplektuyuschie/videokarty-ASgBAgICAkTGB~pm7gmmZw?cd=1&f=ASgBAgECAkTGB~pm7gmmZwFFxpoMFnsiZnJvbSI6NTAwLCJ0byI6MjAwMH0&q=rx570"
    },
    {
        "name": "RX 480 (500-2000р)",
        "url": "https://www.avito.ru/all/tovary_dlya_kompyutera/komplektuyuschie/videokarty-ASgBAgICAkTGB~pm7gmmZw?cd=1&f=ASgBAgECAkTGB~pm7gmmZwFFxpoMFnsiZnJvbSI6NTAwLCJ0byI6MjAwMH0&q=rx480"
    },
    {
        "name": "RX 470 (500-2000р)",
        "url": "https://www.avito.ru/all/tovary_dlya_kompyutera/komplektuyuschie/videokarty-ASgBAgICAkTGB~pm7gmmZw?cd=1&f=ASgBAgECAkTGB~pm7gmmZwFFxpoMFnsiZnJvbSI6NTAwLCJ0byI6MjAwMH0&q=rx470"
    }
]

# Путь к файлу базы данных SQLite
DATABASE_PATH = os.path.join(os.path.dirname(__file__), "avito_bot.db")
