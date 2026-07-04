"""
server/services/osint/scanners/twitter.py
==========================================
Twitter / X OSINT scanner via RapidAPI + X_tool deep analytics.
"""

print("[ECHOMARK][scanners/twitter.py] Module loaded — Twitter/X scanner initializing")

import os
import json
import requests
from server.storage.cases import upsert_section
from server.services.osint.scanners.shared import RAPIDAPI_API_KEY, _log
from server.services.osint.scanners.sherlock import run_sherlock
from server.services.osint.scanners.X_tool.live_fetch import fetch_target_profile_rapid
from server.services.osint.scanners.X_tool.config import CLEAN_REPORT_DIR


def _load_cached_xtool_profile(username: str) -> dict:
    report_path = os.path.join(CLEAN_REPORT_DIR, f"{username.lstrip('@')}.json")
    if not os.path.exists(report_path):
        return {}

    try:
        with open(report_path, "r", encoding="utf-8") as f:
            cached = json.load(f)

        identity = cached.get("Target_Core_Identity", {})
        metrics = cached.get("Platform_Volume_Metrics", {})

        return {
            "name": identity.get("Target_Display_Name", username),
            "username": identity.get("Target_Username", username.lstrip("@")),
            "bio": identity.get("Profile_Bio_Text", ""),
            "followers": metrics.get("Followers_Count_Inbound", 0),
            "following": metrics.get("Following_Count_Outbound", 0),
            "tweets": metrics.get("Lifetime_Total_Posts_Posted", 0),
            "likes": 0,
            "verified": False,
            "created_at": cached.get("Case_Evidentiary_Metadata", {}).get("Account_Creation_Date", ""),
            "location": identity.get("Stated_Geographic_Location", ""),
            "website": "",
            "profile_pic_url": identity.get("Avatar_Image_URL", ""),
            "banner_url": "",
            "is_private": False,
            "source": "cache",
        }
    except Exception:
        return {}


def fetch_twitter(username: str) -> dict:
    print(f"[ECHOMARK][scanners/twitter.py] fetch_twitter: querying '{username}'")

    api_key = RAPIDAPI_API_KEY or os.environ.get("TWITTER_API45_KEY", "")
    headers = {
        "x-rapidapi-key": api_key,
        "x-rapidapi-host": "twitter-api45.p.rapidapi.com"
    }

    if not api_key:
        print("[ECHOMARK][scanners/twitter.py] fetch_twitter: RapidAPI key not set, trying cache fallback")
        cached = _load_cached_xtool_profile(username)
        if cached:
            return cached
        return {
            "name": username,
            "username": username.lstrip("@"),
            "bio": "",
            "followers": 0,
            "following": 0,
            "tweets": 0,
            "likes": 0,
            "verified": False,
            "created_at": "",
            "location": "",
            "website": "",
            "profile_pic_url": "",
            "banner_url": "",
            "is_private": False,
            "source": "degraded",
        }

    try:
        resp = requests.get(
            "https://twitter-api45.p.rapidapi.com/screenname.php",
            headers=headers,
            params={"screenname": username},
            timeout=15
        )
        if resp.status_code in (401, 403, 429):
            cached = _load_cached_xtool_profile(username)
            if cached:
                print(f"[ECHOMARK][scanners/twitter.py] fetch_twitter: using cache fallback after HTTP {resp.status_code}")
                return cached
            print(f"[ECHOMARK][scanners/twitter.py] fetch_twitter: HTTP {resp.status_code} from RapidAPI, returning degraded profile")
            return {
                "name": username,
                "username": username.lstrip("@"),
                "bio": "",
                "followers": 0,
                "following": 0,
                "tweets": 0,
                "likes": 0,
                "verified": False,
                "created_at": "",
                "location": "",
                "website": "",
                "profile_pic_url": "",
                "banner_url": "",
                "is_private": False,
                "source": "degraded",
            }

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
            "source":          "live",
        }
        print(f"[ECHOMARK][scanners/twitter.py] fetch_twitter: OK — followers={data['followers']}")
        return data

    except Exception as e:
        print(f"[ECHOMARK][scanners/twitter.py] fetch_twitter: error — {e}")
        cached = _load_cached_xtool_profile(username)
        if cached:
            print("[ECHOMARK][scanners/twitter.py] fetch_twitter: falling back to cached X_tool profile")
            return cached
        return {
            "name": username,
            "username": username.lstrip("@"),
            "bio": "",
            "followers": 0,
            "following": 0,
            "tweets": 0,
            "likes": 0,
            "verified": False,
            "created_at": "",
            "location": "",
            "website": "",
            "profile_pic_url": "",
            "banner_url": "",
            "is_private": False,
            "source": "degraded",
            "error": str(e),
        }


def scan_twitter(code: str, username: str) -> None:
    print(f"[ECHOMARK][scanners/twitter.py] scan_twitter: START code={code} username='{username}'")
    _log(code, f"[TWITTER] Scan started for '{username}'")

    # --- Twitter profile (existing RapidAPI call) ---
    profile = fetch_twitter(username)
    upsert_section(code, "twitter", {
        "section": "twitter",
        "query":   username,
        **profile,
        "status": "connected" if profile.get("source") == "live" else "degraded",
    })
    _log(code, f"[TWITTER] Profile section written — source={profile.get('source', 'unknown')}")

    # --- Related platforms via Sherlock ---
    sherlock_results = run_sherlock(username)
    upsert_section(code, "related_platforms", {
        "section":   "related_platforms",
        "query":     username,
        "platforms": sherlock_results,
        "source":    "sherlock"
    })
    _log(code, f"[TWITTER] Related platforms: {len(sherlock_results)} found via Sherlock")

    # --- X_tool deep analytics (analytics / sentiment / related_accounts) ---
    try:
        xtool_ok = fetch_target_profile_rapid(username)
    except Exception as e:
        xtool_ok = False
        print(f"[ECHOMARK][scanners/twitter.py] X_tool error: {e}")
        _log(code, f"[TWITTER] X_tool exception: {e}")

    if xtool_ok:
        try:
            report_path = os.path.join(CLEAN_REPORT_DIR, f"{username.lstrip('@')}.json")
            with open(report_path, "r", encoding="utf-8") as f:
                xdata = json.load(f)
            behavior = xdata.get("Behavioral_Frequency_Analysis", {})

            upsert_section(code, "analytics", {
                "section": "analytics", "query": username,
                "active_hours": behavior.get("Temporal_Hourly_Post_Profile_UTC", {}),
                "note": "Derived from X_tool timeline analysis"
            })
            upsert_section(code, "sentiment", {
                "section": "sentiment", "query": username,
                "keywords": behavior.get("Most_Used_Hashtags_Clustering", {}),
                "note": "Hashtag clustering via X_tool"
            })
            upsert_section(code, "related_accounts", {
                "section": "related_accounts", "query": username,
                "accounts": behavior.get("Most_Interacted_With_Handles", {}),
                "note": "Interaction frequency via X_tool"
            })
            _log(code, "[TWITTER] X_tool analytics sections written")
        except Exception as e:
            print(f"[ECHOMARK][scanners/twitter.py] X_tool report read error: {e}")
            _log(code, f"[TWITTER] X_tool report read error: {e}")
            xtool_ok = False

    if not xtool_ok:
        _log(code, "[TWITTER] X_tool fetch failed — using placeholders")
        for section_name, key, val, note in [
            ("analytics", "active_hours", [], "X_tool fetch failed or quota exhausted."),
            ("sentiment", "keywords", [], "X_tool fetch failed or quota exhausted."),
            ("related_accounts", "accounts", [], "X_tool fetch failed or quota exhausted."),
        ]:
            upsert_section(code, section_name, {"section": section_name, "query": username, key: val, "note": note})

    # --- Remaining placeholder sections ---
    placeholders = [
        ("gallery",            "images",   [], "Media extraction requires Twitter API v2 bearer token."),
        ("media_intelligence", "media",    [], "Media intelligence requires scraped tweet media."),
        ("followers",          "followers",[], "Follower/following graph requires Twitter API v2 access."),
        ("correlation",        "correlations", [], "Awaiting more datapoints to establish cross-platform links."),
        ("reverse_image",      "results",  [], "Requires a target profile picture to initiate."),
        ("fake_account",       "indicators",[], "Bot detection requires scraped tweet engagement data."),
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