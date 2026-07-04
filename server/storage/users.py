"""
server/storage/users.py
=======================
Users stored in case_data/users.json as a JSON array.
"""

print("[ECHOMARK][storage/users.py] Module loaded — user storage initializing")

import os
import json
import threading

DATA_DIR  = os.path.join(os.path.dirname(__file__), "..", "..", "case_data")
USERS_FILE = os.path.join(DATA_DIR, "users.json")
_lock = threading.Lock()


def _read_users() -> list:
    os.makedirs(DATA_DIR, exist_ok=True)
    if not os.path.exists(USERS_FILE):
        return []
    with open(USERS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def _write_users(users: list) -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    tmp = USERS_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(users, f, indent=2, ensure_ascii=False)
    os.replace(tmp, USERS_FILE)


def get_user_by_identity(identity: str):
    """Find a user by email or operatorId."""
    with _lock:
        users = _read_users()
    for u in users:
        if u.get("email") == identity or u.get("operatorId") == identity:
            print(f"[ECHOMARK][storage/users.py] get_user_by_identity: '{identity}' → FOUND")
            return u
    print(f"[ECHOMARK][storage/users.py] get_user_by_identity: '{identity}' → NOT FOUND")
    return None


def save_user_record(user: dict) -> None:
    """Append or update a user record."""
    with _lock:
        users = _read_users()
        for i, u in enumerate(users):
            if u.get("email") == user.get("email") or u.get("operatorId") == user.get("operatorId"):
                users[i] = user
                _write_users(users)
                print(f"[ECHOMARK][storage/users.py] save_user_record: '{user.get('email')}' → updated")
                return
        users.append(user)
        _write_users(users)
    print(f"[ECHOMARK][storage/users.py] save_user_record: '{user.get('email')}' → created")


def seed_admin_user() -> None:
    """Ensure the default admin user exists on startup."""
    admin = get_user_by_identity("admin@echomark.gov")
    if not admin:
        save_user_record({
            "operatorId": "admin@echomark.gov",
            "fullName":   "System Admin",
            "username":   "ADMIN",
            "email":      "admin@echomark.gov",
            "password":   "admin"
        })
        print("[ECHOMARK][storage/users.py] seed_admin_user: default admin created")
    else:
        print("[ECHOMARK][storage/users.py] seed_admin_user: admin already exists, skipped")


print("[ECHOMARK][storage/users.py] Module ready — all functions registered")
