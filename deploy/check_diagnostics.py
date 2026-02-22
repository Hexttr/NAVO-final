#!/usr/bin/env python3
"""
Проверка /api/diagnostics. Запуск: python check_diagnostics.py
Можно вызывать из Cursor для проверки состояния продакшена.
"""
import json
import urllib.request

URL = "https://navoradio.com/api/diagnostics"


def main():
    try:
        req = urllib.request.Request(URL, headers={"User-Agent": "NAVO-Check/1.0"})
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read().decode())
    except Exception as e:
        print(f"ERROR: {e}")
        return 1

    print(json.dumps(data, indent=2, ensure_ascii=False))
    checks = data.get("checks", {})
    ok = data.get("ok", False)
    broadcast_ready = checks.get("broadcast_ready", False)
    icecast_live = checks.get("icecast_live", "?")
    print("\n--- Summary ---")
    print(f"ok: {ok}, broadcast_ready: {broadcast_ready}, icecast: {icecast_live}")
    return 0 if ok and broadcast_ready else 1


if __name__ == "__main__":
    exit(main())
