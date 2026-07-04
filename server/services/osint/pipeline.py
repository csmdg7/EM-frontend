"""
server/services/osint/pipeline.py
==================================
OSINT pipeline router.

This file is intentionally thin — it only:
  1. Resolves the case type to a bucket
  2. Dispatches to the correct scanner module
  3. Calls the AI summary generator at the end

All actual scanning logic lives in:
  scanners/instagram.py
  scanners/facebook.py
  scanners/twitter.py
  scanners/email.py
  scanners/phone.py
  scanners/username.py
  scanners/alias.py
  scanners/domain.py
  scanners/ai_summary.py
  scanners/sherlock.py   (shared tool)
  scanners/shared.py     (shared utilities)
"""

print("[ECHOMARK][services/osint/pipeline.py] Module loaded — OSINT pipeline router initializing")

from server.storage.cases import update_search_status
from server.services.osint.scanners.shared import _log

# Scanner imports
from server.services.osint.scanners.instagram  import scan_instagram
from server.services.osint.scanners.facebook   import scan_facebook
from server.services.osint.scanners.twitter    import scan_twitter
from server.services.osint.scanners.email      import scan_email
from server.services.osint.scanners.phone      import scan_phone
from server.services.osint.scanners.username   import scan_username
from server.services.osint.scanners.alias      import scan_alias
from server.services.osint.scanners.domain     import scan_domain
from server.services.osint.scanners.ai_summary import generate_ai_summary
from server.services.osint.scanners.dorking    import scan_dorking


# ------------------------------------------------------------------ #
#  Type bucket resolver
# ------------------------------------------------------------------ #

def _type_bucket(type_str: str) -> str:
    """
    Normalize a case type string into a pipeline bucket name.

    Returns one of:
      'email' | 'phone' | 'alias' | 'username' |
      'instagram' | 'facebook' | 'twitter' | 'tiktok' |
      'linkedin' | 'reddit' | 'ip' | 'domain'
    """
    t = type_str.lower().strip()

    if "email" in t:
        return "email"
    if "phone" in t:
        return "phone"
    if "alias" in t or ("name" in t and "username" not in t):
        return "alias"
    if "instagram" in t:
        return "instagram"
    if "facebook" in t:
        return "facebook"
    if "twitter" in t or t == "x":
        return "twitter"
    if "tiktok" in t:
        return "tiktok"
    if "linkedin" in t:
        return "linkedin"
    if "reddit" in t:
        return "reddit"
    if "username" in t or "social" in t:
        return "username"
    if "ip" in t:
        return "ip"
    if "domain" in t or "website" in t or "url" in t:
        return "domain"

    return "username"  # safe fallback


# ------------------------------------------------------------------ #
#  Main pipeline entry point (called in a background thread)
# ------------------------------------------------------------------ #

def run_osint_scanner(code: str, query: str, type_str: str) -> None:
    """
    Dispatch OSINT scan to the correct scanner module, then run AI summary.
    Called from routes/cases.py in a daemon thread.
    """
    print(f"[ECHOMARK][pipeline] run_osint_scanner: START — code={code} query='{query}' type='{type_str}'")
    update_search_status(code, "Scanning")
    _log(code, f"[PIPELINE] Scan started — query='{query}' type='{type_str}'")

    bucket = _type_bucket(type_str)
    print(f"[ECHOMARK][pipeline] run_osint_scanner: bucket resolved → '{bucket}'")
    _log(code, f"[PIPELINE] Type bucket → '{bucket}'")

    try:
        if bucket == "email":
            scan_email(code, query)

        elif bucket == "phone":
            scan_phone(code, query)

        elif bucket == "alias":
            scan_alias(code, query)

        elif bucket == "instagram":
            scan_instagram(code, query)

        elif bucket == "facebook":
            scan_facebook(code, query)

        elif bucket == "twitter":
            scan_twitter(code, query)

        elif bucket in ("ip", "domain"):
            scan_domain(code, query)

        elif bucket in ("tiktok", "linkedin", "reddit"):
            # No dedicated scanner yet — fall back to username (Sherlock covers these)
            print(f"[ECHOMARK][pipeline] run_osint_scanner: no dedicated scanner for '{bucket}' — using username scanner")
            _log(code, f"[PIPELINE] No dedicated scanner for '{bucket}' — running username fallback")
            scan_username(code, query)

        else:
            # Generic username fallback
            scan_username(code, query)

        # AI summary runs for every case after all sections are written
        generate_ai_summary(code, query, type_str)
        scan_dorking(code, query, type_str)

    except Exception as e:
        print(f"[ECHOMARK][pipeline] run_osint_scanner: UNHANDLED ERROR — {e}")
        _log(code, f"[PIPELINE] ERROR: {e}")

    finally:
        update_search_status(code, "Completed")
        _log(code, "[PIPELINE] Scan completed")
        print(f"[ECHOMARK][pipeline] run_osint_scanner: END — code={code}")


print("[ECHOMARK][services/osint/pipeline.py] Module ready — run_osint_scanner registered")
