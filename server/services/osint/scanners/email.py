"""
server/services/osint/scanners/email.py
========================================
Email OSINT scanner.

APIs:
  1. RapidAPI "Email Social Media Checker"  — breach + registered-platform data
  2. RapidAPI "Google Data" (airaudoeduardo/google-data) — Google account,
     profile photo, Maps reviews, presence

Exports:
    scan_email(code, email) -> None
"""

print("[ECHOMARK][scanners/email.py] Module loaded — Email scanner initializing")

import os
import requests
from urllib.parse import quote

from server.storage.cases import upsert_section, update_search_status
from server.services.osint.scanners.shared import _log

RAPIDAPI_API_KEY   = os.environ.get("RAPIDAPI_API_KEY", "")
RAPIDAPI_HOST      = "email-social-media-checker.p.rapidapi.com"

GOOGLEDATA_API_KEY = os.environ.get("GOOGLEDATA_API_KEY", "")
GOOGLEDATA_HOST    = os.environ.get("GOOGLEDATA_HOST", "google-data.p.rapidapi.com")


# ------------------------------------------------------------------ #
#  Email Social Media Checker
# ------------------------------------------------------------------ #

def _fetch_email_intel(email: str) -> dict:
    print(f"[ECHOMARK][scanners/email.py] _fetch_email_intel: querying '{email}'")
    if not RAPIDAPI_API_KEY:
        print("[ECHOMARK][scanners/email.py] _fetch_email_intel: RAPIDAPI_API_KEY not set")
        return {"status": False, "error": "RAPIDAPI_API_KEY not configured"}
    try:
        resp = requests.get(
            f"https://{RAPIDAPI_HOST}/check_email?email={quote(email)}",
            headers={"X-RapidAPI-Key": RAPIDAPI_API_KEY,
                     "X-RapidAPI-Host": RAPIDAPI_HOST,
                     "Content-Type": "application/json"},
            timeout=30
        )
        print(f"[ECHOMARK][scanners/email.py] _fetch_email_intel: HTTP {resp.status_code}")
        resp.raise_for_status()
        data = resp.json()
        if not data.get("status"):
            return {"status": False, "error": "API returned no data for this email"}
        print(f"[ECHOMARK][scanners/email.py] _fetch_email_intel: OK — score={data.get('data', {}).get('score')}")
        return data
    except requests.exceptions.RequestException as e:
        print(f"[ECHOMARK][scanners/email.py] _fetch_email_intel: failed — {e}")
        return {"status": False, "error": str(e)}
    except Exception as e:
        print(f"[ECHOMARK][scanners/email.py] _fetch_email_intel: unexpected error — {e}")
        return {"status": False, "error": str(e)}


# ------------------------------------------------------------------ #
#  Google Data API
#  Endpoint: GET /email/{email}?noReviews=false&cached=false
# ------------------------------------------------------------------ #

def _fetch_google_data(email: str) -> dict:
    """
    Returns flattened dict with found=True/False.
    All nested structures from the API response are flattened before storage.
    Maps reviews are extracted and included if present.
    """
    print(f"[ECHOMARK][scanners/email.py] _fetch_google_data: querying '{email}'")
    if not GOOGLEDATA_API_KEY:
        print("[ECHOMARK][scanners/email.py] _fetch_google_data: GOOGLEDATA_API_KEY not set")
        return {"found": False, "error": "GOOGLEDATA_API_KEY not configured"}
    try:
        resp = requests.get(
            f"https://{GOOGLEDATA_HOST}/email/{quote(email)}",
            headers={"X-RapidAPI-Key":  GOOGLEDATA_API_KEY,
                     "X-RapidAPI-Host": GOOGLEDATA_HOST,
                     "Content-Type":    "application/json"},
            params={"noReviews": "false", "cached": "false"},
            timeout=20
        )
        print(f"[ECHOMARK][scanners/email.py] _fetch_google_data: HTTP {resp.status_code}")
        resp.raise_for_status()
        raw = resp.json()

        container = raw.get("PROFILE_CONTAINER", {})
        profile   = container.get("profile", {}) or {}
        person_id = profile.get("personId", "")

        if not person_id:
            print(f"[ECHOMARK][scanners/email.py] _fetch_google_data: no Google account for '{email}'")
            return {"found": False}

        # Safely extract nested blocks
        emails_block = (profile.get("emails") or {}).get("PROFILE", {}) or {}
        photo_block  = (profile.get("profilePhotos") or {}).get("PROFILE", {}) or {}
        names_block  = (profile.get("names") or {}).get("PROFILE", {}) or {}
        info_block   = (profile.get("profileInfos") or {}).get("PROFILE", {}) or {}
        reach_block  = (profile.get("inAppReachability") or {}).get("PROFILE", {}) or {}
        source_block = (profile.get("sourceIds") or {}).get("PROFILE", {}) or {}
        extended     = profile.get("extendedData") or {}
        dynamite     = extended.get("dynamiteData") or {}
        gplus        = extended.get("gplusData") or {}
        cust_raw     = dynamite.get("customerId")
        customer_id  = (cust_raw.get("customerId", "") if isinstance(cust_raw, dict) else "") or ""

        maps_block = container.get("maps") or {}

        # Extract Maps reviews
        reviews_raw = maps_block.get("reviews") or []
        maps_reviews = [{
            "place":   r.get("location", {}).get("name", "") if isinstance(r.get("location"), dict) else "",
            "address": r.get("location", {}).get("address", "") if isinstance(r.get("location"), dict) else "",
            "rating":  r.get("rating", 0),
            "comment": r.get("comment", ""),
            "date":    r.get("date", ""),
            "likes":   r.get("likes", 0),
            "link":    r.get("link", ""),
        } for r in reviews_raw]

        # Maps stats
        maps_stats = maps_block.get("stats") or {}

        # Contributor info from enhanced_data if present
        enhanced      = maps_block.get("enhanced_data") or {}
        contrib_info  = enhanced.get("contributor_info") or {}
        local_guide   = contrib_info.get("local_guide", False)
        guide_level   = contrib_info.get("level", 0)
        guide_points  = contrib_info.get("points", 0)

        flat = {
            "found":               True,
            "person_id":           person_id,
            "verified_email":      emails_block.get("value", email),
            "full_name":           names_block.get("fullname", ""),
            "first_name":          names_block.get("firstName", ""),
            "last_name":           names_block.get("lastName", ""),
            "profile_photo_url":   photo_block.get("url", ""),
            "is_default_photo":    photo_block.get("isDefault", True),
            "user_types":          info_block.get("userTypes", []),
            "reachable_apps":      reach_block.get("apps", []),
            "last_updated":        source_block.get("lastUpdated", ""),
            "presence":            dynamite.get("presence", ""),
            "entity_type":         dynamite.get("entityType", ""),
            "dnd_state":           dynamite.get("dndState", ""),
            "customer_id":         customer_id,
            "is_enterprise_user":  gplus.get("isEntrepriseUser", False),
            "has_play_games":      container.get("play_games") is not None,
            "has_calendar":        container.get("calendar") is not None,
            "maps_reviews":        maps_reviews,
            "maps_reviews_count":  len(maps_reviews),
            "maps_stats":          maps_stats,
            "is_local_guide":      local_guide,
            "local_guide_level":   guide_level,
            "local_guide_points":  guide_points,
        }
        print(f"[ECHOMARK][scanners/email.py] _fetch_google_data: OK — person_id={person_id} reviews={len(maps_reviews)}")
        return flat

    except requests.exceptions.RequestException as e:
        print(f"[ECHOMARK][scanners/email.py] _fetch_google_data: request failed — {e}")
        return {"found": False, "error": str(e)}
    except Exception as e:
        print(f"[ECHOMARK][scanners/email.py] _fetch_google_data: unexpected error — {e}")
        return {"found": False, "error": str(e)}


# ------------------------------------------------------------------ #
#  Main pipeline
# ------------------------------------------------------------------ #

def scan_email(code: str, email: str) -> None:
    """
    Writes sections: basic, google_account, connected_socials, databreach.
    """
    print(f"[ECHOMARK][scanners/email.py] scan_email: START code={code} email='{email}'")
    update_search_status(code, "Scanning...")
    _log(code, f"[EMAIL] Scan started for '{email}'")

    local_part = email.split("@")[0] if "@" in email else email
    domain     = email.split("@")[1] if "@" in email else ""

    upsert_section(code, "basic", {
        "section":    "basic",
        "query":      email,
        "type":       "email",
        "local_part": local_part,
        "domain":     domain,
        "notes":      "Email target — querying breach checker and Google account API.",
    })

    # --- Google account lookup ---
    update_search_status(code, "Checking Google account...")
    google = _fetch_google_data(email)
    if google.get("found"):
        # Strip "found" key, write everything else flat
        upsert_section(code, "google_account", {
            "section": "google_account",
            "email":   email,
            **{k: v for k, v in google.items() if k != "found"},
            "note": "Active Google account found.",
        })
        _log(code, f"[EMAIL] Google account found — person_id={google.get('person_id')} reviews={google.get('maps_reviews_count', 0)}")
    else:
        upsert_section(code, "google_account", {
            "section": "google_account",
            "email":   email,
            "found":   False,
            "note":    google.get("error") or "No Google account associated with this email.",
        })
        _log(code, f"[EMAIL] Google account: {'error — ' + google.get('error') if google.get('error') else 'not found'}")

    # --- Email Social Media Checker ---
    update_search_status(code, "Scanning Breach Databases...")
    raw = _fetch_email_intel(email)

    if not raw.get("status"):
        err = raw.get("error", "Unknown error")
        _log(code, f"[EMAIL] Breach checker failed — {err}")
        upsert_section(code, "connected_socials", {"section": "connected_socials", "query": email, "profiles": [], "source": "email-social-media-checker", "note": err})
        upsert_section(code, "databreach",        {"section": "databreach",        "email": email, "breach_count": 0, "breaches": [], "note": err})
        print(f"[ECHOMARK][scanners/email.py] scan_email: END (breach checker failed) code={code}")
        return

    payload      = raw.get("data", {})
    breach_block = payload.get("dataBreaches", {})
    breaches_raw = breach_block.get("breaches", [])
    is_breached  = len(breaches_raw) > 0
    name_of_breaches = [b.get("name") for b in breaches_raw if b.get("name")]

    profiles_block = payload.get("profiles", {})
    registered     = profiles_block.get("registered", [])
    not_registered = profiles_block.get("notRegistered", [])

    upsert_section(code, "connected_socials", {
        "section":          "connected_socials",
        "query":            email,
        "profiles":         [{"platform": p, "status": "found", "source": "email-social-media-checker"} for p in registered],
        "registered_count": len(registered),
        "not_registered":   not_registered,
        "source":           "email-social-media-checker",
    })
    _log(code, f"[EMAIL] Social accounts found: {len(registered)}")

    upsert_section(code, "databreach", {
        "section":       "databreach",
        "email":         email,
        "is_breached":   is_breached,
        "breach_count":  breach_block.get("numberOfBreaches", len(breaches_raw)),
        "first_breach":  breach_block.get("firstBreach"),
        "breaches":      breaches_raw,
        "breach_names":  name_of_breaches,
        "domain_intel":  payload.get("domain", {}),
        "score":         payload.get("score", 0),
        "applied_rules": payload.get("appliedRules", []),
        "note":          f"{len(name_of_breaches)} breach source(s) found." if is_breached else "No known breaches.",
    })
    _log(code, f"[EMAIL] Breach: {'BREACHED (' + str(len(name_of_breaches)) + ')' if is_breached else 'Clean'}")

    _log(code, "[EMAIL] All sections written")
    print(f"[ECHOMARK][scanners/email.py] scan_email: END code={code}")


print("[ECHOMARK][scanners/email.py] Module ready — scan_email exported")


# ------------------------------------------------------------------ #
#  Retry-callable sub-functions
# ------------------------------------------------------------------ #

def _write_google_section(code: str, email: str) -> None:
    """Retry only the Google Data lookup for a case."""
    print(f"[ECHOMARK][scanners/email.py] _write_google_section: retrying for {email}")
    update_search_status(code, "Retrying Google Account lookup...")
    google = _fetch_google_data(email)
    if google.get("found"):
        upsert_section(code, "google_account", {
            "section": "google_account", "email": email,
            **{k: v for k, v in google.items() if k != "found"},
            "note": "Active Google account found.",
        })
    else:
        upsert_section(code, "google_account", {
            "section": "google_account", "email": email, "found": False,
            "note": google.get("error") or "No Google account found.",
        })
    _log(code, f"[EMAIL] Google retry: {'found' if google.get('found') else 'not found'}")


def _write_breach_section(code: str, email: str) -> None:
    """Retry only the Email Social Media Checker for a case."""
    print(f"[ECHOMARK][scanners/email.py] _write_breach_section: retrying for {email}")
    update_search_status(code, "Retrying breach check...")
    raw = _fetch_email_intel(email)
    if not raw.get("status"):
        err = raw.get("error", "Unknown")
        upsert_section(code, "connected_socials", {"section": "connected_socials", "query": email, "profiles": [], "note": err})
        upsert_section(code, "databreach",        {"section": "databreach", "email": email, "breach_count": 0, "breaches": [], "note": err})
        _log(code, f"[EMAIL] Breach retry failed: {err}")
        return
    payload      = raw.get("data", {})
    breach_block = payload.get("dataBreaches", {})
    breaches_raw = breach_block.get("breaches", [])
    is_breached  = len(breaches_raw) > 0
    registered   = payload.get("profiles", {}).get("registered", [])
    upsert_section(code, "connected_socials", {
        "section": "connected_socials", "query": email,
        "profiles": [{"platform": p, "status": "found", "source": "email-social-media-checker"} for p in registered],
        "registered_count": len(registered), "source": "email-social-media-checker",
    })
    upsert_section(code, "databreach", {
        "section": "databreach", "email": email,
        "is_breached": is_breached,
        "breach_count": breach_block.get("numberOfBreaches", len(breaches_raw)),
        "breaches": breaches_raw,
        "breach_names": [b.get("name") for b in breaches_raw if b.get("name")],
        "note": f"{len(breaches_raw)} breach(es) found." if is_breached else "No known breaches.",
    })
    _log(code, f"[EMAIL] Breach retry: {'BREACHED' if is_breached else 'Clean'}")
