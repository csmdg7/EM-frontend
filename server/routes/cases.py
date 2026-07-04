"""
server/routes/cases.py
=======================
Case management REST endpoints.

All case data now lives in a single JSON file per case (case_data/<CODE>.json).
"""

print("[ECHOMARK][routes/cases.py] Module loaded — cases blueprint initializing")

import threading
from datetime import datetime, timezone

from flask import Blueprint, request, jsonify

from server.storage.cases import (
    get_case_record,
    save_case_record,
    delete_case_record,
    get_all_cases,
    prepend_logs,
    update_search_status,
    get_section,
)
from server.services.osint.pipeline import run_osint_scanner

cases_bp = Blueprint("cases", __name__)


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%MZ")


# ------------------------------------------------------------------ #
#  POST /api/cases — Create a new case
# ------------------------------------------------------------------ #

@cases_bp.post("/")
def create_case():
    print("[ECHOMARK][routes/cases.py] POST /api/cases — create_case called")
    payload = request.get_json(silent=True)

    if not payload or not payload.get("code"):
        print("[ECHOMARK][routes/cases.py] create_case: missing code — 400")
        return jsonify({"error": "Invalid case data: 'code' is required"}), 400

    code = payload["code"].strip()

    record = {
        "code":         code,
        "title":        payload.get("title", code),
        "query":        payload.get("query", ""),
        "type":         payload.get("type", ""),
        "created":      payload.get("created", _now()),
        "status":       payload.get("status", "Active"),
        "priority":     payload.get("priority", "Medium"),
        "objective":    payload.get("objective", f"OSINT scan for target '{payload.get('query', '')}'"),
        "searchStatus": "Pending",
        "logs":         [f"{_now()} — Case {code} created."],
        "sections":     [],
    }

    save_case_record(code, record)
    print(f"[ECHOMARK][routes/cases.py] create_case: saved {code} — 201")
    return jsonify({"success": True, "case": record}), 201


# ------------------------------------------------------------------ #
#  GET /api/cases — List all cases
# ------------------------------------------------------------------ #

@cases_bp.get("/")
def list_cases():
    #print("[ECHOMARK][routes/cases.py] GET /api/cases — list_cases called")
    try:
        cases = get_all_cases()
        #print(f"[ECHOMARK][routes/cases.py] list_cases: returning {len(cases)} records")
        return jsonify(cases)
    except Exception as e:
        print(f"[ECHOMARK][routes/cases.py] list_cases: ERROR — {e}")
        return jsonify({"error": "Failed to list cases", "details": str(e)}), 500


# ------------------------------------------------------------------ #
#  GET /api/cases/<code> — Get single case
# ------------------------------------------------------------------ #

@cases_bp.get("/<code>")
def get_case(code):
    print(f"[ECHOMARK][routes/cases.py] GET /api/cases/{code} — get_case called")
    data = get_case_record(code)
    if data:
        return jsonify(data)
    print(f"[ECHOMARK][routes/cases.py] get_case: {code} not found — 404")
    return jsonify({"error": f"Case {code} not found"}), 404


# ------------------------------------------------------------------ #
#  DELETE /api/cases/<code> — Delete a case
# ------------------------------------------------------------------ #

@cases_bp.delete("/<code>")
def delete_case(code):
    print(f"[ECHOMARK][routes/cases.py] DELETE /api/cases/{code} — delete_case called")
    try:
        delete_case_record(code)
        return jsonify({"success": True, "message": f"Case {code} deleted."})
    except Exception as e:
        print(f"[ECHOMARK][routes/cases.py] delete_case: ERROR — {e}")
        return jsonify({"error": "Failed to delete case", "details": str(e)}), 500


# ------------------------------------------------------------------ #
#  POST /api/cases/<code>/update-log — Append a log line
# ------------------------------------------------------------------ #

@cases_bp.post("/<code>/update-log")
def update_log(code):
    print(f"[ECHOMARK][routes/cases.py] POST /api/cases/{code}/update-log called")
    data = request.get_json(silent=True) or {}
    msg  = data.get("logMessage", "").strip()

    if not msg:
        return jsonify({"error": "logMessage is required"}), 400

    if not get_case_record(code):
        return jsonify({"error": f"Case {code} not found"}), 404

    prepend_logs(code, [f"{_now()} — {msg}"])
    return jsonify({"success": True, "case": get_case_record(code)})


# ------------------------------------------------------------------ #
#  POST /api/cases/<code>/trigger-osint — Launch background scan
# ------------------------------------------------------------------ #

@cases_bp.post("/<code>/trigger-osint")
def trigger_osint(code):
    print(f"[ECHOMARK][routes/cases.py] POST /api/cases/{code}/trigger-osint called")
    case_data = get_case_record(code)
    if not case_data:
        print(f"[ECHOMARK][routes/cases.py] trigger_osint: {code} not found — 404")
        return jsonify({"error": f"Case {code} not found"}), 404

    query    = case_data.get("query", "")
    type_str = case_data.get("type", "")

    print(f"[ECHOMARK][routes/cases.py] trigger_osint: spawning thread for {code} query='{query}' type='{type_str}'")

    threading.Thread(
        target=run_osint_scanner,
        args=(code, query, type_str),
        daemon=True
    ).start()

    return jsonify({"success": True, "message": "OSINT pipeline started."})


print("[ECHOMARK][routes/cases.py] Module ready — cases_bp fully registered")


# ------------------------------------------------------------------ #
#  POST /api/cases/<code>/retry-module  — Retry a specific scanner
# ------------------------------------------------------------------ #

RETRYABLE_MODULES = {
    # email sub-modules
    "email_breach":   ("server.services.osint.scanners.email",    "_run_email_breach"),
    "email_google":   ("server.services.osint.scanners.email",    "_run_google_only"),
    # instagram sub-modules
    "instagram":      ("server.services.osint.scanners.instagram", "scan_instagram"),
    "interactors":    ("server.services.osint.scanners.interactors","scan_interactors"),
    "reverse_image":  ("server.services.osint.scanners.reverse_image","reverse_image_search"),
    "nlp":            ("server.services.osint.scanners.nlp_analysis","analyse_text"),
    # generic
    "sherlock":       ("server.services.osint.scanners.username",  "scan_username"),
    "ai_summary":     ("server.services.osint.scanners.ai_summary","generate_ai_summary"),
    "dorking":        ("server.services.osint.scanners.dorking",   "scan_dorking"),
}


def _run_retry(code: str, module_key: str) -> None:
    """Background thread: retry a specific scanner module."""
    import importlib
    from server.storage.cases import get_case_record, prepend_logs, update_search_status
    from datetime import datetime, timezone

    def _ts():
        return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%MZ")

    record = get_case_record(code)
    if not record:
        return

    query    = record.get("query", "")
    type_str = record.get("type", "")

    update_search_status(code, f"Retrying {module_key}...")
    prepend_logs(code, [f"{_ts()} — [RETRY] Retrying module: {module_key}"])
    print(f"[ECHOMARK][routes/cases.py] _run_retry: {code} module={module_key} query={query}")

    if module_key not in RETRYABLE_MODULES:
        prepend_logs(code, [f"{_ts()} — [RETRY] Unknown module: {module_key}"])
        update_search_status(code, "Completed")
        return

    mod_path, fn_name = RETRYABLE_MODULES[module_key]

    try:
        mod = importlib.import_module(mod_path)
        fn  = getattr(mod, fn_name)

        # Call with appropriate args based on module type
        if module_key == "email_breach":
            # run only the breach checker part
            from server.services.osint.scanners.email import _fetch_email_intel, _write_breach_section
            _write_breach_section(code, query)

        elif module_key == "email_google":
            from server.services.osint.scanners.email import _write_google_section
            _write_google_section(code, query)

        elif module_key in ("instagram", "sherlock"):
            fn(code, query)

        elif module_key == "interactors":
            from server.storage.cases import get_section
            mi_sec = get_section(code, "media_intelligence") or {}
            ig_sec = get_section(code, "instagram") or {}
            fn(code, query, mi_sec.get("media", []), ig_sec.get("captions", []))

        elif module_key == "reverse_image":
            from server.storage.cases import get_section
            ig_sec = get_section(code, "instagram") or {}
            pic    = ig_sec.get("profile_pic_url", "")
            if pic:
                fn(code, pic)

        elif module_key == "nlp":
            from server.storage.cases import get_section
            ig_sec = get_section(code, "instagram") or {}
            mi_sec = get_section(code, "media_intelligence") or {}
            fn(code, query, ig_sec.get("bio",""), ig_sec.get("captions",[]), mi_sec.get("media",[]))

        elif module_key == "ai_summary":
            fn(code, query, type_str)

        elif module_key == "dorking":
            fn(code, query, type_str)

        else:
            fn(code, query)

        prepend_logs(code, [f"{_ts()} — [RETRY] {module_key} completed successfully"])
    except Exception as e:
        prepend_logs(code, [f"{_ts()} — [RETRY] {module_key} failed: {e}"])
        print(f"[ECHOMARK][routes/cases.py] _run_retry: {module_key} error — {e}")
    finally:
        update_search_status(code, "Completed")


@cases_bp.post("/<code>/retry-module")
def retry_module(code):
    print(f"[ECHOMARK][routes/cases.py] POST /api/cases/{code}/retry-module called")
    data       = request.get_json(silent=True) or {}
    module_key = data.get("module", "").strip()

    if not module_key:
        return jsonify({"error": "module field required"}), 400

    if not get_case_record(code):
        return jsonify({"error": f"Case {code} not found"}), 404

    threading.Thread(target=_run_retry, args=(code, module_key), daemon=True).start()
    return jsonify({"success": True, "message": f"Retrying {module_key}..."})
