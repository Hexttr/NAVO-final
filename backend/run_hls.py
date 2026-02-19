#!/usr/bin/env python3
"""
CLI для генерации HLS. Запуск: python run_hls.py YYYY-MM-DD
Используется из API для фоновой генерации в отдельном процессе.
"""
import os
import sys
from datetime import date
from pathlib import Path

# Обеспечить импорты при запуске из backend/
sys.path.insert(0, str(Path(__file__).resolve().parent))

from database import SessionLocal
from services.hls_service import generate_hls


def main():
    if len(sys.argv) < 2:
        print("Usage: python run_hls.py YYYY-MM-DD", file=sys.stderr)
        sys.exit(1)
    try:
        d = date.fromisoformat(sys.argv[1])
    except ValueError:
        print(f"Invalid date: {sys.argv[1]}", file=sys.stderr)
        sys.exit(1)

    print(f"[run_hls] Start: {d}, cwd={os.getcwd()}, v=concat-fix", flush=True)
    db = SessionLocal()
    try:
        print(f"[run_hls] Calling generate_hls...", flush=True)
        result = generate_hls(db, d)
        print(f"[run_hls] Result: {result}", flush=True)
        if result.get("ok"):
            print(f"OK: {result.get('url')}")
            sys.exit(0)
        else:
            print(f"FAIL: {result.get('error', 'unknown')}", file=sys.stderr)
            sys.exit(1)
    except Exception as e:
        import traceback
        traceback.print_exc(file=sys.stderr)
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    main()
