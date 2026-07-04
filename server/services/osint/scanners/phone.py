"""
server/services/osint/scanners/phone.py
========================================
Phone number OSINT scanner.

Tools used:
  - Sherlock on sanitized digit string
  - NumLookupAPI for carrier/country lookup (free tier)
  - Google Dork query generation

Exports:
    scan_phone(code, phone) -> None
"""

print("[ECHOMARK][scanners/phone.py] Module loaded — Phone scanner initializing")

import re
import requests
from server.storage.cases import upsert_section
from server.services.osint.scanners.shared import _log
from server.services.osint.scanners.sherlock import run_sherlock


def _fetch_phone_info(phone: str) -> dict:
    """
    Query NumLookupAPI (free, no key required) for basic phone metadata.
    Returns dict or {"error": "..."} on failure.
    """
    print(f"[ECHOMARK][scanners/phone.py] _fetch_phone_info: querying '{phone}'")
    # Strip non-digits for API call
    digits = re.sub(r"\D", "", phone)
    try:
        resp = requests.get(
            f"https://api.numlookupapi.com/v1/validate/{digits}",
            timeout=10
        )
        resp.raise_for_status()
        raw = resp.json()
        data = {
            "valid":           raw.get("valid", False),
            "number":          raw.get("number", phone),
            "local_format":    raw.get("local_format", ""),
            "international":   raw.get("international_format", ""),
            "country_prefix":  raw.get("country_prefix", ""),
            "country_code":    raw.get("country_code", ""),
            "country_name":    raw.get("country_name", ""),
            "location":        raw.get("location", ""),
            "carrier":         raw.get("carrier", ""),
            "line_type":       raw.get("line_type", ""),
        }
        print(f"[ECHOMARK][scanners/phone.py] _fetch_phone_info: OK — country={data['country_name']} carrier={data['carrier']}")
        return data
    except Exception as e:
        print(f"[ECHOMARK][scanners/phone.py] _fetch_phone_info: error — {e}")
        return {"error": str(e)}


def scan_phone(code: str, phone: str) -> None:
    """
    Full phone OSINT pipeline.
    Writes sections: basic, connected_socials, databreach, dorking.
    """
    print(f"[ECHOMARK][scanners/phone.py] scan_phone: START code={code} phone='{phone}'")
    _log(code, f"[PHONE] Scan started for '{phone}'")

    digits = re.sub(r"\D", "", phone)

    # --- Phone metadata lookup ---
    phone_info = _fetch_phone_info(phone)
    upsert_section(code, "basic", {
        "section":  "basic",
        "query":    phone,
        "type":     "phone",
        "digits":   digits,
        "notes":    "Phone target — carrier and location lookup performed.",
        **{k: v for k, v in phone_info.items() if k != "error"},
        **({"lookup_error": phone_info["error"]} if "error" in phone_info else {})
    })
    _log(code, f"[PHONE] Basic section updated — info_error={phone_info.get('error', 'none')}")

    # --- Connected socials via Sherlock on digit string ---
    sherlock_results = run_sherlock(digits)
    upsert_section(code, "connected_socials", {
        "section":  "connected_socials",
        "query":    phone,
        "profiles": sherlock_results,
        "source":   "sherlock"
    })
    _log(code, f"[PHONE] Connected socials: {len(sherlock_results)} found via Sherlock")

    # --- Databreach placeholder ---
    upsert_section(code, "databreach", {
        "section":  "databreach",
        "phone":    phone,
        "breaches": [],
        "note":     "Phone breach lookup requires a third-party SMS breach API (e.g. IntelX)."
    })
    _log(code, "[PHONE] Databreach section written (API not configured)")

    # --- Dorking queries ---
    upsert_section(code, "dorking", {
        "section": "dorking",
        "queries": [
            f'"{phone}"',
            f'"{digits}"',
            f'"{phone}" site:truecaller.com',
            f'"{phone}" site:linkedin.com',
            f'"{phone}" site:facebook.com',
            f'"{phone}" site:pastebin.com',
            f'"{phone}" filetype:pdf',
            f'"{digits}" intext:phone OR intext:contact',
        ],
        "note": "Run these queries manually in Google / Bing / DuckDuckGo."
    })
    _log(code, "[PHONE] Dorking queries generated")

    _log(code, "[PHONE] All sections written")
    print(f"[ECHOMARK][scanners/phone.py] scan_phone: END code={code}")


print("[ECHOMARK][scanners/phone.py] Module ready — scan_phone exported")
