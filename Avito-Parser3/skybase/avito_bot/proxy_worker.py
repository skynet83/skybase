# -*- coding: utf-8 -*-
"""
Фоновый воркер для поиска и проверки бесплатных прокси для Avito.
Может запускаться как из Telegram-бота, так и из веб-панели ElectroBase.
"""
import os
import sys
import json
import asyncio
import atexit
import logging

BOT_DIR = os.path.dirname(os.path.abspath(__file__))
SITE_DIR = os.path.dirname(BOT_DIR)
LIB_DIR = os.path.join(SITE_DIR, "lib")
if os.path.exists(LIB_DIR) and LIB_DIR not in sys.path:
    sys.path.insert(0, LIB_DIR)
try:
    with open(os.path.join(BOT_DIR, "proxy_worker.log"), "a", encoding="utf-8") as _f:
        _f.write(f"--- proxy_worker process starting (argv={sys.argv}) ---\n")
except Exception:
    pass

if sys.platform == "win32":
    if sys.stdout and hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass
    if sys.stderr and hasattr(sys.stderr, "reconfigure"):
        try:
            sys.stderr.reconfigure(encoding="utf-8")
        except Exception:
            pass

PID_FILE = os.path.join(BOT_DIR, "proxy_worker.pid")
STATUS_FILE = os.path.join(BOT_DIR, "proxy_status.json")

def write_pid():
    with open(PID_FILE, "w", encoding="utf-8") as f:
        f.write(str(os.getpid()))

def cleanup_pid():
    if os.path.exists(PID_FILE):
        try:
            with open(PID_FILE, "r", encoding="utf-8") as f:
                saved_pid = int(f.read().strip())
            if saved_pid == os.getpid():
                os.remove(PID_FILE)
        except Exception:
            pass

atexit.register(cleanup_pid)

def update_status(is_fetching: bool, found: int = 0, target: int = 50, message: str = ""):
    data = {
        "is_fetching": is_fetching,
        "found": found,
        "target": target,
        "message": message
    }
    try:
        if os.path.exists(STATUS_FILE):
            with open(STATUS_FILE, "r", encoding="utf-8") as f:
                prev = json.load(f)
                if isinstance(prev, dict) and "manual_started" in prev:
                    data["manual_started"] = prev["manual_started"]
        with open(STATUS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

def log_worker(msg: str):
    try:
        log_file = os.path.join(BOT_DIR, "proxy_worker.log")
        import time
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n")
    except Exception:
        pass

def is_license_expired() -> bool:
    """Проверяет истекла ли лицензия."""
    try:
        sys.path.insert(0, os.path.dirname(BOT_DIR))
        import avito_api_helper
        lic = avito_api_helper.get_license_status_info("")
        if lic and lic.get("is_expired") is True:
            return True
        return False
    except Exception:
        return False

def is_monitoring_or_tg_active():
    """Проверяет: включен ли мониторинг или тг-уведомления."""
    try:
        sys.path.insert(0, os.path.dirname(BOT_DIR))
        import avito_api_helper
        mon = avito_api_helper.get_monitor_state()
        tg_paused = avito_api_helper.get_bot_paused()
        return bool(mon or (not tg_paused)), bool(mon), bool(not tg_paused)
    except Exception:
        mon_file = os.path.join(BOT_DIR, "monitor_state.json")
        if os.path.exists(mon_file):
            try:
                with open(mon_file, "r", encoding="utf-8") as f:
                    d = json.load(f)
                    m = bool(d.get("enabled", True))
                    t = not bool(d.get("bot_paused", False))
                    return (m or t), m, t
            except Exception:
                pass
        return True, True, True

def get_target_proxy_count() -> tuple[int, int]:
    """Вычисляет целевой размер пула прокси с учетом активных ссылок:
    N активных ссылок * 15 (базовый боевой состав) + N * 5 (горячий резерв) = N * 20.
    Возвращает (target_total, active_links_count).
    Для 1 ссылки:  20 (15 база + 5 резерв)
    Для 2 ссылок:  40 (30 база + 10 резерв)
    ...
    Для 10 ссылок: 200 (150 база + 50 резерв)
    """
    try:
        import sqlite3
        db_path = os.path.join(BOT_DIR, "avito_bot.db")
        if os.path.exists(db_path):
            con = sqlite3.connect(db_path)
            cur = con.cursor()
            cur.execute("""
                SELECT COUNT(t.id)
                FROM tracked_urls t
                JOIN users u ON t.user_id = u.user_id
                WHERE t.is_active = 1 AND u.status IN ('admin', 'approved')
            """)
            row = cur.fetchone()
            con.close()
            active_cnt = int(row[0]) if row and row[0] else 1
        else:
            active_cnt = 1
    except Exception:
        active_cnt = 1

    active_cnt = min(10, max(1, active_cnt))
    return (active_cnt * 20), active_cnt

async def run_fetch(target: int = 40):
    target, active_links = get_target_proxy_count()
    log_worker(f"run_fetch started (adaptive mode: {active_links} ссылок, цель={target} с резервом, PID={os.getpid()})")
    write_pid()
    update_status(True, found=0, target=target, message=f"Сбор и проверка кандидатов (цель: {target})...")
    
    try:
        sys.path.insert(0, BOT_DIR)
        from parser import ProxyPool
        pool = ProxyPool()
        log_worker("ProxyPool initialized")

        update_status(True, found=len(pool.proxies), target=target, message="Очистка нерабочих прокси...")
        alive_before = await pool.filter_and_clean_dead_proxies()
        log_worker(f"Dead proxies cleaned: {alive_before} alive remaining")
        update_status(True, found=alive_before, target=target, message=f"Осталось живых: {alive_before}/{target}. Проверка и поиск...")

        async def on_progress(found_count, target_count):
            if is_license_expired():
                pool.stop_fetching()
                return
            if os.path.exists(STATUS_FILE):
                try:
                    with open(STATUS_FILE, "r", encoding="utf-8") as f:
                        cur_st = json.load(f)
                    if cur_st.get("is_fetching") is False:
                        pool.reload()
                        if len(pool.proxies) == 0:
                            pool.stop_fetching()
                            return
                except Exception:
                    pass
            log_worker(f"Progress: {found_count}/{target}")
            update_status(True, found=found_count, target=target, message=f"Найдено рабочих: {found_count}/{target}")
            
        round_idx = 0
        while True:
            # 1. Проверка срока действия лицензии (единственное жесткое условие остановки)
            if is_license_expired():
                log_worker("License expired. Stopping proxy worker.")
                pool.reload()
                update_status(False, found=len(pool.proxies), target=target, message="Лицензия истекла. Проверка остановлена.")
                break

            # 2. Проверка ручной остановки при условии прокси = 0
            if os.path.exists(STATUS_FILE):
                try:
                    with open(STATUS_FILE, "r", encoding="utf-8") as f:
                        cur_st = json.load(f)
                        if cur_st.get("is_fetching") is False:
                            pool.reload()
                            if len(pool.proxies) == 0:
                                log_worker("Stop flag found and proxy count is 0. Exiting.")
                                break
                except Exception:
                    pass

            target, active_links = get_target_proxy_count()
            pool.reload()
            cur_alive = len(pool.proxies)

            # Если пул укомплектован (достигнута цель с резервом)
            # Переходим в непрерывный режим селекции: чистим отвалившиеся и ищем прокси с меньшим пингом ("Царь горы")
            if cur_alive >= target:
                log_worker(f"Target reached: {cur_alive}/{target} ({active_links} ссылок). Running ping optimization (Царь горы)...")
                update_status(True, found=cur_alive, target=target, message=f"Пул укомплектован ({cur_alive}/{target}). Селекция прокси с наименьшим пингом...")
                
                # Чистим отвалившиеся прокси
                cur_alive = await pool.filter_and_clean_dead_proxies()
                log_worker(f"After cleaning: {cur_alive}/{target} alive remaining")

                # Если после чистки пул всё ещё полон — запускаем раунд селекции по пингу
                if cur_alive >= target:
                    round_idx += 1
                    await pool.fetch_free_proxies_and_verify(
                        target_alive=target,
                        max_candidates=1000,
                        on_progress=on_progress,
                        replace_slower=True
                    )
                    # Пауза 30 секунд перед следующим циклом проверки
                    for _ in range(30):
                        if is_license_expired():
                            break
                        await asyncio.sleep(1.0)
                    continue

            round_idx += 1
            log_worker(f"Starting harvest round #{round_idx}: current alive={cur_alive}/{target} ({active_links} ссылок)")
            base_thresh = active_links * 15
            if cur_alive < base_thresh:
                stage_msg = f"Набор базы ({cur_alive}/{base_thresh}) для параллельного опроса ({active_links} ссылок)..."
            else:
                stage_msg = f"Набор резерва ({cur_alive}/{target}) для параллельного опроса ({active_links} ссылок)..."
            update_status(True, found=cur_alive, target=target, message=stage_msg)

            # Собираем и валидируем кандидатов
            import time as _time
            t0 = _time.time()
            new_count = await pool.fetch_free_proxies_and_verify(
                target_alive=target,
                max_candidates=5000,
                on_progress=on_progress,
                replace_slower=True
            )
            elapsed = _time.time() - t0
            pool.reload()
            cur_alive = len(pool.proxies)
            log_worker(f"Round #{round_idx} ended in {elapsed:.1f}s, current alive={cur_alive}/{target} (new_from_fetch={new_count})")

            # Если пул пуст (0 прокси) и ничего не нашлось
            if cur_alive == 0:
                log_worker("Warning: 0 live proxies found in this cycle. Retrying in 10s...")
                await asyncio.sleep(10.0)
                continue

            # Короткая пауза между раундами добора
            await asyncio.sleep(3.0)

        total = len(pool.proxies)
        log_worker(f"Proxy worker loop ended with total={total}/{target}")
        msg = f"Проверка завершена ({total}/{target})"
        update_status(False, found=total, target=target, message=msg)
    except Exception as e:
        import traceback
        err_msg = traceback.format_exc()
        log_worker(f"Error in run_fetch: {err_msg}")
        update_status(False, found=0, target=target, message=f"Ошибка: {e}")
    finally:
        log_worker("run_fetch finally block: cleaning up PID")
        cleanup_pid()

def main():
    log_worker(f"proxy_worker.py main() called with argv={sys.argv}")
    if len(sys.argv) < 2:
        return
    cmd = sys.argv[1].lower()
    if cmd == "fetch":
        target = int(sys.argv[2]) if len(sys.argv) > 2 else 999
        try:
            asyncio.run(run_fetch(target))
        except Exception as e:
            log_worker(f"asyncio.run error: {e}")
    log_worker("proxy_worker.py main() ended")

if __name__ == "__main__":
    main()

