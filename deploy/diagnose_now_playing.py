#!/usr/bin/env python3
"""
Диагностика «Сейчас играет». Запуск:
  python diagnose_now_playing.py              # локально (http://localhost:8000)
  python diagnose_now_playing.py --remote     # на сервере navoradio.com
"""
import json
import sys
import urllib.request

def fetch(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "NAVO-Diag/1.0"})
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read().decode())

def main():
    remote = "--remote" in sys.argv
    base = "https://navoradio.com" if remote else "http://localhost:8000"
    url = f"{base}/api/broadcast/diagnostics/now-playing"
    try:
        d = fetch(url)
    except Exception as e:
        print(f"Ошибка: {e}")
        return 1

    print("=" * 60)
    print("ДИАГНОСТИКА «Сейчас играет»")
    print("=" * 60)
    print(f"Московское время:     {d.get('moscow_time', '?')} ({d.get('moscow_sec', 0)} сек от полуночи)")
    print(f"Дата эфира:          {d.get('broadcast_date', '?')}")
    print(f"Icecast:             {d.get('icecast', '?')}")
    print(f"Позиция (источник):  {d.get('position_used', 0):.0f} сек — {d.get('position_source', '?')}")
    print()

    sp = d.get("stream_position_file", {})
    print("stream_position.json:")
    print(f"  Путь:   {sp.get('path', '?')}")
    print(f"  Существует: {sp.get('exists', False)}")
    print(f"  Возраст: {sp.get('age_sec')} сек" if sp.get("age_sec") is not None else "  Возраст: —")
    if sp.get("raw"):
        r = sp["raw"]
        if "error" in r:
            print(f"  Ошибка: {r['error']}")
        else:
            print(f"  position_sec: {r.get('position_sec')}")
            print(f"  entity_type:  {r.get('entity_type')}")
            print(f"  entity_id:    {r.get('entity_id')}")
            print(f"  title:        {r.get('title', '—')}")
    print()

    np = d.get("now_playing_response", {})
    print(">>> ЧТО ВИДИТ ПОЛЬЗОВАТЕЛЬ (now-playing API):")
    print(f"  Источник: {np.get('source', '?')}")
    print(f"  Трек:    {np.get('title', '—')}")
    print(f"  Тип:     {np.get('entityType')} id={np.get('entityId')}")
    print(f"  Время:   {np.get('currentTime', '?')}")
    print()

    slot_db = d.get("slot_by_db")
    slot_real = d.get("slot_by_real_durations")
    print("Слот по расписанию (БД):")
    if slot_db:
        print(f"  {slot_db.get('title', '—')} [{slot_db.get('entity_type')} id={slot_db.get('entity_id')}]")
        print(f"  {slot_db.get('start_sec')}-{slot_db.get('end_sec')} сек, duration_db={slot_db.get('duration_db')}")
    else:
        print("  —")
    print()
    print("Слот по реальным длительностям:")
    if slot_real:
        print(f"  {slot_real.get('title', '—')} [{slot_real.get('entity_type')} id={slot_real.get('entity_id')}]")
        print(f"  {slot_real.get('start_sec')}-{slot_real.get('end_sec')} сек, duration_real={slot_real.get('duration_real')}")
    else:
        print("  —")
    print()

    if slot_db and slot_real and (slot_db.get("entity_id") != slot_real.get("entity_id") or slot_db.get("entity_type") != slot_real.get("entity_type")):
        print("!!! РАССИНХРОН: БД и реальные длительности дают разные треки")
    elif np and slot_real and (np.get("entityId") != slot_real.get("entity_id") or np.get("entityType") != slot_real.get("entity_type")):
        print("!!! РАССИНХРОН: Пользователь видит другой трек, чем по реальным длительностям")

    print("=" * 60)
    return 0

if __name__ == "__main__":
    sys.exit(main())
