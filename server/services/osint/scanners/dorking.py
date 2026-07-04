"""
server/services/osint/scanners/dorking.py
==========================================
Google AI (Gemini 2.0 Flash) powered dorking scanner.

Strategy:
  - Sends target context to Gemini with a strict prompt to generate
    precision Google dork queries
  - Gemini returns ONLY JSON (forced via prompt engineering)
  - Executes each dork via DuckDuckGo HTML scrape (no API key)
  - Returns structured results per dork query

Why Gemini for dorking vs. a static list:
  - Target-aware: uses username, email, bio, platforms, real name
    to generate highly specific dorks rather than generic templates
  - Adaptive: if target is a professional, it dorks LinkedIn/CV;
    if a gamer, it dorks Steam/Discord; etc.
  - Output is always structured JSON — easy to render

Exports:
    scan_dorking(code, query, type_str) -> None
"""

print("[ECHOMARK][scanners/dorking.py] Module loaded")

import os
import re
import json
import requests
from urllib.parse import quote
from server.storage.cases import upsert_section, get_case_record, get_section
from server.services.osint.scanners.shared import _log

GEMINI_KEY  = os.environ.get("GEMINI_API_KEY", "")
GEMINI_URL  = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"

HEADERS_UA = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}


# ── Gemini dork generation ────────────────────────────────────────

def _build_context(code: str, query: str, type_str: str) -> str:
    """Pull existing case sections to give Gemini maximum context."""
    parts = [f"Target: {query}", f"Type: {type_str}"]

    ig = get_section(code, "instagram")
    if ig and not ig.get("error"):
        parts.append(f"Instagram: username={ig.get('username')} full_name={ig.get('full_name')} bio={ig.get('bio','')[:100]}")
        details = ig.get("account_details") or {}
        if details.get("country"):
            parts.append(f"Country: {details['country']}")

    google = get_section(code, "google_account")
    if google and google.get("person_id"):
        parts.append(f"Google: verified_email={google.get('verified_email')} full_name={google.get('full_name','')}")

    nlp = get_section(code, "nlp_content")
    if nlp:
        top_hashtags = [h["tag"] for h in (nlp.get("top_hashtags") or [])[:5]]
        if top_hashtags:
            parts.append(f"Top hashtags: {' '.join(top_hashtags)}")
        emails = nlp.get("contact_emails") or []
        if emails:
            parts.append(f"Emails found in bio/captions: {emails}")
        urls = nlp.get("external_urls") or []
        if urls:
            parts.append(f"External URLs: {urls[:3]}")
        cls = (nlp.get("content_classification") or {}).get("dominant", "")
        if cls:
            parts.append(f"Content focus: {cls}")

    related = get_section(code, "related_platforms")
    if related:
        plats = [p.get("platform","") for p in (related.get("platforms") or [])[:6]]
        if plats:
            parts.append(f"Found on platforms: {', '.join(plats)}")

    return "\n".join(parts)


def _gemini_generate_dorks(context: str) -> list:
    """
    Ask Gemini to generate targeted Google dork queries.
    Returns list of dork dicts: [{query, purpose, category}]
    Forces JSON-only output via prompt engineering.
    """
    print("[ECHOMARK][scanners/dorking.py] _gemini_generate_dorks: calling Gemini")

    if not GEMINI_KEY:
        print("[ECHOMARK][scanners/dorking.py] _gemini_generate_dorks: GEMINI_API_KEY not set")
        return []

    prompt = f"""You are a professional OSINT analyst and Google dorking expert.

Target intelligence:
{context}

Generate 12 highly targeted Google dork queries for this specific target.
Use all available context (name, username, email, bio, platforms, hashtags, country).

Rules:
- Use advanced Google operators: site:, inurl:, intitle:, intext:, filetype:, -site:, ""
- Make queries SPECIFIC to this target, not generic templates
- Cover: social accounts, leaked credentials, documents, professional info, location clues
- Each query should find something different

YOU MUST RESPOND WITH ONLY VALID JSON. NO EXPLANATION. NO MARKDOWN. NO BACKTICKS.
Return exactly this structure:
[
  {{"query": "exact google search string", "purpose": "what this finds", "category": "social|credentials|documents|professional|location|other"}},
  ...
]"""

    try:
        resp = requests.post(
            f"{GEMINI_URL}?key={GEMINI_KEY}",
            json={"contents": [{"parts": [{"text": prompt}]}],
                  "generationConfig": {"temperature": 0.3, "maxOutputTokens": 1500}},
            timeout=25
        )
        resp.raise_for_status()
        raw_text = resp.json()["candidates"][0]["content"]["parts"][0]["text"].strip()

        # Strip any accidental markdown fences
        clean = re.sub(r"```json|```", "", raw_text, flags=re.I).strip()
        dorks = json.loads(clean)

        if not isinstance(dorks, list):
            print("[ECHOMARK][scanners/dorking.py] _gemini_generate_dorks: non-list response")
            return []

        print(f"[ECHOMARK][scanners/dorking.py] _gemini_generate_dorks: {len(dorks)} dorks generated")
        return dorks

    except json.JSONDecodeError as e:
        print(f"[ECHOMARK][scanners/dorking.py] _gemini_generate_dorks: JSON parse error — {e}")
        return []
    except Exception as e:
        print(f"[ECHOMARK][scanners/dorking.py] _gemini_generate_dorks: error — {e}")
        return []


# ── DuckDuckGo execution ──────────────────────────────────────────

def _execute_dork(dork_query: str, max_results: int = 5) -> list:
    """
    Execute a dork query via DuckDuckGo HTML (no API key).
    Returns list of {title, url, snippet} dicts.
    """
    try:
        resp = requests.get(
            "https://html.duckduckgo.com/html/",
            params={"q": dork_query, "kl": "us-en"},
            headers=HEADERS_UA,
            timeout=10
        )
        html = resp.text
        results = []

        # Extract result blocks
        blocks = re.findall(
            r'<a[^>]+class="[^"]*result__a[^"]*"[^>]+href="([^"]+)"[^>]*>([^<]+)</a>.*?'
            r'<a[^>]+class="[^"]*result__snippet[^"]*"[^>]*>(.*?)</a>',
            html, re.S
        )
        for url, title, snippet in blocks[:max_results]:
            # DDG wraps URLs — extract real URL
            real_url = re.search(r'uddg=([^&]+)', url)
            real_url = requests.utils.unquote(real_url.group(1)) if real_url else url
            results.append({
                "title":   re.sub(r'<[^>]+>', '', title).strip(),
                "url":     real_url.strip(),
                "snippet": re.sub(r'<[^>]+>', '', snippet).strip()[:200],
            })

        return results

    except Exception as e:
        print(f"[ECHOMARK][scanners/dorking.py] _execute_dork: error for '{dork_query[:40]}' — {e}")
        return []


# ── Fallback static dorks (when Gemini unavailable) ───────────────

def _static_dorks(query: str, type_str: str) -> list:
    """Generate basic dorks without Gemini."""
    t = type_str.lower()
    base = [
        {"query": f'"{query}"',                             "purpose": "Exact match anywhere", "category": "other"},
        {"query": f'"{query}" site:linkedin.com',           "purpose": "LinkedIn profile",      "category": "professional"},
        {"query": f'"{query}" site:github.com',             "purpose": "GitHub profile",        "category": "social"},
        {"query": f'"{query}" site:pastebin.com',           "purpose": "Leaked pastes",         "category": "credentials"},
        {"query": f'"{query}" filetype:pdf',                "purpose": "PDF documents",         "category": "documents"},
        {"query": f'"{query}" -site:instagram.com -site:facebook.com -site:twitter.com', "purpose": "Other web mentions", "category": "other"},
    ]
    if "email" in t:
        base += [
            {"query": f'"{query}" site:haveibeenpwned.com', "purpose": "Breach check",         "category": "credentials"},
            {"query": f'"{query}" intext:password OR intext:passwd', "purpose": "Leaked credentials", "category": "credentials"},
        ]
    if "instagram" in t or "username" in t:
        base += [
            {"query": f'"{query}" site:instagram.com',      "purpose": "Instagram presence",   "category": "social"},
            {"query": f'"{query}" site:reddit.com',         "purpose": "Reddit mentions",      "category": "social"},
        ]
    return base


# ── Main entry ────────────────────────────────────────────────────

def scan_dorking(code: str, query: str, type_str: str) -> None:
    """
    Generate AI-powered dork queries and execute them.
    Writes dorking section with:
      - ai_generated: bool
      - dork_queries: [{query, purpose, category, results:[]}]
      - summary: Gemini analysis of findings
    """
    print(f"[ECHOMARK][scanners/dorking.py] scan_dorking: START code={code} query='{query}'")
    _log(code, "[DORKING] AI dorking scan started")

    context = _build_context(code, query, type_str)
    dorks   = _gemini_generate_dorks(context)
    ai_generated = bool(dorks)

    if not dorks:
        _log(code, "[DORKING] Gemini unavailable — using static dork templates")
        dorks = _static_dorks(query, type_str)

    # Execute each dork
    executed = []
    for d in dorks[:12]:
        dork_q = d.get("query", "")
        if not dork_q:
            continue
        results = _execute_dork(dork_q, max_results=5)
        executed.append({
            "query":    dork_q,
            "purpose":  d.get("purpose", ""),
            "category": d.get("category", "other"),
            "results":  results,
            "hit_count": len(results),
        })
        print(f"[ECHOMARK][scanners/dorking.py] scan_dorking: '{dork_q[:50]}' → {len(results)} results")

    # Total hits
    total_hits = sum(e["hit_count"] for e in executed)
    categories_with_hits = list({e["category"] for e in executed if e["hit_count"] > 0})

    # Gemini summary of findings
    summary = ""
    if GEMINI_KEY and total_hits > 0:
        findings_text = "\n".join(
            f"[{e['category']}] {e['query']}: {e['hit_count']} result(s)" +
            (f" — top: {e['results'][0]['title'][:60]}" if e['results'] else "")
            for e in executed
        )
        sum_prompt = f"""OSINT dorking results for target: {query}

{findings_text}

Provide a 3-sentence intelligence summary of what these dork results reveal about the target.
Respond in plain text only (no JSON, no markdown).
Be factual and analytical."""
        try:
            resp = requests.post(
                f"{GEMINI_URL}?key={GEMINI_KEY}",
                json={"contents": [{"parts": [{"text": sum_prompt}]}],
                      "generationConfig": {"maxOutputTokens": 300}},
                timeout=20
            )
            resp.raise_for_status()
            summary = resp.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
        except Exception as e:
            print(f"[ECHOMARK][scanners/dorking.py] scan_dorking: summary error — {e}")

    upsert_section(code, "dorking", {
        "section":           "dorking",
        "query":             query,
        "ai_generated":      ai_generated,
        "total_dorks":       len(executed),
        "total_hits":        total_hits,
        "categories_hit":    categories_with_hits,
        "dork_queries":      executed,
        "ai_summary":        summary,
        "note": f"{'AI-generated' if ai_generated else 'Static'} dorks. {total_hits} total results across {len(executed)} queries.",
    })

    _log(code, f"[DORKING] {len(executed)} queries, {total_hits} total hits. AI: {ai_generated}")
    print(f"[ECHOMARK][scanners/dorking.py] scan_dorking: END code={code}")


print("[ECHOMARK][scanners/dorking.py] Module ready — scan_dorking exported")