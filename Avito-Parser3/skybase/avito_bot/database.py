"""
Модуль для работы с локальной базой данных SQLite.
Поддерживает мультисессионность: у каждого пользователя (user_id) свой персональный набор поисков.
"""
import aiosqlite
import re
import logging
from typing import List, Dict, Optional, Any
from config import DATABASE_PATH, DEFAULT_SEARCH_URLS

logger = logging.getLogger(__name__)


async def init_db():
    """Инициализация таблиц базы данных с поддержкой мультипользовательской изоляции."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("PRAGMA journal_mode = WAL")
        await db.execute("PRAGMA synchronous = NORMAL")
        await db.execute("PRAGMA busy_timeout = 10000")
        # --- Автомиграция: проверяем схему seen_items ---
        async with db.execute("PRAGMA table_info(seen_items)") as cursor:
            columns = [row[1] for row in await cursor.fetchall()]
        if columns and "user_id" not in columns:
            logger.warning("Обнаружена старая схема БД (без user_id). Выполняется миграция...")
            await db.execute("DROP TABLE IF EXISTS seen_items")
            await db.execute("DROP TABLE IF EXISTS tracked_urls")
            await db.commit()
            logger.info("Старые таблицы удалены. Будут созданы новые с мультисессионной схемой.")

        # Таблица уже просмотренных/отправленных объявлений (изолированно для каждого пользователя)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS seen_items (
                user_id INTEGER,
                item_id TEXT,
                title TEXT,
                price TEXT,
                url TEXT,
                seen_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                photo TEXT,
                seller TEXT,
                address TEXT,
                search_name TEXT,
                PRIMARY KEY (user_id, item_id)
            )
        """)

        # Миграция: проверяем наличие новых колонок в seen_items
        async with db.execute("PRAGMA table_info(seen_items)") as cursor:
            s_columns = [row[1] for row in await cursor.fetchall()]
        for col, col_def in [
            ("photo", "TEXT"),
            ("seller", "TEXT"),
            ("address", "TEXT"),
            ("search_name", "TEXT"),
            ("has_delivery", "INTEGER DEFAULT 0"),
            ("has_chat", "INTEGER DEFAULT 1"),
            ("seller_type", "TEXT DEFAULT 'Частное лицо'"),
            ("item_date", "TEXT"),
            ("notified_tg", "INTEGER DEFAULT 1"),
            ("seller_rating", "TEXT"),
            ("photos", "TEXT")
        ]:
            if s_columns and col not in s_columns:
                await db.execute(f"ALTER TABLE seen_items ADD COLUMN {col} {col_def}")

        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_seen_user_item ON seen_items(user_id, item_id)
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS deleted_items (
                item_id TEXT PRIMARY KEY,
                deleted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Постоянная история отправленных в Telegram объявлений:
        # гарантирует, что ни при каких обстоятельствах старое объявление не отправится повторно в ТГ
        await db.execute("""
            CREATE TABLE IF NOT EXISTS notified_tg_history (
                user_id INTEGER,
                item_id TEXT,
                notified_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, item_id)
            )
        """)

        # Первичное наполнение истории из уже существующих записей seen_items
        try:
            await db.execute("""
                INSERT OR IGNORE INTO notified_tg_history (user_id, item_id)
                SELECT user_id, item_id FROM seen_items
            """)
            await db.commit()
        except Exception:
            pass

        # Таблица персональных отслеживаемых ссылок поиска
        await db.execute("""
            CREATE TABLE IF NOT EXISTS tracked_urls (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                url TEXT NOT NULL,
                is_active INTEGER DEFAULT 1,
                is_initialized INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, url)
            )
        """)

        # Миграция: добавляем is_initialized если колонки нет в существующей таблице
        async with db.execute("PRAGMA table_info(tracked_urls)") as cursor:
            tu_columns = [row[1] for row in await cursor.fetchall()]
        if tu_columns and "is_initialized" not in tu_columns:
            await db.execute("ALTER TABLE tracked_urls ADD COLUMN is_initialized INTEGER DEFAULT 0")
            logger.info("Миграция tracked_urls: добавлена колонка is_initialized")
        if tu_columns and "last_polled_at" not in tu_columns:
            await db.execute("ALTER TABLE tracked_urls ADD COLUMN last_polled_at TEXT")
            logger.info("Миграция tracked_urls: добавлена колонка last_polled_at")
        if tu_columns and "autobuy" not in tu_columns:
            await db.execute("ALTER TABLE tracked_urls ADD COLUMN autobuy INTEGER DEFAULT 0")
        if tu_columns and "autoreserve" not in tu_columns:
            await db.execute("ALTER TABLE tracked_urls ADD COLUMN autoreserve INTEGER DEFAULT 0")
        if tu_columns and "max_price" not in tu_columns:
            await db.execute("ALTER TABLE tracked_urls ADD COLUMN max_price REAL DEFAULT 0")
        if tu_columns and "price_with_delivery" not in tu_columns:
            await db.execute("ALTER TABLE tracked_urls ADD COLUMN price_with_delivery INTEGER DEFAULT 1")
        if tu_columns and "min_rating" not in tu_columns:
            await db.execute("ALTER TABLE tracked_urls ADD COLUMN min_rating REAL DEFAULT 0")
        if tu_columns and "only_delivery" not in tu_columns:
            await db.execute("ALTER TABLE tracked_urls ADD COLUMN only_delivery INTEGER DEFAULT 0")
        if tu_columns and "is_pending" not in tu_columns:
            await db.execute("ALTER TABLE tracked_urls ADD COLUMN is_pending INTEGER DEFAULT 0")

        # Таблица пользователей и прав доступа
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                full_name TEXT,
                status TEXT DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Таблица избранных объявлений (bookmarks)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS favorites (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                item_id TEXT NOT NULL,
                title TEXT,
                price TEXT,
                url TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, item_id)
            )
        """)

        # Таблица черного списка продавцов (Blacklist)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS blacklist (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                seller_name TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, seller_name)
            )
        """)

        # Таблица персональных прокси пользователей
        await db.execute("""
            CREATE TABLE IF NOT EXISTS user_proxies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                proxy TEXT NOT NULL,
                is_alive INTEGER DEFAULT 1,
                last_checked TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, proxy)
            )
        """)

        # Миграция: добавляем user_id в deleted_items, если нет
        async with db.execute("PRAGMA table_info(deleted_items)") as cursor:
            d_columns = [row[1] for row in await cursor.fetchall()]
        if d_columns and "user_id" not in d_columns:
            await db.execute("ALTER TABLE deleted_items ADD COLUMN user_id INTEGER DEFAULT 0")
            logger.info("Миграция deleted_items: добавлена колонка user_id")

        # Миграция: добавляем silent_mode в users, если нет
        async with db.execute("PRAGMA table_info(users)") as cursor:
            u_columns = [row[1] for row in await cursor.fetchall()]
        if u_columns and "silent_mode" not in u_columns:
            await db.execute("ALTER TABLE users ADD COLUMN silent_mode INTEGER DEFAULT 0")
            logger.info("Миграция users: добавлена колонка silent_mode")

        # Таблица учета выданных триал-ключей по железу (HWID)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS hwid_trials (
                hwid TEXT PRIMARY KEY,
                client_name TEXT,
                telegram_id INTEGER,
                trial_key TEXT,
                ip_address TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at TEXT
            )
        """)

        await db.commit()


async def is_item_deleted(item_id: str, user_id: Optional[int] = None) -> bool:
    """Проверяет, было ли объявление удалено пользователем (находится в deleted_items и не в favorites)."""
    if not item_id:
        return False
    clean = str(item_id).strip()
    async with aiosqlite.connect(DATABASE_PATH) as db:
        try:
            if user_id:
                async with db.execute("SELECT 1 FROM favorites WHERE item_id = ? AND user_id = ? LIMIT 1", (clean, user_id)) as cursor:
                    if await cursor.fetchone():
                        return False
                async with db.execute("SELECT 1 FROM deleted_items WHERE item_id = ? AND (user_id = ? OR user_id = 0) LIMIT 1", (clean, user_id)) as cursor:
                    row = await cursor.fetchone()
                    return row is not None
            else:
                async with db.execute("SELECT 1 FROM favorites WHERE item_id = ? LIMIT 1", (clean,)) as cursor:
                    if await cursor.fetchone():
                        return False
                async with db.execute("SELECT 1 FROM deleted_items WHERE item_id = ? LIMIT 1", (clean,)) as cursor:
                    row = await cursor.fetchone()
                    return row is not None
        except Exception:
            return False


async def remove_deleted_item(item_id: str, user_id: Optional[int] = None):
    """Удаляет запись об исключении объявления из deleted_items."""
    if not item_id:
        return
    clean = str(item_id).strip()
    async with aiosqlite.connect(DATABASE_PATH) as db:
        if user_id:
            await db.execute("DELETE FROM deleted_items WHERE item_id = ? AND (user_id = ? OR user_id = 0)", (clean, user_id))
        else:
            await db.execute("DELETE FROM deleted_items WHERE item_id = ?", (clean,))
        await db.commit()


async def clear_deleted_items_by_search(search_name: str, user_id: Optional[int] = None):
    """Очищает список исключений (удаленных карточек) для конкретного поиска (например при первом сборе)."""
    if not search_name or not search_name.strip():
        return
    clean_name = search_name.strip()
    async with aiosqlite.connect(DATABASE_PATH) as db:
        if user_id:
            await db.execute("DELETE FROM deleted_items WHERE LOWER(search_name) = LOWER(?) AND (user_id = ? OR user_id = 0)", (clean_name, user_id))
        else:
            await db.execute("DELETE FROM deleted_items WHERE LOWER(search_name) = LOWER(?)", (clean_name,))
        await db.commit()


async def is_seen(user_id: int, item_id: str, ignore_deleted: bool = False) -> bool:
    """Проверяет, видел ли данный пользователь это объявление (или было ли оно удалено)."""
    if not item_id:
        return False
    clean = str(item_id).strip()
    async with aiosqlite.connect(DATABASE_PATH) as db:
        try:
            if not ignore_deleted:
                async with db.execute("SELECT 1 FROM favorites WHERE item_id = ? LIMIT 1", (clean,)) as f_cur:
                    is_fav = await f_cur.fetchone() is not None
                if not is_fav:
                    async with db.execute("SELECT 1 FROM deleted_items WHERE item_id = ? AND (user_id = ? OR user_id = 0) LIMIT 1", (clean, user_id)) as cursor:
                        if await cursor.fetchone():
                            return True
        except Exception:
            pass
        async with db.execute(
            "SELECT 1 FROM seen_items WHERE user_id = ? AND item_id = ?",
            (user_id, clean)
        ) as cursor:
            row = await cursor.fetchone()
            return row is not None


async def get_seen_price(user_id: int, item_id: str) -> Optional[str]:
    """Возвращает ранее сохранённую цену объявления для данного пользователя."""
    if not item_id:
        return None
    async with aiosqlite.connect(DATABASE_PATH) as db:
        async with db.execute(
            "SELECT price FROM seen_items WHERE user_id = ? AND item_id = ?",
            (user_id, str(item_id))
        ) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else None


async def get_total_seen_count(user_id: Optional[int] = None) -> int:
    """Возвращает общее число сохраненных объявлений в базе."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        if user_id is not None:
            async with db.execute("SELECT COUNT(*) FROM seen_items WHERE user_id = ? AND (item_id NOT IN (SELECT item_id FROM deleted_items) OR item_id IN (SELECT item_id FROM favorites))", (user_id,)) as cursor:
                row = await cursor.fetchone()
                return row[0] if row else 0
        else:
            async with db.execute("SELECT COUNT(*) FROM seen_items WHERE (item_id NOT IN (SELECT item_id FROM deleted_items) OR item_id IN (SELECT item_id FROM favorites))") as cursor:
                row = await cursor.fetchone()
                return row[0] if row else 0


async def update_seen_price(user_id: int, item_id: str, new_price: str):
    """Обновляет цену уже просмотренного объявления при её изменении."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            "UPDATE seen_items SET price = ?, seen_at = CURRENT_TIMESTAMP WHERE user_id = ? AND item_id = ?",
            (new_price, user_id, str(item_id))
        )
        await db.commit()


async def add_seen(user_id: int, item_id: str, title: str, price: str, url: str, photo: Optional[str] = None, photos: Optional[List[str] | str] = None, seller: Optional[str] = None, address: Optional[str] = None, search_name: Optional[str] = None, has_delivery: int = 0, seller_type: str = "Частное лицо", item_date: Optional[str] = None, notified_tg: int = 0, seller_rating: Optional[str] = None, is_first_run: bool = False, description: Optional[str] = None):
    """Добавляет объявление в список просмотренных для конкретного пользователя."""
    if not item_id:
        return
    clean = str(item_id).strip()
    photos_json = json.dumps(photos, ensure_ascii=False) if isinstance(photos, list) else (photos or None)
    async with aiosqlite.connect(DATABASE_PATH) as db:
        try:
            async with db.execute("SELECT 1 FROM favorites WHERE item_id = ? LIMIT 1", (clean,)) as f_cur:
                is_fav = await f_cur.fetchone() is not None
            if not is_fav:
                async with db.execute("SELECT 1 FROM deleted_items WHERE item_id = ? LIMIT 1", (clean,)) as cursor:
                    if await cursor.fetchone():
                        return
        except Exception:
            pass
        await db.execute(
            """INSERT OR IGNORE INTO seen_items 
               (user_id, item_id, title, price, url, photo, photos, description, seller, address, search_name, has_delivery, seller_type, item_date, seller_rating, notified_tg) 
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (user_id, str(item_id), title, price, url, photo, photos_json, description or "", seller, address, search_name, int(has_delivery), seller_type, item_date, seller_rating, int(notified_tg))
        )
        if photos_json:
            await db.execute(
                "UPDATE seen_items SET photos = ? WHERE user_id = ? AND item_id = ? AND (photos IS NULL OR photos = '' OR photos = '[]' OR LENGTH(photos) < LENGTH(?))",
                (photos_json, user_id, str(item_id), photos_json)
            )
        if seller_rating:
            await db.execute(
                "UPDATE seen_items SET seller_rating = ? WHERE user_id = ? AND item_id = ? AND (seller_rating IS NULL OR seller_rating = '')",
                (seller_rating, user_id, str(item_id))
            )
        if description:
            await db.execute(
                "UPDATE seen_items SET description = ? WHERE user_id = ? AND item_id = ? AND (description IS NULL OR description = '')",
                (description, user_id, str(item_id))
            )
        if item_date:
            await db.execute(
                "UPDATE seen_items SET item_date = ? WHERE user_id = ? AND item_id = ? AND (item_date IS NULL OR item_date = '' OR (item_date LIKE '%назад%' AND ? NOT LIKE '%назад%'))",
                (item_date, user_id, str(item_id), item_date)
            )
        await db.commit()


async def is_notified_tg(user_id: int, item_id: str) -> bool:
    """Проверяет, было ли объявление отправлено пользователю в Telegram."""
    if not item_id:
        return False
    async with aiosqlite.connect(DATABASE_PATH) as db:
        async with db.execute(
            "SELECT notified_tg FROM seen_items WHERE user_id = ? AND item_id = ?",
            (user_id, str(item_id))
        ) as cursor:
            row = await cursor.fetchone()
            return bool(row[0]) if row and row[0] is not None else False


async def set_notified_tg(user_id: int, item_id: str):
    """Отмечает объявление как отправленное в Telegram."""
    if not item_id:
        return
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            "UPDATE seen_items SET notified_tg = 1 WHERE user_id = ? AND item_id = ?",
            (user_id, str(item_id))
        )
        await db.commit()


async def update_seen_details_if_missing(user_id: int, item_id: str, photo: Optional[str] = None, seller: Optional[str] = None, address: Optional[str] = None, search_name: Optional[str] = None, has_delivery: Optional[int] = None, seller_type: Optional[str] = None, item_date: Optional[str] = None, seller_rating: Optional[str] = None):
    """Обновляет фото, продавца, адрес, имя поиска, доставку, тип продавца, дату или рейтинг продавца у ранее сохраненного объявления."""
    if not item_id:
        return
    async with aiosqlite.connect(DATABASE_PATH) as db:
        async with db.execute("SELECT photo, seller, address, search_name, has_delivery, seller_type, item_date, seller_rating FROM seen_items WHERE user_id = ? AND item_id = ?", (user_id, str(item_id))) as cursor:
            row = await cursor.fetchone()
        if row:
            db_photo, db_seller, db_address, db_search_name, db_has_delivery, db_seller_type, db_item_date, db_seller_rating = row
            updates = []
            params = []
            if photo and (not db_photo or db_photo == ""):
                updates.append("photo = ?")
                params.append(photo)
            if seller and (not db_seller or db_seller == ""):
                updates.append("seller = ?")
                params.append(seller)
            if address and (not db_address or db_address == ""):
                updates.append("address = ?")
                params.append(address)
            if search_name and (not db_search_name or db_search_name == ""):
                updates.append("search_name = ?")
                params.append(search_name)
            if has_delivery is not None and (db_has_delivery is None or db_has_delivery == 0):
                updates.append("has_delivery = ?")
                params.append(int(has_delivery))
            if seller_type and (not db_seller_type or db_seller_type == "Частное лицо"):
                updates.append("seller_type = ?")
                params.append(seller_type)
            if item_date and (not db_item_date or db_item_date == "" or ("назад" in db_item_date and "назад" not in item_date)):
                updates.append("item_date = ?")
                params.append(item_date)
            if seller_rating and (not db_seller_rating or db_seller_rating == ""):
                updates.append("seller_rating = ?")
                params.append(seller_rating)
            if updates:
                params.extend([user_id, str(item_id)])
                query = f"UPDATE seen_items SET {', '.join(updates)} WHERE user_id = ? AND item_id = ?"
                await db.execute(query, tuple(params))
                await db.commit()


async def delete_seen_item(item_id: str) -> bool:
    """Удаляет объявление из базы (например, если оно снято с продажи на Авито)."""
    if not item_id:
        return False
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cursor = await db.execute("DELETE FROM seen_items WHERE item_id = ?", (str(item_id),))
        await db.commit()
        return cursor.rowcount > 0


async def delete_seen_items_batch(item_ids: List[str]) -> int:
    """Пакетно удаляет список объявлений, снятых с продажи на Авито."""
    if not item_ids:
        return 0
    async with aiosqlite.connect(DATABASE_PATH) as db:
        placeholders = ",".join("?" for _ in item_ids)
        cursor = await db.execute(f"DELETE FROM seen_items WHERE item_id IN ({placeholders})", [str(x) for x in item_ids])
        await db.commit()
        return cursor.rowcount


async def cleanup_untracked_legacy_items() -> int:
    """Удаляет устаревшие объявления от старых тестовых поисков (например, PlayStation/Sega), которых больше нет в отслеживании."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cursor = await db.execute("""
            DELETE FROM seen_items 
            WHERE (search_name IS NULL OR search_name = '') 
              AND (
                LOWER(title) LIKE '%playstation%' OR 
                LOWER(title) LIKE '%sony%' OR 
                LOWER(title) LIKE '%ps4%' OR 
                LOWER(title) LIKE '%ps5%' OR 
                LOWER(title) LIKE '%sega%' OR 
                LOWER(title) LIKE '%dendy%'
              )
        """)
        await db.commit()
        return cursor.rowcount


async def get_user_tracked_urls(user_id: int) -> List[Dict]:
    """Возвращает все персональные ссылки пользователя (активные и сверх тарифа)."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT id, name, url, is_active, is_initialized, only_delivery FROM tracked_urls WHERE user_id = ? ORDER BY is_active DESC, id ASC",
            (user_id,)
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]


async def get_all_active_tasks() -> List[Dict]:
    """Возвращает список всех активных задач всех авторизованных пользователей."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        # Только для пользователей со статусом 'admin' или 'approved'
        async with db.execute("""
            SELECT t.id, t.user_id, t.name, t.url, t.is_initialized, t.last_polled_at, t.only_delivery, u.status 
            FROM tracked_urls t
            JOIN users u ON t.user_id = u.user_id
            WHERE t.is_active = 1 AND u.status IN ('admin', 'approved')
            ORDER BY (t.last_polled_at IS NOT NULL) ASC, t.last_polled_at ASC, t.id ASC
        """) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]


async def set_url_initialized(url_id: int):
    """Помечает поисковую ссылку как инициализированную (первичный снимок сделан)."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            "UPDATE tracked_urls SET is_initialized = 1, last_polled_at = datetime('now', 'localtime') WHERE id = ?",
            (url_id,)
        )
        await db.commit()


async def set_url_polled(url_id: int):
    """Обновляет время последнего опроса ссылки."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            "UPDATE tracked_urls SET last_polled_at = datetime('now', 'localtime'), is_initialized = 1 WHERE id = ?",
            (url_id,)
        )
        await db.commit()


async def add_user_tracked_url(user_id: int, url: str, name: Optional[str] = None) -> int:
    """Добавляет новую ссылку в персональный мониторинг пользователя."""
    clean_url = url.strip()
    if not name:
        name = f"Поиск #{clean_url[:30]}..."
    try:
        from filters import attach_price_suffix_to_name
        name = attach_price_suffix_to_name(name, clean_url)
    except Exception:
        pass
    async with aiosqlite.connect(DATABASE_PATH) as db:
        # Проверяем, существует ли уже такая ссылка у данного пользователя
        cursor = await db.execute(
            "SELECT id FROM tracked_urls WHERE user_id = ? AND url = ?",
            (user_id, clean_url)
        )
        existing_row = await cursor.fetchone()
        if not existing_row:
            # Ограничение количества создаваемых ссылок для поиска: максимум 10 шт.
            cursor = await db.execute(
                "SELECT COUNT(*) FROM tracked_urls WHERE user_id = ?",
                (user_id,)
            )
            count = (await cursor.fetchone())[0]
            if count >= 10:
                raise ValueError("Достигнут максимальный лимит: 10 поисковых ссылок!")

        cursor = await db.execute(
            "INSERT OR REPLACE INTO tracked_urls (user_id, name, url, is_active, is_initialized) VALUES (?, ?, ?, 1, 0)",
            (user_id, name, clean_url)
        )
        await db.commit()
        return cursor.lastrowid


async def delete_user_tracked_url(user_id: int, url_id: int) -> bool:
    """Удаляет персональную ссылку пользователя по ID."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cursor = await db.execute(
            "DELETE FROM tracked_urls WHERE id = ? AND user_id = ?",
            (url_id, user_id)
        )
        await db.commit()
        return cursor.rowcount > 0


async def seed_default_urls_for_user(user_id: int):
    """Добавляет базовые ссылки для нового пользователя, если у него еще нет поиска."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        async with db.execute("SELECT COUNT(*) FROM tracked_urls WHERE user_id = ?", (user_id,)) as cursor:
            count = (await cursor.fetchone())[0]
            if count == 0:
                for item in DEFAULT_SEARCH_URLS:
                    await db.execute(
                        "INSERT OR IGNORE INTO tracked_urls (user_id, name, url, is_initialized) VALUES (?, ?, ?, 0)",
                        (user_id, item["name"], item["url"])
                    )
                await db.commit()


# ================= Управление пользователями =================

async def get_user_status(user_id: int) -> Optional[str]:
    """Возвращает статус пользователя (admin, approved, pending, rejected)."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        async with db.execute("SELECT status FROM users WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else None


async def register_or_update_user(user_id: int, username: Optional[str], full_name: str, status: Optional[str] = None) -> str:
    """Регистрирует пользователя или обновляет профиль."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        async with db.execute("SELECT status FROM users WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            
        if row:
            current_status = row[0]
            if status:
                current_status = status
            await db.execute(
                "UPDATE users SET username = ?, full_name = ?, status = ?, updated_at = CURRENT_TIMESTAMP WHERE user_id = ?",
                (username or "", full_name, current_status, user_id)
            )
            await db.commit()
            return current_status
        else:
            new_status = status if status else "pending"
            await db.execute(
                "INSERT INTO users (user_id, username, full_name, status) VALUES (?, ?, ?, ?)",
                (user_id, username or "", full_name, new_status)
            )
            await db.commit()
            return new_status


async def set_user_status(user_id: int, status: str) -> bool:
    """Устанавливает статус пользователя (approved, rejected, admin)."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cursor = await db.execute(
            "UPDATE users SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE user_id = ?",
            (status, user_id)
        )
        await db.commit()
        return cursor.rowcount > 0


async def get_users_by_status(status: Optional[str] = None) -> List[Dict]:
    """Возвращает список пользователей."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        if status:
            query = "SELECT user_id, username, full_name, status, created_at FROM users WHERE status = ? ORDER BY created_at DESC"
            params = (status,)
        else:
            query = "SELECT user_id, username, full_name, status, created_at FROM users ORDER BY created_at DESC"
            params = ()
            
        async with db.execute(query, params) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]


async def get_stats() -> Dict:
    """Общая статистика системы."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        async with db.execute("SELECT COUNT(*) FROM seen_items") as cursor:
            seen_count = (await cursor.fetchone())[0]
        async with db.execute("SELECT COUNT(*) FROM tracked_urls WHERE is_active = 1") as cursor:
            urls_count = (await cursor.fetchone())[0]
        async with db.execute("SELECT COUNT(*) FROM users WHERE status IN ('admin', 'approved')") as cursor:
            clients_count = (await cursor.fetchone())[0]
        async with db.execute("SELECT COUNT(*) FROM users WHERE status = 'pending'") as cursor:
            pending_count = (await cursor.fetchone())[0]
        return {
            "seen_count": seen_count,
            "urls_count": urls_count,
            "clients_count": clients_count,
            "pending_count": pending_count
        }


async def delete_user_and_clean_data(user_id: int) -> Dict[str, int]:
    """
    Полностью удаляет пользователя и очищает все связанные с ним данные:
    - Персональные ссылки поиска (tracked_urls)
    - Историю сохраненных объявлений (seen_items)
    - Запись пользователя (users)
    - Выполняет VACUUM в SQLite для физического освобождения дискового пространства.
    """
    deleted_seen = 0
    deleted_urls = 0
    deleted_users = 0

    async with aiosqlite.connect(DATABASE_PATH) as db:
        # 1. Удаляем сохраненные объявления пользователя
        cursor_seen = await db.execute("DELETE FROM seen_items WHERE user_id = ?", (user_id,))
        deleted_seen = cursor_seen.rowcount

        # 2. Удаляем персональные поисковые ссылки
        cursor_urls = await db.execute("DELETE FROM tracked_urls WHERE user_id = ?", (user_id,))
        deleted_urls = cursor_urls.rowcount

        # 3. Удаляем самого пользователя
        cursor_user = await db.execute("DELETE FROM users WHERE user_id = ?", (user_id,))
        deleted_users = cursor_user.rowcount

        await db.commit()

        # 4. Освобождаем дисковое пространство (сжатие файла базы данных SQLite)
        await db.execute("VACUUM")

    return {
        "deleted_seen": deleted_seen,
        "deleted_urls": deleted_urls,
        "deleted_users": deleted_users
    }


# ================= Избранное (Favorites) =================

async def add_favorite(user_id: int, item_id: str, title: str, price: str, url: str) -> bool:
    """Добавляет объявление в избранное пользователя."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        try:
            await db.execute(
                "INSERT OR REPLACE INTO favorites (user_id, item_id, title, price, url) VALUES (?, ?, ?, ?, ?)",
                (user_id, str(item_id), title, price, url)
            )
            await db.commit()
            return True
        except Exception:
            return False


async def remove_favorite(user_id: int, item_id: str) -> bool:
    """Удаляет объявление из избранного пользователя."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cursor = await db.execute(
            "DELETE FROM favorites WHERE user_id = ? AND item_id = ?",
            (user_id, str(item_id))
        )
        await db.commit()
        return cursor.rowcount > 0


async def get_user_favorites(user_id: int) -> List[Dict]:
    """Возвращает список избранных объявлений пользователя."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT item_id, title, price, url, created_at FROM favorites WHERE user_id = ? ORDER BY created_at DESC",
            (user_id,)
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]


# ================= Черный список (Blacklist) =================

async def add_to_blacklist(user_id: int, seller_name: str, city: Optional[str] = None) -> bool:
    """Добавляет имя продавца в черный список пользователя."""
    if not seller_name:
        return False
    clean_seller = seller_name.strip().lower()
    if city and "@" not in clean_seller:
        key = f"{clean_seller}@{city.strip().lower()}"
    else:
        key = clean_seller
    async with aiosqlite.connect(DATABASE_PATH) as db:
        try:
            await db.execute(
                "INSERT OR IGNORE INTO blacklist (user_id, seller_name) VALUES (?, ?)",
                (user_id, key)
            )
            await db.commit()
            return True
        except Exception:
            return False


async def is_blacklisted(user_id: int, seller_name: Optional[str], url: Optional[str] = None, address: Optional[str] = None) -> bool:
    """Проверяет, находится ли продавец в черном списке пользователя."""
    if not seller_name:
        return False
    clean_seller = seller_name.strip().lower()
    city = ""
    if url:
        m = re.search(r"avito\.ru/([^/?#]+)", str(url))
        if m and m.group(1).lower() not in ("items", "i"):
            city = m.group(1).lower().strip()
    if not city and address:
        parts = str(address).split(",")
        if parts and parts[0].strip():
            city = parts[0].lower().strip()

    async with aiosqlite.connect(DATABASE_PATH) as db:
        if city:
            async with db.execute(
                "SELECT 1 FROM blacklist WHERE user_id = ? AND LOWER(seller_name) = LOWER(?)",
                (user_id, f"{clean_seller}@{city}")
            ) as cursor:
                if await cursor.fetchone() is not None:
                    return True
        if not city:
            async with db.execute(
                "SELECT 1 FROM blacklist WHERE user_id = ? AND LOWER(seller_name) = LOWER(?)",
                (user_id, clean_seller)
            ) as cursor:
                return await cursor.fetchone() is not None
        return False


async def remove_from_blacklist(user_id: int, seller_name: str) -> bool:
    """Удаляет продавца из черного списка."""
    clean_seller = seller_name.strip().lower()
    async with aiosqlite.connect(DATABASE_PATH) as db:
        if "@" in clean_seller:
            cursor = await db.execute(
                "DELETE FROM blacklist WHERE user_id = ? AND LOWER(seller_name) = LOWER(?)",
                (user_id, clean_seller)
            )
        else:
            cursor = await db.execute(
                "DELETE FROM blacklist WHERE user_id = ? AND (LOWER(seller_name) = LOWER(?) OR LOWER(seller_name) LIKE LOWER(?))",
                (user_id, clean_seller, f"{clean_seller}@%")
            )
        await db.commit()
        return cursor.rowcount > 0


async def get_user_blacklist(user_id: int) -> List[str]:
    """Возвращает список заблокированных продавцов пользователя."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        async with db.execute(
            "SELECT seller_name FROM blacklist WHERE user_id = ? ORDER BY created_at DESC",
            (user_id,)
        ) as cursor:
            rows = await cursor.fetchall()
            return [row[0] for row in rows]


# ================= Настройки звука (Silent Mode) =================

async def is_silent_mode(user_id: int) -> bool:
    """Проверяет, включен ли тихий режим у пользователя (без звука)."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        async with db.execute(
            "SELECT silent_mode FROM users WHERE user_id = ?",
            (user_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return bool(row[0]) if row and row[0] is not None else False


async def toggle_silent_mode(user_id: int) -> bool:
    """Переключает тихий режим (вкл/выкл) и возвращает новое состояние."""
    current = await is_silent_mode(user_id)
    new_state = 0 if current else 1
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            "UPDATE users SET silent_mode = ? WHERE user_id = ?",
            (new_state, user_id)
        )
        await db.commit()
    return bool(new_state)


async def get_user_proxies(user_id: int) -> List[str]:
    """Возвращает список персональных прокси конкретного пользователя."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        async with db.execute(
            "SELECT proxy FROM user_proxies WHERE user_id = ? AND is_alive = 1 ORDER BY id ASC",
            (user_id,)
        ) as cursor:
            rows = await cursor.fetchall()
            return [r[0] for r in rows]


async def add_user_proxy(user_id: int, proxy: str):
    """Добавляет персональный прокси пользователю."""
    p = proxy.strip()
    if not p:
        return
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO user_proxies (user_id, proxy, is_alive) VALUES (?, ?, 1)",
            (user_id, p)
        )
        await db.commit()


async def remove_user_proxy(user_id: int, proxy: str):
    """Удаляет персональный прокси пользователя."""
    p = proxy.strip()
    if not p:
        return
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            "DELETE FROM user_proxies WHERE user_id = ? AND proxy = ?",
            (user_id, p)
        )
        await db.commit()


async def set_user_proxies(user_id: int, proxies: List[str]):
    """Перезаписывает список персональных прокси пользователя."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("DELETE FROM user_proxies WHERE user_id = ?", (user_id,))
        for p in proxies:
            p = p.strip()
            if p:
                await db.execute(
                    "INSERT OR IGNORE INTO user_proxies (user_id, proxy, is_alive) VALUES (?, ?, 1)",
                    (user_id, p)
                )
        await db.commit()


async def is_tg_notified(user_id: int, item_id: Any) -> bool:
    """Проверяет, было ли уже отправлено уведомление по объявлению пользователю в Telegram."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        async with db.execute(
            "SELECT 1 FROM notified_tg_history WHERE user_id = ? AND item_id = ?",
            (user_id, str(item_id))
        ) as cursor:
            row = await cursor.fetchone()
            return row is not None


async def record_tg_notified(user_id: int, item_id: Any):
    """Фиксирует объявление как известное/отправленное в Telegram, предотвращая повторный спам."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO notified_tg_history (user_id, item_id) VALUES (?, ?)",
            (user_id, str(item_id))
        )
        await db.commit()

