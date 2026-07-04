import json
import os
from datetime import datetime
from .config import QUOTA_FILE, QUOTA_LIMITS, VAULT_DIR

os.makedirs(VAULT_DIR, exist_ok=True)


def _load():
    if not os.path.exists(QUOTA_FILE):
        return {"month": datetime.utcnow().strftime("%Y-%m"), "usage": {}}
    with open(QUOTA_FILE, "r") as f:
        data = json.load(f)
    current_month = datetime.utcnow().strftime("%Y-%m")
    if data.get("month") != current_month:
        return {"month": current_month, "usage": {}}
    return data


def _save(data):
    with open(QUOTA_FILE, "w") as f:
        json.dump(data, f, indent=2)


def can_call(key_name: str) -> bool:
    data = _load()
    used = data["usage"].get(key_name, 0)
    return used < QUOTA_LIMITS.get(key_name, 500)


def record_call(key_name: str):
    data = _load()
    data["usage"][key_name] = data["usage"].get(key_name, 0) + 1
    _save(data)


def remaining(key_name: str) -> int:
    data = _load()
    used = data["usage"].get(key_name, 0)
    return max(QUOTA_LIMITS.get(key_name, 500) - used, 0)