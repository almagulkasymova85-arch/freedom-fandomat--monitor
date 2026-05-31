#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Freedom Фандоматы — Автоматическая настройка Telegram-бота
Запустите: python setup.py
"""

import json
import urllib.request
import urllib.parse
import subprocess
import sys
import os

REPO = "almagulkasymova85-arch/freedom-fandomat--monitor"
TARGET_CHAT = "TASTA"  # часть названия чата

def api(token, method, params=None):
    url  = f"https://api.telegram.org/bot{token}/{method}"
    data = urllib.parse.urlencode(params or {}).encode() if params else None
    req  = urllib.request.Request(url, data=data)
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())

def set_secret(name, value):
    result = subprocess.run(
        ["gh", "secret", "set", name, "--body", value, "--repo", REPO],
        capture_output=True, text=True
    )
    return result.returncode == 0

print("=" * 55)
print("  Freedom Фандоматы — Настройка Telegram-бота")
print("=" * 55)
print()

# ── ШАГ 1: Токен
print("ШАГ 1 из 4 — Токен бота")
print("-" * 40)
print("Откройте Telegram → @BotFather → /mybots")
print("→ выберите бота → API Token → скопируйте")
print()
token = input("Вставьте токен сюда: ").strip()
if not token or ":" not in token:
    print("❌ Неверный формат токена!")
    sys.exit(1)

# ── ШАГ 2: Проверка токена
print()
print("ШАГ 2 из 4 — Проверка бота...")
print("-" * 40)
try:
    me = api(token, "getMe")
    if not me.get("ok"):
        print(f"❌ Токен недействителен: {me}")
        sys.exit(1)
    bot_name = me["result"]["username"]
    print(f"✅ Бот найден: @{bot_name}")
except Exception as e:
    print(f"❌ Ошибка: {e}")
    sys.exit(1)

# ── ШАГ 3: Поиск чата
print()
print("ШАГ 3 из 4 — Поиск чата 'TASTA: ФАНДОМАТЫ'...")
print("-" * 40)
print(f"Убедитесь что @{bot_name} добавлен в группу 'TASTA: ФАНДОМАТЫ'")
print("Затем напишите ЛЮБОЕ сообщение в этой группе и нажмите Enter")
input("Нажмите Enter когда отправите сообщение... ")

chat_id   = None
chat_name = None

try:
    updates = api(token, "getUpdates", {"limit": 50, "timeout": 0})
    if not updates.get("ok"):
        raise Exception(str(updates))

    for upd in reversed(updates.get("result", [])):
        msg  = upd.get("message") or upd.get("channel_post") or {}
        chat = msg.get("chat", {})
        title = chat.get("title", "")
        cid   = chat.get("id")
        ctype = chat.get("type", "")

        if TARGET_CHAT.upper() in title.upper() and cid:
            chat_id   = cid
            chat_name = title
            break

    if not chat_id:
        # показать все найденные чаты
        print("\n⚠️  Чат 'TASTA' не найден. Найденные чаты:")
        seen = set()
        for upd in updates.get("result", []):
            msg  = upd.get("message") or upd.get("channel_post") or {}
            chat = msg.get("chat", {})
            title = chat.get("title", "")
            cid   = chat.get("id")
            if cid and cid not in seen and title:
                print(f"   {title}  (id: {cid})")
                seen.add(cid)

        print()
        manual = input("Введите Chat ID вручную (или Enter для выхода): ").strip()
        if manual:
            chat_id   = manual
            chat_name = "Введён вручную"
        else:
            print("Добавьте бота в группу и повторите.")
            sys.exit(1)

    print(f"✅ Найден чат: '{chat_name}' (ID: {chat_id})")

except Exception as e:
    print(f"❌ Ошибка getUpdates: {e}")
    sys.exit(1)

# ── ШАГ 4: Сохранение секретов
print()
print("ШАГ 4 из 4 — Сохранение в GitHub Secrets...")
print("-" * 40)

ok1 = set_secret("TELEGRAM_BOT_TOKEN", token)
ok2 = set_secret("TELEGRAM_CHAT_ID",   str(chat_id))

if ok1 and ok2:
    print("✅ TELEGRAM_BOT_TOKEN — сохранён")
    print("✅ TELEGRAM_CHAT_ID   — сохранён")
else:
    if not ok1: print("❌ Ошибка сохранения TELEGRAM_BOT_TOKEN")
    if not ok2: print("❌ Ошибка сохранения TELEGRAM_CHAT_ID")
    sys.exit(1)

# ── Тестовая отправка
print()
print("Отправка тестового сообщения...")
try:
    test_msg = (
        "✅ <b>Freedom Фандоматы — бот настроен!</b>\n\n"
        "Ежедневный отчёт по критичным точкам будет приходить каждый день в <b>10:00</b> (Алматы).\n\n"
        "♻️ Мониторинг запущен!"
    )
    result = api(token, "sendMessage", {
        "chat_id":    str(chat_id),
        "text":       test_msg,
        "parse_mode": "HTML"
    })
    if result.get("ok"):
        print("✅ Тестовое сообщение отправлено в Telegram!")
    else:
        print(f"⚠️  Ошибка отправки: {result}")
except Exception as e:
    print(f"⚠️  Ошибка отправки: {e}")

print()
print("=" * 55)
print("  🎉 НАСТРОЙКА ЗАВЕРШЕНА!")
print("=" * 55)
print()
print(f"  Чат:    {chat_name}")
print(f"  Бот:    @{bot_name}")
print(f"  Время:  Каждый день в 10:00 (Алматы)")
print()
print("  Для ручного запуска отчёта:")
print(f"  gh workflow run daily-report.yml --repo {REPO}")
print()
