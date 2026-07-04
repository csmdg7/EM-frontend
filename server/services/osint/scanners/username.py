"""
server/services/osint/scanners/username.py
==========================================
Generic username OSINT scanner.

Used when case type is "username" with no specific platform.
Runs Sherlock across all platforms and writes all standard sections.

Exports:
    scan_username(code, username) -> None
"""

print("[ECHOMARK][scanners/username.py] Module loaded — Username scanner initializing")

from server.storage.cases import upsert_section
from server.services.osint.scanners.shared import _log
from server.services.osint.scanners.sherlock import run_sherlock


def scan_username(code: str, username: str) -> None:
    """
    Full generic username OSINT pipeline.
    Writes all standard sections for non-email/phone targets.
    """
    print(f"[ECHOMARK][scanners/username.py] scan_username: START code={code} username='{username}'")
    _log(code, f"[USERNAME] Scan started for '{username}'")

    # --- Basic ---
    upsert_section(code, "basic", {
        "section": "basic",
        "query":   username,
        "type":    "username",
        "notes":   "Username target — running Sherlock cross-platform probe."
    })

    # --- Gallery placeholder ---
    upsert_section(code, "gallery", {
        "section": "gallery",
        "query":   username,
        "images":  [],
        "note":    "Profile image extraction requires a platform-specific scrape."
    })
    _log(code, "[USERNAME] Gallery section written (pending scrape)")

    # --- Related platforms via Sherlock ---
    sherlock_results = run_sherlock(username)
    upsert_section(code, "related_platforms", {
        "section":   "related_platforms",
        "query":     username,
        "platforms": sherlock_results,
        "source":    "sherlock"
    })
    _log(code, f"[USERNAME] Related platforms: {len(sherlock_results)} found via Sherlock")

    # --- Related accounts placeholder ---
    upsert_section(code, "related_accounts", {
        "section":  "related_accounts",
        "query":    username,
        "accounts": [],
        "accuracy": "80%",
        "note":     "Cross-platform account correlation requires more datapoints."
    })

    # --- Analytics placeholder ---
    upsert_section(code, "analytics", {
        "section":       "analytics",
        "query":         username,
        "active_hours":  [],
        "timeline":      [],
        "pattern_match": "Insufficient data — activity analytics requires scraped post timestamps."
    })

    # --- Sentiment placeholder ---
    upsert_section(code, "sentiment", {
        "section":          "sentiment",
        "query":            username,
        "behavior_score":   0,
        "sentiment_label":  "Unknown",
        "extracted_bio":    "",
        "keywords":         [],
        "captions":         [],
        "behavior_verdict": "No data available — sentiment analysis requires scraped post content."
    })

    # --- Media intelligence placeholder ---
    upsert_section(code, "media_intelligence", {
        "section": "media_intelligence",
        "query":   username,
        "media":   [],
        "note":    "Media intelligence requires platform-specific scraping."
    })

    # --- Followers placeholder ---
    upsert_section(code, "followers", {
        "section":   "followers",
        "query":     username,
        "followers": [],
        "following": [],
        "friends":   [],
        "note":      "Social graph extraction requires authenticated platform API access."
    })

    # --- Correlation placeholder ---
    upsert_section(code, "correlation", {
        "section":      "correlation",
        "query":        username,
        "correlations": [],
        "note":         "Awaiting more datapoints to establish cross-platform links."
    })

    # --- Reverse image placeholder ---
    upsert_section(code, "reverse_image", {
        "section": "reverse_image",
        "query":   username,
        "results": [],
        "note":    "Requires a target profile picture to initiate reverse image search."
    })

    # --- Fake account check placeholder ---
    upsert_section(code, "fake_account", {
        "section":    "fake_account",
        "query":      username,
        "verdict":    "Pending",
        "confidence": 0,
        "indicators": [],
        "note":       "Bot detection requires scraped engagement metrics and post patterns."
    })

    _log(code, "[USERNAME] All sections written")
    print(f"[ECHOMARK][scanners/username.py] scan_username: END code={code}")


print("[ECHOMARK][scanners/username.py] Module ready — scan_username exported")
