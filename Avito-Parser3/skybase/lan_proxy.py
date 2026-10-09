#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ElectroBase LAN Proxy (Zero-Elevation TCP/HTTP Reverse Proxy)
Позволяет подключаться к серверу по любому локальному IP (192.168.x.x, 10.x.x.x)
и с телефонов/планшетов без необходимости прав Администратора и регистрации URLACL.
"""

import sys
import os
import asyncio
import socket

PID_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lan_proxy.pid")

def write_pid():
    try:
        with open(PID_FILE, "w", encoding="ascii") as f:
            f.write(str(os.getpid()))
    except Exception:
        pass

def remove_pid():
    try:
        if os.path.exists(PID_FILE):
            os.remove(PID_FILE)
    except Exception:
        pass

async def pipe_client_to_target(client_reader, target_writer):
    try:
        while True:
            chunk = await client_reader.read(65536)
            if not chunk:
                break
            target_writer.write(chunk)
            await target_writer.drain()
    except Exception:
        pass
    finally:
        try:
            target_writer.write_eof()
            await target_writer.drain()
        except Exception:
            pass

async def pipe_target_to_client(target_reader, client_writer):
    try:
        while True:
            chunk = await target_reader.read(65536)
            if not chunk:
                break
            client_writer.write(chunk)
            await client_writer.drain()
    except Exception:
        pass
    finally:
        try:
            client_writer.close()
            await client_writer.wait_closed()
        except Exception:
            pass

async def handle_connection(client_reader, client_writer, target_port):
    target_writer = None
    try:
        peer = client_writer.get_extra_info('peername')
        client_ip = peer[0] if peer else "127.0.0.1"

        # Считываем HTTP заголовки запроса (до \r\n\r\n)
        header_buf = bytearray()
        while b"\r\n\r\n" not in header_buf:
            chunk = await client_reader.read(4096)
            if not chunk:
                break
            header_buf.extend(chunk)
            if len(header_buf) > 131072: # Защита от слишком больших заголовков
                break

        if not header_buf:
            client_writer.close()
            return

        delim = header_buf.find(b"\r\n\r\n")
        if delim != -1:
            raw_headers = header_buf[:delim].decode("iso-8859-1")
            initial_body = bytes(header_buf[delim + 4:])
        else:
            raw_headers = header_buf.decode("iso-8859-1")
            initial_body = b""

        # Модифицируем заголовки: подменяем Host на целевой бэкенд и передаем реальный IP
        lines = raw_headers.split("\r\n")
        new_lines = []
        has_xff = False

        for line in lines:
            lower = line.lower()
            if lower.startswith("host:"):
                new_lines.append(f"Host: 127.0.0.1:{target_port}")
            elif lower.startswith("x-forwarded-for:"):
                new_lines.append(f"{line}, {client_ip}")
                has_xff = True
            elif lower.startswith("connection:"):
                new_lines.append("Connection: close")
            else:
                new_lines.append(line)

        if not has_xff:
            new_lines.append(f"X-Forwarded-For: {client_ip}")
        new_lines.append(f"X-Real-IP: {client_ip}")
        new_lines.append("X-Forwarded-Proto: http")
        if not any(l.lower().startswith("connection:") for l in new_lines):
            new_lines.append("Connection: close")

        modified_headers = "\r\n".join(new_lines).encode("iso-8859-1") + b"\r\n\r\n" + initial_body

        # Подключаемся к локальному бэкенду (server.ps1 на порту 127.0.0.1:target_port)
        target_reader, target_writer = await asyncio.open_connection("127.0.0.1", target_port)
        target_writer.write(modified_headers)
        await target_writer.drain()

        # Запускаем чтение тела запроса от клиента в бэкенд в фоне
        t_client = asyncio.create_task(pipe_client_to_target(client_reader, target_writer))

        # Основной поток: отдаем клиенту полный ответ от бэкенда с таймаутом
        try:
            await asyncio.wait_for(pipe_target_to_client(target_reader, client_writer), timeout=30.0)
        finally:
            t_client.cancel()
            try:
                await t_client
            except (asyncio.CancelledError, Exception):
                pass
    except Exception:
        pass
    finally:
        try:
            if target_writer:
                target_writer.close()
                await target_writer.wait_closed()
        except Exception:
            pass
        try:
            client_writer.close()
            await client_writer.wait_closed()
        except Exception:
            pass

async def main():
    write_pid()
    listen_port = 80
    target_port = 10080

    # Разбор аргументов
    args = sys.argv[1:]
    if len(args) >= 2:
        try:
            listen_port = int(args[0])
            target_port = int(args[1])
        except ValueError:
            pass
    elif len(args) == 1:
        try:
            listen_port = int(args[0])
            target_port = 10080 if listen_port == 80 else (listen_port + 10000)
        except ValueError:
            pass

    # Список портов для бинда (приоритет 80 для работы без указания порта в браузере)
    ports_to_bind = [listen_port]
    if listen_port == 80 and 8080 not in ports_to_bind:
        ports_to_bind.append(8080)
    elif listen_port == 8080 and 80 not in ports_to_bind:
        ports_to_bind.insert(0, 80)

    servers = []
    bound_ports = []
    for lp in ports_to_bind:
        try:
            srv = await asyncio.start_server(
                lambda r, w: handle_connection(r, w, target_port),
                "0.0.0.0",
                lp,
                family=socket.AF_INET,
                reuse_address=True
            )
            servers.append(srv)
            bound_ports.append(lp)
        except Exception:
            pass

    # Если ни один из предпочтительных портов не удалось занять — ищем любой свободный
    if not servers:
        for cand_port in [8000, 8888, 5000, 0]:
            try:
                srv = await asyncio.start_server(
                    lambda r, w: handle_connection(r, w, target_port),
                    "0.0.0.0",
                    cand_port,
                    family=socket.AF_INET,
                    reuse_address=True
                )
                actual_p = srv.sockets[0].getsockname()[1]
                servers.append(srv)
                bound_ports.append(actual_p)
                break
            except Exception:
                pass

    if not servers:
        print(f"[LAN-PROXY] [ОШИБКА] Не удалось занять ни один порт для LAN-прокси!", flush=True)
        return

    ports_desc = " и ".join([f"0.0.0.0:{p}" for p in bound_ports])
    has_80 = 80 in bound_ports
    print(f"[LAN-PROXY] Слушает на {ports_desc} -> перенаправляет на 127.0.0.1:{target_port}", flush=True)
    if has_80:
        print("[LAN-PROXY] Доступ без указания порта активен (порт 80)! Можно писать 127.0.0.1 или localhost", flush=True)

    try:
        tasks = [srv.serve_forever() for srv in servers]
        await asyncio.gather(*tasks)
    except asyncio.CancelledError:
        pass
    finally:
        remove_pid()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        remove_pid()
