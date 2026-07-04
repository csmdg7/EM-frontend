"""
server/services/osint/scanners/shared.py
=========================================
Shared utilities imported by every scanner module:
  - _now()             timestamp string
  - _log()             write to case log + stdout
  - RAPIDAPI_API_KEY   env var (must match the name in .env exactly)
  - GEMINI_KEY         env var
"""

print("[ECHOMARK][scanners/shared.py] Module loaded — shared utilities initializing")

import os
from datetime import datetime, timezone
from server.storage.cases import prepend_logs

RAPIDAPI_API_KEY = os.environ.get("RAPIDAPI_API_KEY", "")
GEMINI_KEY       = os.environ.get("GEMINI_API_KEY", "")

print(f"[ECHOMARK][scanners/shared.py] RAPIDAPI_API_KEY loaded: {'YES (' + str(len(RAPIDAPI_API_KEY)) + ' chars)' if RAPIDAPI_API_KEY else 'NO — empty/missing'}")
print(f"[ECHOMARK][scanners/shared.py] GEMINI_KEY loaded: {'YES (' + str(len(GEMINI_KEY)) + ' chars)' if GEMINI_KEY else 'NO — empty/missing'}")


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%MZ")


def _log(code: str, msg: str) -> None:
    prepend_logs(code, [f"{_now()} — {msg}"])
    print(f"[ECHOMARK][pipeline] [{code}] {msg}")


print("[ECHOMARK][scanners/shared.py] Module ready — _now, _log, RAPIDAPI_API_KEY, GEMINI_KEY exported")
