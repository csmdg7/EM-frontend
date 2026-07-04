"""
server/services/osint/scanners/sherlock.py
==========================================
Wrapper around the Sherlock CLI tool.

Exports:
    run_sherlock(username) -> list[dict]

Each dict: { platform, url, status, source }
Returns [] if Sherlock is not installed, times out, or finds nothing.
"""

print("[ECHOMARK][scanners/sherlock.py] Module loaded — Sherlock wrapper initializing")

import re
import subprocess


def run_sherlock(username: str) -> list:
    """
    Run Sherlock CLI against a username.
    Returns a list of found-platform dicts.
    """
    print(f"[ECHOMARK][scanners/sherlock.py] run_sherlock: querying '{username}'")
    try:
        result = subprocess.run(
            ["sherlock", username, "--print-found", "--no-color", "--timeout", "15"],
            capture_output=True, text=True, timeout=120
        )
        found = []
        for line in result.stdout.splitlines():
            # Sherlock output: [+] PlatformName: https://url
            m = re.match(r"\[\+\]\s+(.+?):\s+(https?://\S+)", line)
            if m:
                found.append({
                    "platform": m.group(1).strip(),
                    "url":      m.group(2).strip(),
                    "status":   "found",
                    "source":   "sherlock"
                })
        print(f"[ECHOMARK][scanners/sherlock.py] run_sherlock: found {len(found)} results for '{username}'")
        return found

    except FileNotFoundError:
        print("[ECHOMARK][scanners/sherlock.py] run_sherlock: Sherlock not installed — skipping")
        return []
    except subprocess.TimeoutExpired:
        print(f"[ECHOMARK][scanners/sherlock.py] run_sherlock: timeout for '{username}'")
        return []
    except Exception as e:
        print(f"[ECHOMARK][scanners/sherlock.py] run_sherlock: error — {e}")
        return []


print("[ECHOMARK][scanners/sherlock.py] Module ready — run_sherlock exported")
