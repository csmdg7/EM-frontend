"""
server/routes/auth.py
=====================
Authentication endpoints: register, login, /me
"""

print("[ECHOMARK][routes/auth.py] Module loaded — auth blueprint initializing")

import os
import jwt
from datetime import datetime, timedelta, timezone

from flask import Blueprint, request, jsonify
from server.storage.users import get_user_by_identity, save_user_record

auth_bp = Blueprint("auth", __name__)

JWT_SECRET       = os.environ.get("JWT_SECRET", "sk-jwt-secret-key-cidecode2026")
JWT_EXPIRY_HOURS = 24


def _make_token(operator_id: str, email: str) -> str:
    payload = {
        "operatorId": operator_id,
        "email":      email,
        "exp":        datetime.now(timezone.utc) + timedelta(hours=JWT_EXPIRY_HOURS),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")


def _decode_token(token: str):
    return jwt.decode(token, JWT_SECRET, algorithms=["HS256"])


# ------------------------------------------------------------------ #
#  POST /api/auth/register
# ------------------------------------------------------------------ #

@auth_bp.post("/register")
def register():
    print("[ECHOMARK][routes/auth.py] POST /api/auth/register called")
    data          = request.get_json(silent=True) or {}
    full_name     = data.get("fullName",       "").strip()
    username      = data.get("username",       "").strip()
    email         = data.get("email",          "").strip()
    encryption_key= data.get("encryptionKey",  "").strip()

    if not all([full_name, username, email, encryption_key]):
        print("[ECHOMARK][routes/auth.py] register: missing fields — 400")
        return jsonify({"error": "Missing required fields"}), 400

    if get_user_by_identity(email):
        print(f"[ECHOMARK][routes/auth.py] register: '{email}' already exists — 400")
        return jsonify({"error": "Operative identity already registered"}), 400

    new_user = {
        "operatorId": email,
        "fullName":   full_name,
        "username":   username.upper(),
        "email":      email,
        "password":   encryption_key,
    }

    try:
        save_user_record(new_user)
        token = _make_token(new_user["operatorId"], new_user["email"])
        print(f"[ECHOMARK][routes/auth.py] register: '{email}' registered — 201")
        return jsonify({
            "token": token,
            "user": {
                "operatorId": new_user["operatorId"],
                "fullName":   new_user["fullName"],
                "username":   new_user["username"],
                "email":      new_user["email"],
            }
        }), 201
    except Exception as e:
        print(f"[ECHOMARK][routes/auth.py] register: ERROR — {e}")
        return jsonify({"error": "Failed to register", "details": str(e)}), 500


# ------------------------------------------------------------------ #
#  POST /api/auth/login
# ------------------------------------------------------------------ #

@auth_bp.post("/login")
def login():
    print("[ECHOMARK][routes/auth.py] POST /api/auth/login called")
    data         = request.get_json(silent=True) or {}
    operator_id  = data.get("operatorId",  "").strip()
    access_code  = data.get("accessCode",  "").strip()

    if not operator_id or not access_code:
        return jsonify({"error": "Operator ID and Access Code required"}), 400

    user = get_user_by_identity(operator_id)
    if not user or user.get("password") != access_code:
        print(f"[ECHOMARK][routes/auth.py] login: invalid credentials for '{operator_id}' — 401")
        return jsonify({"error": "Invalid Operator ID or Access Code"}), 401

    try:
        token = _make_token(user["operatorId"], user["email"])
        print(f"[ECHOMARK][routes/auth.py] login: '{operator_id}' authenticated — 200")
        return jsonify({
            "token": token,
            "user": {
                "operatorId": user["operatorId"],
                "fullName":   user["fullName"],
                "username":   user["username"],
                "email":      user["email"],
            }
        })
    except Exception as e:
        print(f"[ECHOMARK][routes/auth.py] login: ERROR — {e}")
        return jsonify({"error": "Login failed", "details": str(e)}), 500


# ------------------------------------------------------------------ #
#  GET /api/auth/me
# ------------------------------------------------------------------ #

@auth_bp.get("/me")
def me():
    print("[ECHOMARK][routes/auth.py] GET /api/auth/me called")
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return jsonify({"error": "Unauthorized"}), 401

    token = auth_header[7:]
    try:
        decoded = _decode_token(token)
        user    = get_user_by_identity(decoded["operatorId"])
        if not user:
            return jsonify({"error": "User not found"}), 401
        return jsonify({
            "operatorId": user["operatorId"],
            "fullName":   user["fullName"],
            "username":   user["username"],
            "email":      user["email"],
        })
    except jwt.ExpiredSignatureError:
        return jsonify({"error": "Token expired"}), 401
    except Exception as e:
        print(f"[ECHOMARK][routes/auth.py] me: ERROR — {e}")
        return jsonify({"error": "Invalid token"}), 401


print("[ECHOMARK][routes/auth.py] Module ready — auth_bp fully registered")
