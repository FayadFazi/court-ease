import time
from typing import Optional
from flask import session, redirect, url_for, flash
from functools import wraps
from passlib.hash import argon2
from werkzeug.security import check_password_hash
from court_booking.config import get_db_connection

def verify_and_upgrade_password(plain: str, stored_hash: str, user_id: int) -> bool:
    """
    Supports old Werkzeug PBKDF2 hashes and Argon2.
    If PBKDF2 verifies, rehash with Argon2 and persist.
    """
    if not stored_hash:
        return False

    if stored_hash.startswith("pbkdf2:"):
        if check_password_hash(stored_hash, plain):
            new_hash = argon2.hash(plain)
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute("UPDATE users SET password=%s WHERE id=%s", (new_hash, user_id))
            conn.commit()
            cur.close(); conn.close()
            return True
        return False

    try:
        return argon2.verify(plain, stored_hash)
    except Exception:
        return False

def fresh_admin_required(max_age_seconds: int = 600):
    """
    Require admin session and recent authentication (max_age_seconds).
    """
    def deco(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            if session.get("role") != "admin":
                flash("Access denied. Admins only.", "danger")
                return redirect(url_for("auth.login"))
            t = session.get("authn_time", 0)
            if int(time.time()) - int(t) > max_age_seconds:
                flash("Please re-authenticate to continue.", "warning")
                return redirect(url_for("admin_bp.login"))
            return f(*args, **kwargs)
        return wrapper
    return deco

def ensure_not_last_active_admin(target_user_id: int, new_role: Optional[str] = None, deleting: bool = False) -> bool:
    """
    Prevent removing/demoting the last active admin.
    """
    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT id, role, active FROM users WHERE id=%s", (target_user_id,))
    target = cur.fetchone()

    cur.execute("SELECT COUNT(*) AS cnt FROM users WHERE role='admin' AND active=1")
    cnt = cur.fetchone()["cnt"]
    cur.close(); conn.close()

    if not target:
        return True

    if deleting and target["role"] == "admin" and int(target.get("active", 0)) == 1 and cnt <= 1:
        return False

    if (new_role is not None and target["role"] == "admin"
            and new_role != "admin" and int(target.get("active", 0)) == 1 and cnt <= 1):
        return False

    return True