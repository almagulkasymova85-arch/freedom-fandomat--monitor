#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Freedom Фандоматы — Автоматическая настройка Telegram-бота
Отправка отчёта лично вам в Telegram
Запустите: python setup.py
"""

import json
import urllib.request
import urllib.parse
import subprocess
import sys
import os
import webbrowser
import time

REPO = "almagulkasymova85-arch/freedom-fandomat--monitor"

def api(token, method, params=None):
    url  = f"https://api.telegram.org/bot{token}/{method}"
    data = urllib.parse.urlencode(params or {}).encode() if params else None
    req  = urllib.request.Request(url, data=data)
    if data:
        req.add_header("Content-Type", "application/x-www-form-urlencoded")
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())

def set_secret(name, value):
    result = subprocess.run(
        ["gh", "secret", "set", name, "--body", value, "--repo", REPO],
        capture_output=True, text=True
    )
    return result.returncode == 0

print()
print("=" * 55)
print("  Freedom Фандоматы — Настройка Telegram-бота")
print("  Отчёт будет приходить лично вам каждый день")
print("=" * 55)
print()

# ── ШАГ 1: Токен
print("ШАГ 1 из 3 — Токен бота")
print("-" * 40)
print("1. Откройте Telegram")
print("2. Найдите @BotFather")
print("3. Отправьте: /mybots")
print("4. Выберите своего бота")
print("5. Нажмите 'API Token'")
print("6. Скопируйте и вставьте ниже")
print()
token = input("Вставьте токен: ").strip()
if not token or ":" not in token:
    print("❌ Неверный формат! Токен выглядит так: 1234567890:AABB...")
    sys.exit(1)

# ── Проверка токена
print()
print("Проверяю токен...")
try:
    me = api(token, "getMe")
    if not me.get("ok"):
        print(f"❌ Токен не работает. Проверьте и попробуйте снова.")
        sys.exit(1)
    bot_name     = me["result"]["username"]
    bot_fullname = me["result"]["first_name"]
    print(f"✅ Бот найден: {bot_fullname} (@{bot_name})")
except Exception as e:
    print(f"❌ Ошибка: {e}")
    sys.exit(1)

# ── ШАГ 2: Получить chat_id пользователя
print()
print("ШАГ 2 из 3 — Привязка вашего аккаунта")
print("-" * 40)

bot_link = f"https://t.me/{bot_name}?start=setup"
print(f"1. Откройте бота в Telegram: https://t.me/{bot_name}")
print("2. Нажмите кнопку START или отправьте /start")
print("3. Вернитесь сюда и нажмите Enter")
print()

# Открываем ссылку автоматически
try:
    webbrowser.open(f"https://t.me/{bot_name}")
    print(f"   (Открываю бота в браузере...)")
except:
    pass

input("Нажмите Enter после того как написали /start боту... ")

# Ищем chat_id пользователя
print("Ищу ваш аккаунт...")
chat_id   = None
user_name = None

try:
    # Попытка 1: getUpdates
    updates = api(token, "getUpdates", {"limit": 20, "timeout": 5})

    if updates.get("ok") and updates.get("result"):
        for upd in reversed(updates["result"]):
            msg  = upd.get("message", {})
            chat = msg.get("chat", {})
            user = msg.get("from",  {})
            if chat.get("type") == "private" and chat.get("id"):
                chat_id   = chat["id"]
                first     = user.get("first_name","")
                last      = user.get("last_name","")
                username  = user.get("username","")
                user_name = f"{first} {last}".strip() or f"@{username}" or "Пользователь"
                break

    if not chat_id:
        # Повторная попытка — сбросим offset
        updates2 = api(token, "getUpdates", {"limit": 100, "offset": -100})
        for upd in reversed(updates2.get("result", [])):
            msg  = upd.get("message", {})
            chat = msg.get("chat", {})
            user = msg.get("from", {})
            if chat.get("type") == "private" and chat.get("id"):
                chat_id   = chat["id"]
                first     = user.get("first_name","")
                username  = user.get("username","")
                user_name = first or f"@{username}" or "Пользователь"
                break

    if not chat_id:
        print()
        print("⚠️  Не удалось найти автоматически.")
        print("   Введите ваш Telegram ID вручную.")
        print("   Узнать его можно у @userinfobot — напишите ему /start")
        print()
        manual = input("Введите ваш Telegram ID (число): ").strip()
        if manual.lstrip("-").isdigit():
            chat_id   = int(manual)
            user_name = "Вы"
        else:
            print("❌ Неверный формат ID")
            sys.exit(1)

    print(f"✅ Найден аккаунт: {user_name} (ID: {chat_id})")

except Exception as e:
    print(f"❌ Ошибка: {e}")
    sys.exit(1)

# ── ШАГ 3: Сохранение и тест
print()
print("ШАГ 3 из 3 — Сохраняю настройки и проверяю...")
print("-" * 40)

ok1 = set_secret("TELEGRAM_BOT_TOKEN", token)
ok2 = set_secret("TELEGRAM_CHAT_ID",   str(chat_id))

if ok1:
    print("✅ Токен сохранён в GitHub")
else:
    print("❌ Ошибка сохранения токена. Убедитесь что вы вошли через: gh auth login")
    sys.exit(1)

if ok2:
    print("✅ Ваш Chat ID сохранён в GitHub")
else:
    print("❌ Ошибка сохранения Chat ID")
    sys.exit(1)

# Тестовое сообщение
print()
print("Отправляю тестовый отчёт...")
test_msg = (
    "🎉 <b>Freedom Фандоматы — бот настроен!</b>\n\n"
    "Каждый день в <b>10:00</b> (Алматы) вы будете получать отчёт по критичным точкам.\n\n"
    "♻️ <b>Пример отчёта:</b>\n"
    "──────────────────────\n"
    "🚨 <b>Критичные точки сегодня:</b>\n"
    "📍 <b>Астана</b> | ул. Сыганак, 1Б\n"
    "   ⭐ 1.3 ★☆☆☆☆ | Отзывов: 16\n"
    "   💬 Наибольшее кол-во жалоб\n\n"
    "📍 <b>Астана</b> | ТРЦ Asia Park\n"
    "   ⭐ 1.0 ★☆☆☆☆ | Отзывов: 5\n\n"
    "⚡ <b>Действия:</b> ответить в 2ГИС → выехать → починить\n"
    "──────────────────────\n"
    f"🔗 <a href='https://almagulkasymova85-arch.github.io/freedom-fandomat--monitor/'>Открыть монитор</a>"
)

try:
    result = api(token, "sendMessage", {
        "chat_id":                  str(chat_id),
        "text":                     test_msg,
        "parse_mode":               "HTML",
        "disable_web_page_preview": "true"
    })
    if result.get("ok"):
        print("✅ Тестовое сообщение отправлено — проверьте Telegram!")
    else:
        print(f"⚠️  Ошибка: {result.get('description','')}")
except Exception as e:
    print(f"⚠️  Ошибка отправки: {e}")

print()
print("=" * 55)
print("  🎉 ВСЁ ГОТОВО!")
print("=" * 55)
print()
print(f"  Кому:   {user_name}")
print(f"  Бот:    @{bot_name}")
print(f"  Время:  Каждый день в 10:00 (Алматы / UTC+5)")
print(f"  Репо:   github.com/{REPO}")
print()
print("  Для ручного запуска отчёта прямо сейчас:")
print(f"  gh workflow run daily-report.yml --repo {REPO}")
print()
input("Нажмите Enter для закрытия...")
