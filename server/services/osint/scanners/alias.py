"""
server/services/osint/scanners/alias.py
========================================
Alias / Real Name OSINT scanner.

Used when case type is "alias/name".
Runs Sherlock on the sanitized name, generates targeted dork queries.

Exports:
    scan_alias(code, name) -> None
"""

print("[ECHOMARK][scanners/alias.py] Module loaded — Alias/Name scanner initializing")

from server.storage.cases import upsert_section
from server.services.osint.scanners.shared import _log
from server.services.osint.scanners.sherlock import run_sherlock


def scan_alias(code: str, name: str) -> None:
    """
    Full alias/name OSINT pipeline.
    Writes sections: basic, connected_socials, databreach, dorking.
    """
    print(f"[ECHOMARK][scanners/alias.py] scan_alias: START code={code} name='{name}'")
    _log(code, f"[ALIAS] Scan started for '{name}'")

    # Sanitize for Sherlock — remove spaces, lowercase
    handle = name.replace(" ", "").lower()

    # --- Basic ---
    upsert_section(code, "basic", {
        "section":       "basic",
        "query":         name,
        "type":          "alias/name",
        "sanitized":     handle,
        "notes":         "Alias/Name target — running cross-platform probe and generating dork queries."
    })
    _log(code, f"[ALIAS] Basic section written — sanitized='{handle}'")

    # --- Connected socials via Sherlock ---
    sherlock_results = run_sherlock(handle)
    upsert_section(code, "connected_socials", {
        "section":  "connected_socials",
        "query":    name,
        "profiles": sherlock_results,
        "source":   "sherlock"
    })
    _log(code, f"[ALIAS] Connected socials: {len(sherlock_results)} found via Sherlock")

    # --- Databreach placeholder (name alone can't query HIBP) ---
    upsert_section(code, "databreach", {
        "section":  "databreach",
        "name":     name,
        "breaches": [],
        "note":     "Name-based breach lookup not supported — correlate an email address to query HIBP."
    })
    _log(code, "[ALIAS] Databreach section written (email required)")

    # --- Dorking queries ---
    upsert_section(code, "dorking", {
        "section": "dorking",
        "queries": [
            f'"{name}"',
            f'"{name}" site:linkedin.com',
            f'"{name}" site:facebook.com',
            f'"{name}" site:twitter.com',
            f'"{name}" site:instagram.com',
            f'"{name}" site:github.com',
            f'"{name}" resume OR cv filetype:pdf',
            f'"{name}" email OR contact',
            f'"{handle}" site:reddit.com',
        ],
        "note": "Run these queries manually in Google / Bing / DuckDuckGo."
    })
    _log(code, "[ALIAS] Dorking queries generated")

    _log(code, "[ALIAS] All sections written")
    print(f"[ECHOMARK][scanners/alias.py] scan_alias: END code={code}")


print("[ECHOMARK][scanners/alias.py] Module ready — scan_alias exported")
