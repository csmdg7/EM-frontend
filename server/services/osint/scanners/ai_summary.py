"""
server/services/osint/scanners/ai_summary.py
=============================================
Gemini-powered AI summary generator.

Reads the finished sections from the case JSON and produces a
concise OSINT intelligence summary written to the ai_summary section.

Exports:
    generate_ai_summary(code, query, type_str) -> None
    call_gemini(prompt)                        -> str
"""

print("[ECHOMARK][scanners/ai_summary.py] Module loaded — AI Summary generator initializing")

import json
import requests
from server.storage.cases import get_case_record, upsert_section
from server.services.osint.scanners.shared import GEMINI_KEY, _now, _log


def call_gemini(prompt: str) -> str:
    """
    Send a prompt to Gemini 1.5 Flash and return the response text.
    Returns an error string if GEMINI_KEY not set or request fails.
    """
    print(f"[ECHOMARK][scanners/ai_summary.py] call_gemini: sending prompt ({len(prompt)} chars)")

    if not GEMINI_KEY:
        print("[ECHOMARK][scanners/ai_summary.py] call_gemini: GEMINI_API_KEY not set")
        return "AI summary unavailable: GEMINI_API_KEY not configured in .env"

    try:
        resp = requests.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_KEY}",
            json={"contents": [{"parts": [{"text": prompt}]}]},
            timeout=25
        )
        resp.raise_for_status()
        text = resp.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
        print(f"[ECHOMARK][scanners/ai_summary.py] call_gemini: received {len(text)} chars")
        return text
    except Exception as e:
        print(f"[ECHOMARK][scanners/ai_summary.py] call_gemini: error — {e}")
        return f"AI summary generation failed: {e}"


def generate_ai_summary(code: str, query: str, type_str: str) -> None:
    """
    Pull completed section data from the case JSON,
    build a context-rich prompt, call Gemini, and write the ai_summary section.
    """
    print(f"[ECHOMARK][scanners/ai_summary.py] generate_ai_summary: START code={code}")
    _log(code, "[AI] Generating intelligence summary via Gemini...")

    # Pull current case state for context
    record   = get_case_record(code)
    sections = record.get("sections", []) if record else []

    # Build a concise context string from available sections
    context_parts = []
    for s in sections:
        name = s.get("section", "")
        if name == "basic":
            context_parts.append(f"Basic: query={s.get('query')} type={s.get('type')} notes={s.get('notes','')}")
        elif name == "connected_socials":
            profiles = s.get("profiles", [])
            if profiles:
                platforms = [p.get("platform","?") for p in profiles[:10]]
                context_parts.append(f"Connected socials: {', '.join(platforms)}")
        elif name == "databreach":
            bc = s.get("breach_count", len(s.get("breaches", [])))
            if bc:
                context_parts.append(f"Databreach: {bc} breach(es) found")
        elif name in ("instagram", "facebook", "twitter"):
            followers = s.get("followers", "")
            bio = s.get("biography", s.get("bio", s.get("about", "")))
            context_parts.append(f"{name.capitalize()}: followers={followers} bio='{bio[:100]}'")
        elif name == "related_platforms":
            platforms = s.get("platforms", [])
            if platforms:
                names = [p.get("platform","?") for p in platforms[:8]]
                context_parts.append(f"Related platforms: {', '.join(names)}")
        elif name == "dns":
            context_parts.append(f"DNS: A={s.get('a_records',[])} geo={s.get('geolocation',{}).get('city','?')}")

    context = "\n".join(context_parts) if context_parts else "No section data available yet."

    prompt = (
        f"You are a senior OSINT analyst writing a classified intelligence summary.\n"
        f"Target: '{query}' (type: {type_str})\n\n"
        f"Available intelligence:\n{context}\n\n"
        f"Write a concise 4-6 sentence professional OSINT summary. "
        f"Be factual, analytical, and note any gaps in intelligence. "
        f"Do not fabricate or assume data not listed above."
    )

    summary_text = call_gemini(prompt)

    upsert_section(code, "ai_summary", {
        "section":      "ai_summary",
        "summary":      summary_text,
        "generated_at": _now(),
        "context_used": len(context_parts)
    })

    _log(code, f"[AI] Summary written — {len(summary_text)} chars, context_sections={len(context_parts)}")
    print(f"[ECHOMARK][scanners/ai_summary.py] generate_ai_summary: END code={code}")


print("[ECHOMARK][scanners/ai_summary.py] Module ready — call_gemini, generate_ai_summary exported")
