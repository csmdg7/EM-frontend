"""
server/services/osint/scanners/facebook.py
==========================================
Facebook OSINT scanner via RapidAPI.

API used: facebook-scraper3.p.rapidapi.com

Exports:
    scan_facebook(code, username) -> None
    fetch_facebook(username)      -> dict
"""

print("[ECHOMARK][scanners/facebook.py] Module loaded — Facebook scanner initializing")

import requests
from server.storage.cases import upsert_section
from server.services.osint.scanners.shared import RAPIDAPI_API_KEY, _log
from server.services.osint.scanners.sherlock import run_sherlock


def fetch_facebook(username: str) -> dict:
    """
    Call RapidAPI Facebook scraper.
    Returns a cleaned dict or {"error": "..."} on failure.
    """
    print(f"[ECHOMARK][scanners/facebook.py] fetch_facebook: querying '{username}'")

    if not RAPIDAPI_API_KEY:
        print("[ECHOMARK][scanners/facebook.py] fetch_facebook: RAPIDAPI_API_KEY not set")
        return {"error": "RAPIDAPI_API_KEY not configured"}

    try:
        resp = requests.get(
            "https://facebook-scraper3.p.rapidapi.com/profile",
            headers={
                "x-rapidapi-key":  RAPIDAPI_API_KEY,
                "x-rapidapi-host": "facebook-scraper3.p.rapidapi.com"
            },
            params={"username": username},
            timeout=15
        )
        resp.raise_for_status()
        raw = resp.json()

        data = {
            "name":        raw.get("name", ""),
            "username":    raw.get("username", username),
            "profile_url": raw.get("profile_url", ""),
            "followers":   raw.get("followers", 0),
            "likes":       raw.get("likes", 0),
            "verified":    raw.get("verified", False),
            "about":       raw.get("about", ""),
            "location":    raw.get("location", ""),
            "website":     raw.get("website", ""),
            "joined":      raw.get("joined", ""),
            "cover_url":   raw.get("cover_url", ""),
        }
        print(f"[ECHOMARK][scanners/facebook.py] fetch_facebook: OK — followers={data['followers']}")
        return data

    except Exception as e:
        print(f"[ECHOMARK][scanners/facebook.py] fetch_facebook: error — {e}")
        return {"error": str(e)}


def scan_facebook(code: str, username: str) -> None:
    """
    Full Facebook pipeline for a case.
    Writes sections: facebook, related_platforms, gallery,
    related_accounts, analytics, sentiment, media_intelligence,
    followers, correlation, reverse_image, fake_account.
    """
    print(f"[ECHOMARK][scanners/facebook.py] scan_facebook: START code={code} username='{username}'")
    _log(code, f"[FACEBOOK] Scan started for '{username}'")

    # --- Facebook profile ---
    profile = fetch_facebook(username)
    upsert_section(code, "facebook", {
        "section": "facebook",
        "query":   username,
        **profile
    })
    _log(code, f"[FACEBOOK] Profile section written — error={profile.get('error', 'none')}")

    # --- Related platforms via Sherlock ---
    sherlock_results = run_sherlock(username)
    upsert_section(code, "related_platforms", {
        "section":   "related_platforms",
        "query":     username,
        "platforms": sherlock_results,
        "source":    "sherlock"
    })
    _log(code, f"[FACEBOOK] Related platforms: {len(sherlock_results)} found via Sherlock")

    # --- Placeholder sections ---
    placeholders = [
        ("gallery",           "images",       [],  "Photo album extraction requires authenticated Facebook API."),
        ("related_accounts",  "accounts",     [],  "Cross-platform correlation requires more datapoints."),
        ("analytics",         "active_hours", [],  "Activity analytics requires scraped post timestamps."),
        ("sentiment",         "keywords",     [],  "Sentiment analysis requires scraped posts/comments."),
        ("media_intelligence","media",        [],  "Media intelligence requires scraped photo/video data."),
        ("followers",         "followers",    [],  "Friend/follower graph requires authenticated API access."),
        ("correlation",       "correlations", [],  "Awaiting more datapoints to establish cross-platform links."),
        ("reverse_image",     "results",      [],  "Requires a target profile picture to initiate."),
        ("fake_account",      "indicators",   [],  "Bot detection requires scraped engagement metrics."),
    ]
    for section_name, key, val, note in placeholders:
        upsert_section(code, section_name, {
            "section": section_name,
            "query":   username,
            key:       val,
            "note":    note
        })

    _log(code, "[FACEBOOK] All sections written")
    print(f"[ECHOMARK][scanners/facebook.py] scan_facebook: END code={code}")


print("[ECHOMARK][scanners/facebook.py] Module ready — fetch_facebook, scan_facebook exported")
