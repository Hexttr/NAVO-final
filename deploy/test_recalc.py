#!/usr/bin/env python3
"""Test recalc-durations locally to reproduce 500."""
import sys
import os
os.chdir(os.path.join(os.path.dirname(__file__), "..", "backend"))
sys.path.insert(0, ".")

from database import SessionLocal
from services.broadcast_service import recalc_all_durations

db = SessionLocal()
try:
    r = recalc_all_durations(db)
    print("OK:", r)
except Exception as e:
    import traceback
    traceback.print_exc()
    print("ERROR:", e)
finally:
    db.close()
