#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Freedom Фандоматы — Автопарсинг рейтингов из 2ГИС.

Для каждой точки:
  1. берёт координаты из API Tastamat (по uuid),
  2. ищет в 2ГИС карточку фандомата рядом с этими координатами,
  3. забирает рейтинг (general_rating) и число отзывов,
  4. обновляет bot/data.json (с сохранением prevRating).

Запуск:
  GIS_API_KEY=<ключ> python bot/sync_2gis.py            # dry-run, только показать расхождения
  GIS_API_KEY=<ключ> python bot/sync_2gis.py --write    # записать в data.json

Ключ 2ГИС берётся из переменной окружения GIS_API_KEY
(в GitHub Actions — secrets.GIS_API_KEY).
"""

import json
import os
import sys
import time
import urllib.request
import urllib.parse

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

API_KEY     = os.environ.get("GIS_API_KEY", "")
DATA_FILE   = os.path.join(os.path.dirname(__file__), "data.json")
TASTAMAT_URL = "https://rvm.tastamat.com/red/locations"
GIS_SEARCH   = "https://catalog.api.2gis.com/3.0/items"
SEARCH_QUERY = "Freedom фандомат приему пластиковых бутылок"
RADIUS       = 500       # метров вокруг координат аппарата
REQ_DELAY    = 0.3       # пауза между запросами к 2ГИС, сек

# ── HTTP ──────────────────────────────────────────────────
def get_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": "fandomat-sync/1.0"})
    with urllib.request.urlopen(req, timeout=25) as r:
        return json.loads(r.read().decode("utf-8"))

def load_data():
    with open(DATA_FILE, encoding="utf-8-sig") as f:
        return json.load(f)

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

# ── ПОИСК КАРТОЧКИ В 2ГИС ─────────────────────────────────
def looks_like_fandomat(name):
    n = (name or "").lower()
    if "фандомат" in n or ("приему" in n and "бутыл" in n):
        return True
    # запасной матч: Freedom, но не банкомат/картомат/mobile/банк
    if "freedom" in n and not any(w in n for w in ("банкомат", "картомат", "mobile", "bank", "банк")):
        return True
    return False

def find_rating(lat, lon):
    """Вернуть (rating, reviews, name, gis_id) для фандомата у координат или None."""
    q = urllib.parse.quote(SEARCH_QUERY)
    url = (f"{GIS_SEARCH}?q={q}&point={lon},{lat}&radius={RADIUS}"
           f"&fields=items.reviews,items.address&key={API_KEY}")
    d = get_json(url)
    if d.get("meta", {}).get("code") != 200:
        return None
    for it in d.get("result", {}).get("items", []):
        if not looks_like_fandomat(it.get("name")):
            continue
        rv = it.get("reviews") or {}
        rating = rv.get("general_rating")
        if rating is None:
            continue
        reviews = rv.get("general_review_count_with_stars") or rv.get("general_review_count") or 0
        return (rating, reviews, it.get("name"), it.get("id"))
    return None

# ── ОСНОВНАЯ ЛОГИКА ───────────────────────────────────────
def main():
    write = "--write" in sys.argv
    if not API_KEY:
        print("❌ Не задан GIS_API_KEY (ключ 2ГИС). "
              "Запуск: GIS_API_KEY=<ключ> python bot/sync_2gis.py")
        sys.exit(1)

    print(f"🔑 Ключ 2ГИС: …{API_KEY[-6:]}")
    print(f"📥 Режим: {'ЗАПИСЬ в data.json' if write else 'dry-run (только показать)'}\n")

    # координаты аппаратов из Tastamat: uuid -> (lat, lon)
    try:
        coords = {x["uuid"]: (x["latitude"], x["longitude"])
                  for x in get_json(TASTAMAT_URL)["list"]}
    except Exception as e:
        print(f"❌ Не удалось получить координаты из Tastamat: {e}")
        sys.exit(1)

    data = load_data()
    changed, found, no_coords, not_found = 0, 0, 0, 0

    for p in data:
        uuid = p["id"].replace("rvm", "")
        latlon = coords.get(uuid)
        if not latlon:
            no_coords += 1
            continue
        try:
            res = find_rating(*latlon)
        except Exception as e:
            print(f"  ⚠️ RVM {uuid}: ошибка запроса 2ГИС: {e}")
            res = None
        time.sleep(REQ_DELAY)
        if not res:
            not_found += 1
            continue
        rating, reviews, name, gis_id = res
        found += 1
        old_r, old_v = p.get("rating"), p.get("reviews", 0)
        if rating != old_r or reviews != old_v:
            changed += 1
            arrow = "🆕" if old_r is None else ("▲" if rating > old_r else "▼" if rating < old_r else "→")
            print(f"  {arrow} RVM {uuid} {p['city']} — {p['address']}")
            print(f"       рейтинг {old_r} → {rating} | отзывы {old_v} → {reviews}")
            if write:
                p["prevRating"] = old_r
                p["rating"]     = rating
                p["reviews"]    = reviews
                p["gisId"]      = gis_id

    print(f"\n─ ИТОГО ──────────────────────────────────")
    print(f"  Найдено в 2ГИС:   {found}")
    print(f"  Из них изменилось:{changed}")
    print(f"  Не найдено в 2ГИС:{not_found}")
    print(f"  Нет координат:    {no_coords} (нет в API Tastamat)")

    if write and changed:
        save_data(data)
        print(f"\n✅ data.json обновлён ({changed} точек).")
    elif not write:
        print(f"\nℹ️  Это dry-run. Для записи добавь флаг --write")

if __name__ == "__main__":
    main()
