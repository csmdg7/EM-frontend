"""
server/services/osint/scanners/twitter.py
==========================================
Twitter / X OSINT scanner via RapidAPI.

API used: twitter-api45.p.rapidapi.com

Exports:
    scan_twitter(code, username) -> None
    fetch_twitter(username)      -> dict
"""

print("[ECHOMARK][scanners/twitter.py] Module loaded — Twitter/X scanner initializing")

import requests
from server.storage.cases import upsert_section
from server.services.osint.scanners.shared import RAPIDAPI_API_KEY, _log
from server.services.osint.scanners.sherlock import run_sherlock


def fetch_twitter(username: str) -> dict:
    """
    Call RapidAPI Twitter scraper.
    Returns a cleaned dict or {"error": "..."} on failure.
    """
    print(f"[ECHOMARK][scanners/twitter.py] fetch_twitter: querying '{username}'")

    if not RAPIDAPI_API_KEY:
        print("[ECHOMARK][scanners/twitter.py] fetch_twitter: RAPIDAPI_API_KEY not set")
        return {"error": "RAPIDAPI_API_KEY not configured"}

    try:
        resp = requests.get(
            "https://twitter-api45.p.rapidapi.com/screenname.php",
            headers={
                "x-rapidapi-key":  RAPIDAPI_API_KEY,
                "x-rapidapi-host": "twitter-api45.p.rapidapi.com"
            },
            params={"screenname": username},
            timeout=15
        )
        resp.raise_for_status()
        raw = resp.json()

        data = {
            "name":            raw.get("name", ""),
            "username":        raw.get("screen_name", username),
            "bio":             raw.get("description", ""),
            "followers":       raw.get("followers_count", 0),
            "following":       raw.get("friends_count", 0),
            "tweets":          raw.get("statuses_count", 0),
            "likes":           raw.get("favourites_count", 0),
            "verified":        raw.get("verified", False),
            "created_at":      raw.get("created_at", ""),
            "location":        raw.get("location", ""),
            "website":         raw.get("url", ""),
            "profile_pic_url": raw.get("profile_image_url_https", ""),
            "banner_url":      raw.get("profile_banner_url", ""),
            "is_private":      raw.get("protected", False),
        }
        print(f"[ECHOMARK][scanners/twitter.py] fetch_twitter: OK — followers={data['followers']}")
        return data

    except Exception as e:
        print(f"[ECHOMARK][scanners/twitter.py] fetch_twitter: error — {e}")
        return {"error": str(e)}


def scan_twitter(code: str, username: str) -> None:
    """
    Full Twitter/X pipeline for a case.
    Writes sections: twitter, related_platforms, gallery,
    related_accounts, analytics, sentiment, media_intelligence,
    followers, correlation, reverse_image, fake_account.
    """
    print(f"[ECHOMARK][scanners/twitter.py] scan_twitter: START code={code} username='{username}'")
    _log(code, f"[TWITTER] Scan started for '{username}'")

    # --- Twitter profile ---
    profile = fetch_twitter(username)
    upsert_section(code, "twitter", {
        "section": "twitter",
        "query":   username,
        **profile
    })
    _log(code, f"[TWITTER] Profile section written — error={profile.get('error', 'none')}")

    # --- Related platforms via Sherlock ---
    sherlock_results = run_sherlock(username)
    upsert_section(code, "related_platforms", {
        "section":   "related_platforms",
        "query":     username,
        "platforms": sherlock_results,
        "source":    "sherlock"
    })
    _log(code, f"[TWITTER] Related platforms: {len(sherlock_results)} found via Sherlock")

    # --- Placeholder sections ---
    placeholders = [
        ("gallery",           "images",       [],  "Media extraction requires Twitter API v2 bearer token."),
        ("related_accounts",  "accounts",     [],  "Cross-platform correlation requires more datapoints."),
        ("analytics",         "active_hours", [],  "Tweet frequency analysis requires scraped timeline data."),
        ("sentiment",         "keywords",     [],  "Sentiment analysis requires scraped tweet content."),
        ("media_intelligence","media",        [],  "Media intelligence requires scraped tweet media."),
        ("followers",         "followers",    [],  "Follower/following graph requires Twitter API v2 access."),
        ("correlation",       "correlations", [],  "Awaiting more datapoints to establish cross-platform links."),
        ("reverse_image",     "results",      [],  "Requires a target profile picture to initiate."),
        ("fake_account",      "indicators",   [],  "Bot detection requires scraped tweet engagement data."),
    ]
    for section_name, key, val, note in placeholders:
        upsert_section(code, section_name, {
            "section": section_name,
            "query":   username,
            key:       val,
            "note":    note
        })

    _log(code, "[TWITTER] All sections written")
    print(f"[ECHOMARK][scanners/twitter.py] scan_twitter: END code={code}")


print("[ECHOMARK][scanners/twitter.py] Module ready — fetch_twitter, scan_twitter exported")
