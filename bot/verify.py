#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Freedom Фандоматы — Сверка data.json с API Tastamat.

Тянет актуальный список фандоматов из rvm.tastamat.com и сравнивает
с локальным bot/data.json. Печатает отчёт расхождений. Ничего не меняет.

  python bot/verify.py

API отдаёт: city, address, addressDescription, status, occupancy, координаты.
Поля totalAccepted (принято бутылок) в API НЕТ — оно не сверяется.
"""

import json
import os
import re
import sys
import urllib.request

# Windows-консоль по умолчанию cp1251 — переключаем вывод на UTF-8.
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

API_URL   = "https://rvm.tastamat.com/red/locations"
DATA_FILE = os.path.join(os.path.dirname(__file__), "data.json")

STATUS_RU = {
    "ON":                     "✅ работает",
    "OFF":                    "⛔ выключен",
    "UNAVAILABLE_TANK":       "🟠 бак полон",
    "UNAVAILABLE_MAINTENANCE":"🔧 обслуживание",
    "UNAVAILABLE_CAMERA":     "📷 нет камеры",
}

# ── ЗАГРУЗКА ──────────────────────────────────────────────
def fetch_api():
    req = urllib.request.Request(API_URL, headers={"User-Agent": "fandomat-verify/1.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))["list"]

def load_data():
    with open(DATA_FILE, encoding="utf-8-sig") as f:
        return json.load(f)

# ── НОРМАЛИЗАЦИЯ ──────────────────────────────────────────
def norm(s):
    """Грубая нормализация текста для сравнения."""
    if not s:
        return ""
    s = s.lower().replace("ё", "е").replace("​", "")
    s = re.sub(r"[^0-9a-zа-я]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()

def house_numbers(s):
    """Извлечь номера домов вида 175/1, 22к1, 13а, 55/7."""
    s = (s or "").lower().replace("к", "/").replace(" ", "")
    return set(re.findall(r"\d+(?:/\d+[а-я]?|[а-я])?", s))

# ── СВЕРКА ────────────────────────────────────────────────
def main():
    try:
        api = fetch_api()
    except Exception as e:
        print(f"❌ Не удалось получить API: {e}")
        sys.exit(1)

    data = load_data()
    api_by_id  = {x["uuid"]: x for x in api}
    data_by_id = {d["id"].replace("rvm", ""): d for d in data}

    api_ids  = set(api_by_id)
    data_ids = set(data_by_id)
    key = lambda s: int(s) if s.isdigit() else s

    print("═" * 60)
    print("  СВЕРКА data.json ↔ API Tastamat (rvm.tastamat.com)")
    print("═" * 60)
    print(f"  В API:      {len(api)} точек")
    print(f"  В data.json:{len(data)} точек")
    print()

    # 1. Состав
    only_data = sorted(data_ids - api_ids, key=key)
    only_api  = sorted(api_ids - data_ids, key=key)

    print("─ 1. СОСТАВ ─────────────────────────────────────────────")
    if only_api:
        print(f"🔴 В API есть, в data.json НЕТ ({len(only_api)}) — добавить:")
        for u in only_api:
            x = api_by_id[u]
            print(f"   • RVM {u}: {x['city']} — {x.get('addressDescription','')} / {x['address']}")
    if only_data:
        print(f"🟠 В data.json есть, в API НЕТ ({len(only_data)}) — проверить/удалить:")
        for u in only_data:
            d = data_by_id[u]
            print(f"   • RVM {u}: {d['city']} — {d['address']}")
    if not only_api and not only_data:
        print("✅ Состав совпадает.")
    print()

    # 2. Поля по общим точкам
    common = sorted(api_ids & data_ids, key=key)
    city_mismatch, addr_suspect = [], []
    for u in common:
        a, d = api_by_id[u], data_by_id[u]
        if norm(a["city"]) != norm(d.get("city")):
            city_mismatch.append((u, d.get("city"), a["city"]))
        # адрес: ядро — номер дома должен совпадать
        an, dn = house_numbers(a["address"]), house_numbers(d.get("address"))
        if an and dn and not (an & dn):
            addr_suspect.append((u, d.get("address"), f"{a.get('addressDescription','')} / {a['address']}"))

    print("─ 2. ГОРОД ──────────────────────────────────────────────")
    if city_mismatch:
        for u, dc, ac in city_mismatch:
            print(f"🟡 RVM {u}: data.json «{dc}» ≠ API «{ac}»")
    else:
        print("✅ Города совпадают.")
    print()

    print("─ 3. АДРЕС (расходится номер дома) ───────────────────────")
    if addr_suspect:
        for u, da, aa in addr_suspect:
            print(f"🟡 RVM {u}:")
            print(f"     data.json: {da}")
            print(f"     API:       {aa}")
    else:
        print("✅ Номера домов совпадают.")
    print()

    # 3. Текущие статусы (информативно — в data.json этого нет)
    print("─ 4. СТАТУС АППАРАТОВ (из API) ───────────────────────────")
    from collections import Counter
    cnt = Counter(x["status"] for x in api)
    for st, n in cnt.most_common():
        print(f"   {STATUS_RU.get(st, st):<18} {n}")
    not_on = [x for x in api if x["status"] != "ON"]
    if not_on:
        print(f"\n   ⚠️ Сейчас НЕ принимают ({len(not_on)}):")
        for x in sorted(not_on, key=lambda x: key(x["uuid"])):
            print(f"     RVM {x['uuid']:<4} {STATUS_RU.get(x['status'], x['status']):<16} "
                  f"{x['city']} — {x.get('addressDescription','') or x['address']}")
    print()

    print("─ ИТОГО ──────────────────────────────────────────────────")
    print(f"   Состав:  +{len(only_api)} в API / -{len(only_data)} лишних в data.json")
    print(f"   Город:   {len(city_mismatch)} расхождений")
    print(f"   Адрес:   {len(addr_suspect)} подозрительных")
    print("   ⓘ totalAccepted (принято бутылок) в этом API отсутствует — не сверялось.")

if __name__ == "__main__":
    main()
