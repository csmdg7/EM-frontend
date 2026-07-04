"""
server/routes/intel.py
=======================
Intel endpoints: active-scrape, analyze-image
"""

print("[ECHOMARK][routes/intel.py] Module loaded — intel blueprint initializing")

import os
import re
import json
import base64
import requests
from datetime import datetime, timezone

from flask import Blueprint, request, jsonify
from server.storage.cases import (
    get_case_record,
    upsert_section,
    prepend_logs,
)

intel_bp = Blueprint("intel", __name__)

GEMINI_KEY   = os.environ.get("GEMINI_API_KEY", "")
RAPIDAPI_API_KEY = os.environ.get("RAPIDAPI_API_KEY", "")


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%MZ")


# ------------------------------------------------------------------ #
#  POST /api/active-scrape — One-off manual scrape endpoint
# ------------------------------------------------------------------ #

@intel_bp.post("/active-scrape")
def active_scrape():
    print("[ECHOMARK][routes/intel.py] POST /api/active-scrape called")
    data      = request.get_json(silent=True) or {}
    scan_type = data.get("type",  "").strip()
    value     = data.get("value", "").strip()

    if not scan_type or not value:
        return jsonify({"error": "Missing type or value"}), 400

    result = {}

    try:
        if scan_type == "url":
            target = value if value.startswith(("http://", "https://")) else "https://" + value
            headers = {"User-Agent": "Mozilla/5.0"}
            resp = requests.get(target, headers=headers, timeout=10)
            resp.raise_for_status()
            html    = resp.text
            title_m = re.search(r"<title[^>]*>([\s\S]*?)</title>", html, re.I)
            meta_m  = (re.search(r'<meta\s+name=["\']description["\']\s+content=["\']([^"\']*)', html, re.I) or
                       re.search(r'<meta\s+content=["\']([^"\']*)["\'][^>]*name=["\']description', html, re.I))
            result = {
                "title":       title_m.group(1).strip() if title_m else "",
                "description": meta_m.group(1).strip()  if meta_m  else "",
                "size_bytes":  len(html),
                "links_count": len(re.findall(r'href=["\']http', html, re.I)),
            }
            print(f"[ECHOMARK][routes/intel.py] active_scrape url: title='{result['title']}'")

        elif scan_type == "domain":
            domain  = re.sub(r"https?://", "", value).split("/")[0]
            dns_a   = requests.get(f"https://dns.google/resolve?name={domain}&type=A",  timeout=8).json()
            dns_mx  = requests.get(f"https://dns.google/resolve?name={domain}&type=MX", timeout=8).json()
            result  = {
                "domain":       domain,
                "a_records":    [a["data"] for a in dns_a.get("Answer", [])],
                "mx_records":   [a["data"] for a in dns_mx.get("Answer", [])],
            }
            print(f"[ECHOMARK][routes/intel.py] active_scrape domain: A={result['a_records']}")

        else:
            result = {"note": f"Manual scrape for type '{scan_type}' not implemented."}

        print(f"[ECHOMARK][routes/intel.py] active_scrape: success type={scan_type}")
        return jsonify({"success": True, "intel": result})

    except Exception as e:
        print(f"[ECHOMARK][routes/intel.py] active_scrape: ERROR — {e}")
        return jsonify({"error": "Scrape failed", "details": str(e)}), 500


# ------------------------------------------------------------------ #
#  POST /api/cases/<code>/analyze-image — Gemini visual forensics
# ------------------------------------------------------------------ #

@intel_bp.post("/cases/<code>/analyze-image")
def analyze_image(code):
    print(f"[ECHOMARK][routes/intel.py] POST /api/cases/{code}/analyze-image called")
    data       = request.get_json(silent=True) or {}
    image_url  = data.get("imageUrl",   "")
    base64_data= data.get("base64Data", "")

    if not image_url and not base64_data:
        return jsonify({"error": "Missing imageUrl or base64Data"}), 400

    if not GEMINI_KEY:
        return jsonify({"error": "GEMINI_API_KEY not configured"}), 500

    try:
        if base64_data:
            clean_b64  = re.sub(r"^data:image/\w+;base64,", "", base64_data)
            image_part = {"inline_data": {"mime_type": "image/jpeg", "data": clean_b64}}
        else:
            img_resp = requests.get(image_url, timeout=15)
            img_resp.raise_for_status()
            image_part = {
                "inline_data": {
                    "mime_type": img_resp.headers.get("Content-Type", "image/jpeg"),
                    "data":      base64.b64encode(img_resp.content).decode("utf-8"),
                }
            }

        prompt = (
            "You are a top-tier SOCMINT visual forensics investigator.\n"
            "Analyze the provided image and extract key forensic details. "
            "Return STRICT raw JSON only (no markdown):\n"
            '{"description":"...","estimatedLocation":"...","confidenceIndex":"...","clues":[...],"coordinates":"..."}'
        )

        gemini_url  = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_KEY}"
        gemini_resp = requests.post(gemini_url, json={
            "contents": [{"parts": [{"text": prompt}, image_part]}]
        }, timeout=30)
        gemini_resp.raise_for_status()

        raw_text     = gemini_resp.json()["candidates"][0]["content"]["parts"][0]["text"]
        sanitized    = re.sub(r"```json|```", "", raw_text, flags=re.I).strip()
        parsed_intel = json.loads(sanitized)

        print(f"[ECHOMARK][routes/intel.py] analyze_image: parsed OK location='{parsed_intel.get('estimatedLocation')}'")

        if get_case_record(code):
            ts = _now()
            prepend_logs(code, [
                f"{ts} — [FORENSICS] Image analysis: location={parsed_intel.get('estimatedLocation')} "
                f"confidence={parsed_intel.get('confidenceIndex')}"
            ])
            upsert_section(code, "reverse_image", {
                "section":              "reverse_image",
                "description":          parsed_intel.get("description", ""),
                "estimated_location":   parsed_intel.get("estimatedLocation", ""),
                "confidence":           parsed_intel.get("confidenceIndex", ""),
                "clues":                parsed_intel.get("clues", []),
                "coordinates":          parsed_intel.get("coordinates", ""),
                "analyzed_at":          ts,
            })

        return jsonify({"success": True, "forensics": parsed_intel})

    except Exception as e:
        print(f"[ECHOMARK][routes/intel.py] analyze_image: ERROR — {e}")
        return jsonify({"error": "Forensic analysis failed", "details": str(e)}), 500


print("[ECHOMARK][routes/intel.py] Module ready — intel_bp fully registered")


# ------------------------------------------------------------------ #
#  POST /api/cases/<code>/auto-osint — Autonomous AI OSINT agent
# ------------------------------------------------------------------ #

import threading
from server.storage.cases import (
    get_case_record,
    upsert_section as _upsert_section,
    prepend_logs   as _prepend_logs,
    update_search_status,
)

def _agent_log(code: str, msg: str) -> None:
    from datetime import datetime, timezone
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%MZ")
    _prepend_logs(code, [f"{ts} — [AUTO-AGENT] {msg}"])
    print(f"[ECHOMARK][auto-osint] [{code}] {msg}")


def _gemini_call(prompt: str, expect_json: bool = False):
    """Call Gemini 1.5 Flash. Returns text, or parsed dict/list if expect_json."""
    key = os.environ.get("GEMINI_API_KEY", "")
    if not key:
        return None
    try:
        resp = requests.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={key}",
            json={"contents": [{"parts": [{"text": prompt}]}]},
            timeout=30
        )
        resp.raise_for_status()
        text = resp.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
        if expect_json:
            import re as _re
            clean = _re.sub(r"```json|```", "", text, flags=_re.I).strip()
            return json.loads(clean)
        return text
    except Exception as e:
        print(f"[ECHOMARK][auto-osint] Gemini error: {e}")
        return None


def _safe_web_fetch(url: str, max_chars: int = 3000) -> str:
    """Fetch a URL safely, return truncated text."""
    try:
        r = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        import re as _re
        text = _re.sub(r"<[^>]+>", " ", r.text)
        text = _re.sub(r"\s+", " ", text).strip()
        return text[:max_chars]
    except Exception as e:
        return f"[fetch failed: {e}]"


def _run_auto_agent(code: str) -> None:
    """
    Autonomous OSINT agent. Runs in a background thread.
    Steps:
      1. Read all existing case sections + metadata.
      2. Ask Gemini to reason and produce a JSON action plan.
      3. Execute each action (scanner calls, web fetches).
      4. Ask Gemini for a final synthesis report.
      5. Write auto_osint_report section.
    """
    print(f"[ECHOMARK][auto-osint] _run_auto_agent: START code={code}")
    update_search_status(code, "Auto-AI Running...")
    _agent_log(code, "Autonomous OSINT agent started.")

    record = get_case_record(code)
    if not record:
        print(f"[ECHOMARK][auto-osint] Case {code} not found")
        return

    query    = record.get("query", "")
    type_str = record.get("type", "")
    sections = record.get("sections", [])

    # ── Step 1: Build context from existing sections ──────────────────
    context_parts = [f"Case: {code}", f"Target: {query} (type: {type_str})"]
    for s in sections:
        name = s.get("section", "")
        if name == "instagram":
            context_parts.append(f"Instagram: username={s.get('username')} followers={s.get('follower_count')} private={s.get('is_private')}")
        elif name == "google_account":
            if s.get("person_id"):
                context_parts.append(f"Google: person_id={s.get('person_id')} apps={s.get('reachable_apps')} reviews={s.get('maps_reviews_count')}")
        elif name == "databreach":
            context_parts.append(f"Breaches: {s.get('breach_count',0)} — {s.get('breach_names',[])} ")
        elif name == "connected_socials":
            profs = [p.get("platform","") for p in s.get("profiles",[])[:10]]
            context_parts.append(f"Social platforms: {profs}")
        elif name == "fake_account":
            context_parts.append(f"Fake account: verdict={s.get('verdict')} confidence={s.get('confidence')}%")
        elif name == "related_platforms":
            plats = [p.get("platform","") for p in s.get("platforms",[])[:8]]
            context_parts.append(f"Related platforms (Sherlock): {plats}")

    context = "\n".join(context_parts)

    # ── Step 2: Gemini plans the next actions ────────────────────────
    plan_prompt = f"""You are an autonomous OSINT AI agent. Here is all data collected so far:

{context}

Based on this, decide what actions to take next. Available tools:
- scan_email: scan an email address
- scan_username: scan a username on all platforms
- scan_instagram: fetch full Instagram profile
- scan_phone: scan a phone number
- scan_domain: DNS/IP lookup on a domain
- web_fetch: fetch a URL for more intel (use sparingly, only high-value URLs)
- web_search: search the web for a query string

Respond ONLY with a valid JSON array of up to 5 actions. Each action:
{{"tool": "<tool_name>", "params": {{"query": "<value>"}}, "reason": "<one-sentence reason>"}}

If no further actions are useful, return an empty array [].
No markdown, no explanation outside the JSON."""

    _agent_log(code, "Requesting action plan from Gemini...")
    actions = _gemini_call(plan_prompt, expect_json=True)

    if not isinstance(actions, list):
        _agent_log(code, "Gemini returned invalid action plan — skipping tool calls.")
        actions = []

    _agent_log(code, f"Action plan: {len(actions)} action(s) planned.")
    tool_outputs = []

    # ── Step 3: Execute actions ───────────────────────────────────────
    SCANNERS = {
        "scan_email":     ("server.services.osint.scanners.email",     "scan_email"),
        "scan_username":  ("server.services.osint.scanners.username",   "scan_username"),
        "scan_instagram": ("server.services.osint.scanners.instagram",  "scan_instagram"),
        "scan_phone":     ("server.services.osint.scanners.phone",      "scan_phone"),
        "scan_domain":    ("server.services.osint.scanners.domain",     "scan_domain"),
    }

    for i, action in enumerate(actions[:5]):  # hard cap at 5
        tool   = action.get("tool", "")
        params = action.get("params", {})
        reason = action.get("reason", "")
        query_val = params.get("query", "")

        _agent_log(code, f"Action {i+1}/{len(actions)}: {tool}({query_val}) — {reason}")

        if tool in SCANNERS:
            module_path, fn_name = SCANNERS[tool]
            try:
                import importlib
                mod = importlib.import_module(module_path)
                fn  = getattr(mod, fn_name)
                fn(code, query_val)
                tool_outputs.append(f"{tool}({query_val}): completed")
                _agent_log(code, f"{tool}({query_val}) ✓")
            except Exception as e:
                tool_outputs.append(f"{tool}({query_val}): error — {e}")
                _agent_log(code, f"{tool}({query_val}) ✗ — {e}")

        elif tool == "web_fetch" and query_val.startswith("http"):
            content = _safe_web_fetch(query_val)
            tool_outputs.append(f"web_fetch({query_val}): {content[:500]}")
            _agent_log(code, f"web_fetch: fetched {len(content)} chars")

        elif tool == "web_search":
            # Use DuckDuckGo HTML (no API key required)
            try:
                search_url = f"https://html.duckduckgo.com/html/?q={requests.utils.quote(query_val)}"
                raw = _safe_web_fetch(search_url, max_chars=2000)
                tool_outputs.append(f"web_search({query_val}): {raw[:500]}")
                _agent_log(code, f"web_search: got results for '{query_val}'")
            except Exception as e:
                tool_outputs.append(f"web_search({query_val}): error — {e}")

    # ── Step 4: Final synthesis report ───────────────────────────────
    updated_record  = get_case_record(code)
    updated_sections = updated_record.get("sections", []) if updated_record else sections
    updated_context = context + "\n\nAdditional tool outputs:\n" + "\n".join(tool_outputs)

    report_prompt = f"""You are an OSINT analyst. Given the following intelligence gathered autonomously:

{updated_context}

Write a comprehensive intelligence report about this target. Include:
1. Identity summary
2. Digital footprint (platforms, accounts found)
3. Risk indicators (breaches, fake account signals)
4. Location/context clues
5. Recommended follow-up actions

Be factual, professional. Do not fabricate data not present above."""

    _agent_log(code, "Generating final report via Gemini...")
    final_report = _gemini_call(report_prompt, expect_json=False)
    if not final_report:
        final_report = "Report generation failed — GEMINI_API_KEY not configured or Gemini returned no response."

    from datetime import datetime, timezone
    _upsert_section(code, "auto_osint_report", {
        "section":       "auto_osint_report",
        "query":         query,
        "actions_taken": [f"{a.get('tool')}({a.get('params',{}).get('query','')})" for a in actions],
        "tool_outputs":  tool_outputs,
        "report":        final_report,
        "generated_at":  datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%MZ"),
    })

    update_search_status(code, "Completed")
    _agent_log(code, "Auto-AI OSINT agent complete — report written.")
    print(f"[ECHOMARK][auto-osint] _run_auto_agent: END code={code}")


@intel_bp.post("/cases/<code>/auto-osint")
def auto_osint(code):
    print(f"[ECHOMARK][routes/intel.py] POST /api/cases/{code}/auto-osint called")
    if not get_case_record(code):
        return jsonify({"error": f"Case {code} not found"}), 404
    threading.Thread(target=_run_auto_agent, args=(code,), daemon=True).start()
    return jsonify({"success": True, "message": "Auto-AI OSINT agent started."})


print("[ECHOMARK][routes/intel.py] Module ready — intel_bp fully registered")
