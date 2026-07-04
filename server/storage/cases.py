"""
server/storage/cases.py
=======================
Single-file JSON storage per case.

Each case lives at: case_data/<CODE>.json

Schema (flat, single file):
{
  "code":         str,        -- e.g. "DCase1234"
  "title":        str,
  "query":        str,        -- raw target value
  "type":         str,        -- "email" | "phone" | "username" | "instagram" | ...
  "created":      str,        -- ISO-like UTC string
  "status":       str,        -- "Active" | "Resolved"
  "priority":     str,
  "objective":    str,
  "searchStatus": str,        -- "Pending" | "Scanning" | "Completed"
  "logs":         [str],      -- chronological log lines
  "sections":     [           -- list of section objects
    {
      "section": str,         -- section name e.g. "basic", "instagram", "databreach"
      <tool-specific keys...>
    }
  ]
}
"""

print("[ECHOMARK][storage/cases.py] Module loaded — case storage initializing")

import os
import json
import threading

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "case_data")
_lock = threading.Lock()


def _case_path(code: str) -> str:
    os.makedirs(DATA_DIR, exist_ok=True)
    return os.path.join(DATA_DIR, f"{code}.json")


def _read_json(path: str):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _write_json(path: str, data) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp, path)


# ------------------------------------------------------------------ #
#  Public API
# ------------------------------------------------------------------ #

def get_case_record(code: str):
    """Return the full case dict or None if not found."""
    path = _case_path(code)
    if not os.path.exists(path):
        print(f"[ECHOMARK][storage/cases.py] get_case_record: {code} → NOT FOUND")
        return None
    with _lock:
        data = _read_json(path)
    print(f"[ECHOMARK][storage/cases.py] get_case_record: {code} → OK")
    return data


def save_case_record(code: str, record: dict) -> None:
    """Write (create or overwrite) a full case record."""
    path = _case_path(code)
    with _lock:
        _write_json(path, record)
    print(f"[ECHOMARK][storage/cases.py] save_case_record: {code} → saved")


def delete_case_record(code: str) -> None:
    """Delete a case file."""
    path = _case_path(code)
    with _lock:
        if os.path.exists(path):
            os.remove(path)
            print(f"[ECHOMARK][storage/cases.py] delete_case_record: {code} → deleted")
        else:
            print(f"[ECHOMARK][storage/cases.py] delete_case_record: {code} → not found, skipped")


def get_all_cases() -> list:
    """Return list of all case records sorted by creation date (newest first)."""
    os.makedirs(DATA_DIR, exist_ok=True)
    records = []
    with _lock:
        for fname in os.listdir(DATA_DIR):
            if fname.endswith(".json") and fname != "users.json":
                path = os.path.join(DATA_DIR, fname)
                try:
                    records.append(_read_json(path))
                except Exception as e:
                    print(f"[ECHOMARK][storage/cases.py] get_all_cases: failed to read {fname} — {e}")
    records.sort(key=lambda c: c.get("created", ""), reverse=True)
    #print(f"[ECHOMARK][storage/cases.py] get_all_cases: returned {len(records)} records")
    return records


def prepend_logs(code: str, new_lines: list) -> None:
    """Prepend log lines to the case's log list."""
    path = _case_path(code)
    with _lock:
        record = _read_json(path)
        existing = record.get("logs", [])
        record["logs"] = new_lines + existing
        _write_json(path, record)
    print(f"[ECHOMARK][storage/cases.py] prepend_logs: {code} — added {len(new_lines)} lines")


def upsert_section(code: str, section_name: str, section_data: dict) -> None:
    """
    Add or replace a section in record['sections'].
    section_data must include "section": section_name at minimum.
    """
    path = _case_path(code)
    with _lock:
        record = _read_json(path)
        sections = record.get("sections", [])
        # Replace if exists, otherwise append
        replaced = False
        for i, s in enumerate(sections):
            if s.get("section") == section_name:
                sections[i] = section_data
                replaced = True
                break
        if not replaced:
            sections.append(section_data)
        record["sections"] = sections
        _write_json(path, record)
    print(f"[ECHOMARK][storage/cases.py] upsert_section: {code}/{section_name} → {'replaced' if replaced else 'appended'}")


def get_section(code: str, section_name: str):
    """Return a single section dict or None."""
    record = get_case_record(code)
    if not record:
        return None
    for s in record.get("sections", []):
        if s.get("section") == section_name:
            return s
    return None


def update_search_status(code: str, status: str) -> None:
    """Update only the searchStatus field."""
    path = _case_path(code)
    with _lock:
        record = _read_json(path)
        record["searchStatus"] = status
        _write_json(path, record)
    print(f"[ECHOMARK][storage/cases.py] update_search_status: {code} → {status}")


def migrate_flat_files() -> None:
    """
    One-time migration: convert old multi-file layout (meta/profiles/suspects/etc)
    into the new single-file schema. Safe to call on every boot — skips if already migrated.
    """
    print("[ECHOMARK][storage/cases.py] migrate_flat_files: scanning for legacy folder-based cases...")
    os.makedirs(DATA_DIR, exist_ok=True)

    for entry in os.listdir(DATA_DIR):
        entry_path = os.path.join(DATA_DIR, entry)
        if not os.path.isdir(entry_path):
            continue

        code = entry
        new_file = _case_path(code)
        if os.path.exists(new_file):
            print(f"[ECHOMARK][storage/cases.py] migrate_flat_files: {code} already migrated, skipping")
            continue

        def _load(fname):
            p = os.path.join(entry_path, fname)
            if os.path.exists(p):
                try:
                    with open(p) as f:
                        return json.load(f)
                except Exception:
                    return None
            return None

        meta      = _load("meta.json")      or {}
        suspects  = _load("suspects.json")  or []
        profiles  = _load("profiles.json")  or []
        logs_raw  = _load("logs.json")      or []
        summary   = _load("summary.json")   or {}
        analytics = _load("analytics.json") or None
        sentiment = _load("sentiment.json") or None
        corr      = _load("correlations.json") or None

        # Build sections from old data
        sections = []
        if suspects:
            sections.append({"section": "basic", "suspects": suspects})
        if profiles:
            sections.append({"section": "connected_socials", "profiles": profiles})
        if analytics:
            sections.append({"section": "analytics", **analytics})
        if sentiment:
            sections.append({"section": "sentiment", **sentiment})
        if corr:
            sections.append({"section": "correlation", "correlations": corr})

        record = {
            "code":         meta.get("code", code),
            "title":        meta.get("title", code),
            "query":        meta.get("query", ""),
            "type":         meta.get("type", ""),
            "created":      meta.get("created", ""),
            "status":       meta.get("status", "Active"),
            "priority":     meta.get("priority", "Medium"),
            "objective":    meta.get("objective", ""),
            "searchStatus": meta.get("searchStatus", "Completed"),
            "logs":         logs_raw,
            "aiSummary":    summary.get("aiSummary", ""),
            "sections":     sections,
        }

        with _lock:
            _write_json(new_file, record)
        print(f"[ECHOMARK][storage/cases.py] migrate_flat_files: {code} → migrated to {new_file}")

    print("[ECHOMARK][storage/cases.py] migrate_flat_files: done")


print("[ECHOMARK][storage/cases.py] Module ready — all functions registered")
