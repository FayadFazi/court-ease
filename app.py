from flask import Flask, request
import os
from datetime import timedelta
from flask_wtf import CSRFProtect
from extensions import limiter
from dotenv import load_dotenv, find_dotenv

load_dotenv(find_dotenv(), override=False)

app = Flask(__name__)
if not os.getenv("SECRET_KEY") and os.getenv("FLASK_DEBUG") != "1":
    raise RuntimeError("SECRET_KEY must be set in production")
app.secret_key = os.getenv("SECRET_KEY", "dev-only-not-secret")

app.config.update(
    SESSION_COOKIE_NAME="cb_session",
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=(os.getenv("FLASK_DEBUG") != "1"),
    MAX_CONTENT_LENGTH=5 * 1024 * 1024,
)
app.permanent_session_lifetime = timedelta(minutes=30)

csrf = CSRFProtect(app)
@app.context_processor
def inject_csrf_token():
    from flask_wtf.csrf import generate_csrf
    return dict(csrf_token=generate_csrf)

limiter.init_app(app)

from routes.auth_routes import auth_bp
from routes.booking_routes import booking_bp
from routes.calendar_routes import calendar_bp
from routes.admin_routes import admin_bp
app.register_blueprint(auth_bp)
app.register_blueprint(booking_bp)
app.register_blueprint(calendar_bp)
app.register_blueprint(admin_bp)

@app.after_request
def add_security_headers(response):
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("Permissions-Policy", "geolocation=(), microphone=(), camera=()")

    response.headers.setdefault(
        "Content-Security-Policy",
        "default-src 'self'; "
        "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://unpkg.com https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.gstatic.com data:; "
        "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://cdn.tailwindcss.com https://unpkg.com; "
        "img-src 'self' data:; "
        "object-src 'none'; frame-ancestors 'none'; base-uri 'self';"
    )

    if os.getenv("FLASK_DEBUG") != "1":
        response.headers.setdefault(
            "Strict-Transport-Security",
            "max-age=31536000; includeSubDomains; preload"
        )

    if request.endpoint in ("auth.login", "admin_bp.login"):
        response.headers["Cache-Control"] = "no-store"
        response.headers["Pragma"] = "no-cache"

    return response

@app.errorhandler(403)
def forbidden(e):  return ("Forbidden", 403)

@app.errorhandler(404)
def not_found(e):  return ("Not Found", 404)

@app.errorhandler(405)
def method_not_allowed(e):  return ("Method Not Allowed", 405)

if os.getenv("FLASK_DEBUG") != "1":
    @app.errorhandler(500)
    def server_error(e):  return ("Server error", 500)

if os.getenv("FLASK_DEBUG") == "1":
    @app.route("/_dbtest")
    def _dbtest():
        try:
            from court_booking.config import get_db_connection
            conn = get_db_connection()
            cur = conn.cursor(dictionary=True)
            cur.execute("SELECT 1 AS ok")
            row = cur.fetchone()
            cur.close(); conn.close()
            return {"db": "OK", "row": row}, 200
        except Exception as exc:
            return {"db": "ERROR", "error": str(exc)}, 500

if __name__ == "__main__":
    app.run(debug=(os.getenv("FLASK_DEBUG") == "1"))