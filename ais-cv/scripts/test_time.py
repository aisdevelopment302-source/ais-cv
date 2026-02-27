
from datetime import datetime, timezone
import time

# Current naive time
now = datetime.now()
print(f"Naive now: {now}")
print(f"Naive now strftime %H: {now.strftime('%H')}")

# Aware time (local)
try:
    now_aware = now.astimezone()
    print(f"Aware local: {now_aware}")
    print(f"Aware local strftime %H: {now_aware.strftime('%H')}")
    print(f"Aware local tzinfo: {now_aware.tzinfo}")
except Exception as e:
    print(f"astimezone failed: {e}")

# UTC time
now_utc = datetime.now(timezone.utc)
print(f"UTC now: {now_utc}")
