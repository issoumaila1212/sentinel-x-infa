"""Authentication, roles and audit log for the Sentinel X API.

- Passwords are stored hashed (scrypt via Werkzeug), never in clear text.
- A login returns a signed JWT stored in an HttpOnly, Secure, SameSite=Strict cookie,
  so JavaScript can never read it (protects against token theft through XSS).
- The role is read from the database on every request, so a role change or an account
  deactivation takes effect immediately, even for tokens that were already issued.
- Every security-relevant event is written to the audit_log table.
"""
import os
import re
import sqlite3
from datetime import datetime, timedelta, timezone
from functools import wraps

import jwt
from flask import Blueprint, g, has_request_context, jsonify, request
from werkzeug.security import check_password_hash, generate_password_hash

from database import connect

bp = Blueprint("auth", __name__)

ROLES = ("user", "admin", "superadmin")
RANK = {"user": 1, "admin": 2, "superadmin": 3}

COOKIE_NAME = "sentinel_token"
TOKEN_HOURS = 2
MAX_FAILS = 5          # failed logins from one IP address ...
FAIL_WINDOW_S = 300    # ... within this many seconds => temporary block
USERNAME_RE = re.compile(r"^[A-Za-z0-9_.-]{3,32}$")
MIN_PASSWORD = 12
MAX_PASSWORD = 128

# Used to spend the same time on unknown usernames (prevents user enumeration by timing).
_DUMMY_HASH = generate_password_hash("not-a-real-password")


# ---------------------------------------------------------------- helpers
def check_config():
    if len(os.getenv("JWT_SECRET", "")) < 32:
        raise SystemExit(
            "JWT_SECRET manquant ou trop court (32 caractères minimum) dans .env.\n"
            'Génère-en un avec : python -c "import secrets; print(secrets.token_hex(32))"'
        )


def _secret():
    return os.environ["JWT_SECRET"]


def _json():
    data = request.get_json(silent=True)  # None unless Content-Type is application/json
    return data if isinstance(data, dict) else {}


def _public(row):
    return {
        "id": row["id"],
        "username": row["username"],
        "role": row["role"],
        "active": bool(row["active"]),
        "created_at": row["created_at"],
        "last_login": row["last_login"],
    }


def password_error(password, username=""):
    if len(password) < MIN_PASSWORD:
        return f"Password must be at least {MIN_PASSWORD} characters long."
    if len(password) > MAX_PASSWORD:
        return f"Password must be at most {MAX_PASSWORD} characters long."
    if username and password.lower() == username.lower():
        return "Password must not be the same as the username."
    return None


def audit(action, username=None, success=True, detail=None):
    ip = request.remote_addr if has_request_context() else None
    conn = connect()
    with conn:
        conn.execute(
            "INSERT INTO audit_log (username, ip, action, success, detail) VALUES (?, ?, ?, ?, ?)",
            (username, ip, action, int(success), detail),
        )
    conn.close()


def _recent_failures(ip):
    conn = connect()
    n = conn.execute(
        "SELECT COUNT(*) FROM audit_log WHERE action = 'login' AND success = 0 AND ip = ? "
        "AND ts > strftime('%Y-%m-%dT%H:%M:%fZ', 'now', ?)",
        (ip, f"-{FAIL_WINDOW_S} seconds"),
    ).fetchone()[0]
    conn.close()
    return n


def _raise_alert(message):
    conn = connect()
    with conn:
        conn.execute(
            "INSERT INTO alerts (source, level, message) VALUES ('auth', 'warning', ?)",
            (message,),
        )
    conn.close()


def _make_token(user_id):
    now = datetime.now(timezone.utc)
    payload = {"sub": str(user_id), "iat": now, "exp": now + timedelta(hours=TOKEN_HOURS)}
    return jwt.encode(payload, _secret(), algorithm="HS256")


def current_user():
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return None
    try:
        payload = jwt.decode(
            token, _secret(), algorithms=["HS256"], options={"require": ["exp", "sub"]}
        )
        user_id = int(payload["sub"])
    except (jwt.PyJWTError, ValueError):
        return None
    conn = connect()
    row = conn.execute(
        "SELECT id, username, role, active FROM users WHERE id = ?", (user_id,)
    ).fetchone()
    conn.close()
    if row is None or not row["active"]:
        return None
    return dict(row)


def require_role(min_role):
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            user = current_user()
            if user is None:
                return jsonify(error="Authentication required"), 401
            if RANK[user["role"]] < RANK[min_role]:
                audit("forbidden", user["username"], False, f"{request.method} {request.path}")
                return jsonify(error="Insufficient permissions"), 403
            g.user = user
            return fn(*args, **kwargs)
        return wrapper
    return decorator


# ---------------------------------------------------------------- login / logout
@bp.post("/api/auth/login")
def login():
    data = _json()
    username = str(data.get("username", "")).strip()
    password = str(data.get("password", ""))
    ip = request.remote_addr

    if _recent_failures(ip) >= MAX_FAILS:
        audit("login_blocked", username or None, False, "too many failed attempts")
        return jsonify(error="Too many failed attempts. Try again in a few minutes."), 429

    row = None
    if USERNAME_RE.match(username) and len(password) <= MAX_PASSWORD:
        conn = connect()
        row = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        conn.close()

    # Always run one hash check, even for unknown users, so timing does not reveal them.
    hash_ok = check_password_hash(row["password_hash"] if row else _DUMMY_HASH, password)
    if row is None or not row["active"] or not hash_ok:
        audit("login", username[:32] or None, False)
        if _recent_failures(ip) == MAX_FAILS:
            _raise_alert(f"{MAX_FAILS} failed logins from {ip} in {FAIL_WINDOW_S // 60} minutes")
        return jsonify(error="Invalid username or password."), 401

    conn = connect()
    with conn:
        conn.execute(
            "UPDATE users SET last_login = strftime('%Y-%m-%dT%H:%M:%fZ', 'now') WHERE id = ?",
            (row["id"],),
        )
    conn.close()
    audit("login", row["username"], True)

    resp = jsonify(id=row["id"], username=row["username"], role=row["role"])
    resp.set_cookie(
        COOKIE_NAME, _make_token(row["id"]),
        max_age=TOKEN_HOURS * 3600, httponly=True, secure=True, samesite="Strict", path="/",
    )
    return resp


@bp.post("/api/auth/logout")
def logout():
    user = current_user()
    if user:
        audit("logout", user["username"], True)
    resp = jsonify(status="ok")
    resp.delete_cookie(COOKIE_NAME, path="/", secure=True, httponly=True, samesite="Strict")
    return resp


@bp.get("/api/auth/me")
@require_role("user")
def me():
    return jsonify(id=g.user["id"], username=g.user["username"], role=g.user["role"])


@bp.post("/api/auth/password")
@require_role("user")
def change_password():
    data = _json()
    current = str(data.get("current", ""))
    new = str(data.get("new", ""))

    conn = connect()
    row = conn.execute("SELECT * FROM users WHERE id = ?", (g.user["id"],)).fetchone()
    if len(current) > MAX_PASSWORD or not check_password_hash(row["password_hash"], current):
        conn.close()
        audit("password_change", g.user["username"], False, "wrong current password")
        return jsonify(error="Current password is incorrect."), 400
    problem = password_error(new, g.user["username"])
    if problem:
        conn.close()
        return jsonify(error=problem), 400
    with conn:
        conn.execute(
            "UPDATE users SET password_hash = ? WHERE id = ?",
            (generate_password_hash(new), g.user["id"]),
        )
    conn.close()
    audit("password_change", g.user["username"], True)
    return jsonify(status="ok")


# ---------------------------------------------------------------- user management
def _allowed_roles(actor_role):
    return ROLES if actor_role == "superadmin" else ("user", "admin")


@bp.get("/api/users")
@require_role("admin")
def list_users():
    conn = connect()
    rows = conn.execute("SELECT * FROM users ORDER BY id").fetchall()
    conn.close()
    return jsonify([_public(r) for r in rows])


@bp.post("/api/users")
@require_role("admin")
def create_user():
    data = _json()
    username = str(data.get("username", "")).strip()
    password = str(data.get("password", ""))
    role = data.get("role", "user")

    if not USERNAME_RE.match(username):
        return jsonify(error="Username: 3 to 32 characters (letters, digits, . _ -)."), 400
    problem = password_error(password, username)
    if problem:
        return jsonify(error=problem), 400
    if role not in ROLES:
        return jsonify(error="Unknown role."), 400
    if role not in _allowed_roles(g.user["role"]):
        audit("forbidden", g.user["username"], False, f"create user with role {role}")
        return jsonify(error="You cannot create an account with this role."), 403

    conn = connect()
    try:
        with conn:
            conn.execute(
                "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
                (username, generate_password_hash(password), role),
            )
    except sqlite3.IntegrityError:
        conn.close()
        return jsonify(error="This username already exists."), 409
    row = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    conn.close()
    audit("user_created", g.user["username"], True, f"{username} ({role})")
    return jsonify(_public(row)), 201


@bp.patch("/api/users/<int:uid>")
@require_role("admin")
def update_user(uid):
    data = _json()
    actor = g.user

    conn = connect()
    target = conn.execute("SELECT * FROM users WHERE id = ?", (uid,)).fetchone()
    if target is None:
        conn.close()
        return jsonify(error="User not found."), 404
    if target["id"] == actor["id"]:
        conn.close()
        return jsonify(error="You cannot change your own role or status."), 400
    # An admin may only manage accounts that currently have the "user" role.
    if actor["role"] == "admin" and target["role"] != "user":
        conn.close()
        audit("forbidden", actor["username"], False, f"modify {target['username']}")
        return jsonify(error="Insufficient permissions for this account."), 403

    changes = {}
    if "role" in data:
        if data["role"] not in ROLES:
            conn.close()
            return jsonify(error="Unknown role."), 400
        if data["role"] not in _allowed_roles(actor["role"]):
            conn.close()
            audit("forbidden", actor["username"], False, f"set role {data['role']}")
            return jsonify(error="You cannot assign this role."), 403
        changes["role"] = data["role"]
    if "active" in data:
        if not isinstance(data["active"], bool):
            conn.close()
            return jsonify(error="'active' must be true or false."), 400
        changes["active"] = int(data["active"])
    if not changes:
        conn.close()
        return jsonify(error="Nothing to change."), 400

    sets = ", ".join(f"{column} = ?" for column in changes)  # column names come from the whitelist above
    with conn:
        conn.execute(f"UPDATE users SET {sets} WHERE id = ?", (*changes.values(), uid))
    row = conn.execute("SELECT * FROM users WHERE id = ?", (uid,)).fetchone()
    conn.close()
    audit("user_updated", actor["username"], True, f"{target['username']}: {changes}")
    return jsonify(_public(row))


# ---------------------------------------------------------------- audit log
@bp.get("/api/audit")
@require_role("superadmin")
def audit_log():
    limit = min(request.args.get("limit", default=100, type=int), 500)
    conn = connect()
    rows = conn.execute(
        "SELECT id, ts, username, ip, action, success, detail FROM audit_log "
        "ORDER BY id DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])
