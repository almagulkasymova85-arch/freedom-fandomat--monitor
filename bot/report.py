#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Freedom Фандоматы — Ежедневный отчёт в Telegram
Запускается через GitHub Actions каждый день в 10:00 (Алматы UTC+5)
"""

import json
import os
import sys
from datetime import datetime
import urllib.request
import urllib.parse

# ── НАСТРОЙКИ ─────────────────────────────────────────────
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
CHAT_ID   = os.environ.get("TELEGRAM_CHAT_ID", "")
DATA_FILE = os.path.join(os.path.dirname(__file__), "data.json")

# API Tastamat — live-статус аппаратов (принимает / выключен / бак полон)
LIVE_API_URL = "https://rvm.tastamat.com/red/locations"
STATUS_RU = {
    "OFF":                     "⛔ выключен",
    "UNAVAILABLE_TANK":        "🟠 бак полон",
    "UNAVAILABLE_MAINTENANCE": "🔧 обслуживание",
    "UNAVAILABLE_CAMERA":      "📷 нет камеры",
}

# ── HELPERS ───────────────────────────────────────────────
def get_status(rating):
    if rating is None:
        return "new"
    if rating < 2.5:
        return "critical"
    if rating < 3.5:
        return "warning"
    return "good"

def stars(rating):
    if rating is None:
        return "—"
    full = round(rating)
    return "★" * full + "☆" * (5 - full)

def fmt(rating):
    return f"{rating:.1f}" if rating is not None else "—"

def trend(cur, prev):
    if prev is None or cur is None:
        return ""
    d = round(cur - prev, 1)
    if d > 0:
        return f" ▲+{d}"
    if d < 0:
        return f" ▼{d}"
    return " →0"

def send_telegram(text):
    """Отправить сообщение в Telegram"""
    if not BOT_TOKEN or not CHAT_ID:
        print("❌ Не заданы TELEGRAM_BOT_TOKEN или TELEGRAM_CHAT_ID")
        sys.exit(1)

    url  = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    data = urllib.parse.urlencode({
        "chat_id":    CHAT_ID,
        "text":       text,
        "parse_mode": "HTML",
    }).encode("utf-8")

    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            result = json.loads(resp.read().decode())
            if result.get("ok"):
                print("✅ Отчёт отправлен в Telegram")
            else:
                print(f"❌ Ошибка Telegram: {result}")
                sys.exit(1)
    except Exception as e:
        print(f"❌ Ошибка запроса: {e}")
        sys.exit(1)

# ── ЗАГРУЗКА ДАННЫХ ───────────────────────────────────────
def load_data():
    if not os.path.exists(DATA_FILE):
        print(f"⚠️  Файл данных не найден: {DATA_FILE}")
        print("   Экспортируйте данные из монитора (кнопка ⬇️ Экспорт JSON)")
        sys.exit(1)
    with open(DATA_FILE, "r", encoding="utf-8-sig") as f:
        return json.load(f)

def fetch_live_status():
    """Загрузить live-статусы аппаратов из API Tastamat. uuid → код статуса."""
    try:
        req = urllib.request.Request(LIVE_API_URL, headers={"User-Agent": "fandomat-report/1.0"})
        with urllib.request.urlopen(req, timeout=20) as r:
            items = json.loads(r.read().decode("utf-8")).get("list", [])
        return {x["uuid"]: x.get("status") for x in items}
    except Exception as e:
        print(f"⚠️  Не удалось получить live-статусы Tastamat: {e}")
        return {}

# ── ФОРМИРОВАНИЕ ОТЧЁТА ───────────────────────────────────
def build_report(points, live=None):
    live     = live or {}
    now      = datetime.now()
    date_str = now.strftime("%d.%m.%Y")
    time_str = now.strftime("%H:%M")

    critical = [p for p in points if get_status(p.get("rating")) == "critical"]
    warning  = [p for p in points if get_status(p.get("rating")) == "warning"]
    good     = [p for p in points if get_status(p.get("rating")) == "good"]
    no_data  = [p for p in points if p.get("rating") is None]

    rated    = [p for p in points if p.get("rating") is not None]
    avg      = sum(p["rating"] for p in rated) / len(rated) if rated else None
    total_rv = sum(p.get("reviews", 0) for p in points)

    lines = []

    # ── ШАПКА
    lines.append(f"♻️ <b>ОТЧЁТ — Freedom Фандоматы</b>")
    lines.append(f"📅 {date_str}  🕙 {time_str} (Алматы)")
    lines.append("")

    # ── KPI
    lines.append("📊 <b>Сводка по сети:</b>")
    lines.append(f"  Точек всего:     <b>{len(points)}</b>")
    lines.append(f"  Средний рейтинг: <b>{fmt(avg)} ★</b>")
    lines.append(f"  Всего отзывов:   <b>{total_rv}</b>")
    lines.append(f"  ✅ Хорошие:  {len(good)}")
    lines.append(f"  🟡 Слабые:   {len(warning)}")
    lines.append(f"  🔴 Критичные: {len(critical)}")
    lines.append(f"  🔵 Без данных: {len(no_data)}")
    lines.append("")

    # ── LIVE-СТАТУС АППАРАТОВ (API Tastamat)
    if live:
        from collections import Counter
        offline = []
        for p in points:
            uuid = str(p.get("id", "")).replace("rvm", "")
            st = live.get(uuid)
            if st and st != "ON":
                offline.append((p, st))
        working = sum(1 for v in live.values() if v == "ON")
        by_status = Counter(st for _, st in offline)

        lines.append("🔌 <b>Состояние аппаратов (Tastamat):</b>")
        lines.append(f"  ✅ Принимают: <b>{working}</b> из {len(live)}")
        if offline:
            lines.append(f"  ⚠️ Не принимают: <b>{len(offline)}</b> — " +
                         ", ".join(f"{STATUS_RU.get(s, s)} {n}" for s, n in by_status.most_common()))
            # Детально только реально сломанные (не рутинный «бак полон»)
            broken = [(p, st) for p, st in offline if st != "UNAVAILABLE_TANK"]
            LIMIT = 15
            for p, st in broken[:LIMIT]:
                lines.append(f"     {STATUS_RU.get(st, st)} — {p.get('city')}, {p.get('address')}")
            if len(broken) > LIMIT:
                lines.append(f"     …и ещё {len(broken) - LIMIT}")
        lines.append("")

    # ── КРИТИЧНЫЕ (главный блок)
    if critical:
        lines.append("🚨 <b>КРИТИЧНЫЕ ТОЧКИ — реакция сегодня!</b>")
        lines.append("─" * 32)
        for p in critical:
            tr = trend(p.get("rating"), p.get("prevRating"))
            lines.append(
                f"📍 <b>{p.get('city', '?')}</b> | {p.get('address', '?')}\n"
                f"   ⭐ {fmt(p.get('rating'))} {stars(p.get('rating'))}{tr} | "
                f"Отзывов: {p.get('reviews', 0)}"
            )
            if p.get("notes"):
                lines.append(f"   💬 {p['notes']}")
            lines.append("")
        lines.append("⚡ <b>Действия:</b> ответить на отзывы → выехать → починить")
        lines.append("")
    else:
        lines.append("✅ <b>Критичных точек нет — отлично!</b>")
        lines.append("")

    # ── СЛАБЫЕ
    if warning:
        lines.append("⚠️ <b>Слабые точки (рейтинг 2.5–3.5):</b>")
        for p in warning:
            tr = trend(p.get("rating"), p.get("prevRating"))
            lines.append(
                f"  📍 {p.get('city')} — {p.get('address')}\n"
                f"     ⭐ {fmt(p.get('rating'))}{tr} | {p.get('reviews', 0)} отзывов"
            )
        lines.append("")

    # ── ХОРОШИЕ (кратко)
    if good:
        lines.append(f"🟢 <b>Хорошие точки ({len(good)}):</b>")
        for p in good:
            lines.append(
                f"  ✅ {p.get('city')} — {p.get('address')} "
                f"⭐{fmt(p.get('rating'))}"
            )
        lines.append("")

    # ── РЕКОМЕНДАЦИИ ДНЯ
    lines.append("─" * 32)
    lines.append("📋 <b>Задачи на сегодня:</b>")
    if critical:
        for p in critical:
            lines.append(f"  🔴 {p.get('city')}, {p.get('address')[:35]}...")
            lines.append(f"      → Ответить в 2ГИС + выезд на точку")
    if not critical and not warning:
        lines.append("  💡 Стимулировать новые отзывы на хороших точках")
        lines.append("  📱 QR-код → попросить сдавших бутылки оставить отзыв")
    lines.append("")
    lines.append(f"🔗 Монитор: https://almagulkasymova85-arch.github.io/freedom-fandomat--monitor/")

    return "\n".join(lines)

# ── MAIN ──────────────────────────────────────────────────
def main():
    print(f"🚀 Запуск отчёта: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    points = load_data()
    print(f"📊 Загружено точек: {len(points)}")

    live = fetch_live_status()
    print(f"🔌 Live-статусов из API: {len(live)}")

    report = build_report(points, live)
    print("\n" + "="*50)
    print(report)
    print("="*50 + "\n")

    send_telegram(report)

if __name__ == "__main__":
    main()
