#!/usr/bin/env python3
"""Check server time for Moscow sync debug."""
from datetime import datetime, timezone, timedelta

utc = datetime.now(timezone.utc)
moscow_tz = timezone(timedelta(hours=3))
moscow = datetime.now(moscow_tz)
local = datetime.now()

print("UTC:", utc.strftime("%H:%M:%S"))
print("Moscow (UTC+3):", moscow.strftime("%H:%M:%S"))
print("Local (no tz):", local.strftime("%H:%M:%S"))
print("now_sec (Moscow):", moscow.hour * 3600 + moscow.minute * 60 + moscow.second)
