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
from datetime import datetime

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

API_KEY     = os.environ.get("GIS_API_KEY", "")
DATA_FILE   = os.path.join(os.path.dirname(__file__), "data.json")
TASTAMAT_URL = "https://rvm.tastamat.com/red/locations"
GIS_SEARCH   = "https://catalog.api.2gis.com/3.0/items"
GIS_BYID     = "https://catalog.api.2gis.com/3.0/items/byid"
SEARCH_QUERY = "Freedom фандомат приему пластиковых бутылок"
RADIUS       = 500       # метров вокруг координат аппарата
REQ_DELAY    = 0.3       # пауза между запросами к 2ГИС, сек
BYID_CHUNK   = 100       # 2ГИС byid принимает до 100 id за запрос
RESOLVE_AFTER_DAYS = 7   # как часто заново искать карточку для ненайденных точек

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

def extract_rating(reviews_block):
    """Из блока reviews 2ГИС вернуть (rating, reviews) или None."""
    rv = reviews_block or {}
    rating = rv.get("general_rating")
    if rating is None:
        return None
    reviews = rv.get("general_review_count_with_stars") or rv.get("general_review_count") or 0
    return (rating, reviews)

def fetch_byid(ids):
    """Пакетно получить рейтинги по сохранённым id карточек 2ГИС.
    Возвращает {gis_id: (rating, reviews)} и число потраченных запросов."""
    out, requests = {}, 0
    ids = list(dict.fromkeys(ids))   # дедупликация: byid требует уникальные id
    for i in range(0, len(ids), BYID_CHUNK):
        chunk = ids[i:i + BYID_CHUNK]
        url = f"{GIS_BYID}?id={','.join(chunk)}&fields=items.reviews&key={API_KEY}"
        try:
            d = get_json(url); requests += 1
        except Exception as e:
            print(f"  ⚠️ byid ошибка: {e}")
            continue
        if d.get("meta", {}).get("code") != 200:
            continue
        for it in d.get("result", {}).get("items", []):
            er = extract_rating(it.get("reviews"))
            if er:
                out[str(it.get("id"))] = er
        time.sleep(REQ_DELAY)
    return out, requests

def find_rating(lat, lon):
    """Поиск карточки фандомата у координат. (rating, reviews, name, gis_id) или None."""
    q = urllib.parse.quote(SEARCH_QUERY)
    url = (f"{GIS_SEARCH}?q={q}&point={lon},{lat}&radius={RADIUS}"
           f"&fields=items.reviews,items.address&key={API_KEY}")
    d = get_json(url)
    if d.get("meta", {}).get("code") != 200:
        return None
    for it in d.get("result", {}).get("items", []):
        if not looks_like_fandomat(it.get("name")):
            continue
        er = extract_rating(it.get("reviews"))
        if er:
            return (er[0], er[1], it.get("name"), str(it.get("id")))
    return None

# ── ОСНОВНАЯ ЛОГИКА ───────────────────────────────────────
def main():
    write       = "--write" in sys.argv
    resolve_all = "--resolve-all" in sys.argv   # принудительно искать карточки заново
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
    now  = datetime.now()
    req_byid = req_search = 0
    dirty = False
    ratings = {}   # gis_id -> (rating, reviews)

    # 1) ЭКОНОМНО: пакетно тянем рейтинги по сохранённым gisId (1 запрос на 100 шт.)
    have_ids = [p["gisId"] for p in data if p.get("gisId")]
    if have_ids:
        ratings, req_byid = fetch_byid(have_ids)

    # 2) Только для точек БЕЗ карточки — поиск (и не чаще, чем раз в RESOLVE_AFTER_DAYS)
    for p in data:
        if p.get("gisId"):
            continue
        latlon = coords.get(p["id"].replace("rvm", ""))
        if not latlon:
            continue   # нет координат — искать не по чему
        last = p.get("gisMiss")
        if last and not resolve_all:
            try:
                if (now - datetime.fromisoformat(last)).days < RESOLVE_AFTER_DAYS:
                    continue
            except Exception:
                pass
        try:
            res = find_rating(*latlon); req_search += 1
        except Exception as e:
            print(f"  ⚠️ RVM {p['id']}: ошибка 2ГИС: {e}"); res = None
        time.sleep(REQ_DELAY)
        if res:
            rating, reviews, name, gid = res
            ratings[gid] = (rating, reviews)
            if write:
                p["gisId"] = gid
                p.pop("gisMiss", None)
                dirty = True
        elif write:
            p["gisMiss"] = now.date().isoformat()   # помечаем, чтобы не искать каждый день
            dirty = True

    # 3) Применяем рейтинги ко всем точкам
    changed = found = 0
    for p in data:
        gid = p.get("gisId")
        if not gid or gid not in ratings:
            continue
        found += 1
        rating, reviews = ratings[gid]
        old_r, old_v = p.get("rating"), p.get("reviews", 0)
        if rating != old_r or reviews != old_v:
            changed += 1
            arrow = "🆕" if old_r is None else ("▲" if rating > old_r else "▼" if rating < old_r else "→")
            print(f"  {arrow} RVM {p['id'].replace('rvm','')} {p['city']} — {p['address']}")
            print(f"       рейтинг {old_r} → {rating} | отзывы {old_v} → {reviews}")
            if write:
                p["prevRating"] = old_r
                p["rating"]     = rating
                p["reviews"]    = reviews
                dirty = True

    no_coords = sum(1 for p in data if not coords.get(p["id"].replace("rvm", "")))
    no_card   = sum(1 for p in data if not p.get("gisId"))

    print(f"\n─ ИТОГО ──────────────────────────────────")
    print(f"  Получено рейтингов: {found}")
    print(f"  Из них изменилось:  {changed}")
    print(f"  Без карточки 2ГИС:  {no_card}")
    print(f"  Нет координат:      {no_coords} (нет в API Tastamat)")
    print(f"  💸 Запросов к 2ГИС: {req_byid + req_search} "
          f"(пакетно byid: {req_byid}, поиск: {req_search})")

    if write and dirty:
        save_data(data)
        print(f"\n✅ data.json обновлён.")
    elif not write:
        print(f"\nℹ️  Это dry-run. Для записи добавь флаг --write")

if __name__ == "__main__":
    main()
