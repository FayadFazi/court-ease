from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from extensions import limiter
from court_booking.config import get_db_connection
from security import verify_and_upgrade_password
from passlib.hash import argon2
import re, time

auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/')
def index():
    return redirect(url_for('auth.login'))

@auth_bp.route('/register', methods=['GET', 'POST'])
@limiter.limit("3/minute;20/hour", key_func=lambda: request.remote_addr)
def register():
    if request.method == 'POST':
        name = request.form.get('name') or ''
        username = request.form.get('username') or ''
        email = (request.form.get('email') or '').strip().lower()
        password = request.form.get('password') or ''
        dob = request.form.get('dob') or ''
        location = request.form.get('location') or ''

        if not all([name, username, email, password, dob, location]):
            flash("All fields are required.", "warning")
            return redirect(url_for('auth.register'))

        if not re.match(r"[^@]+@[^@]+\.[^@]+", email):
            flash("Please enter a valid email address.", "warning")
            return redirect(url_for('auth.register'))

        if len(password) < 8 or password.isdigit() or password.isalpha():
            flash("Password must be at least 8 chars and include letters and numbers.", "warning")
            return redirect(url_for('auth.register'))

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT 1 FROM users WHERE username=%s OR email=%s", (username, email))
        if cursor.fetchone():
            flash("Username or email already exists.", "danger")
            cursor.close(); conn.close()
            return redirect(url_for('auth.register'))

       
        hashed_pw = argon2.hash(password)

        cursor.execute("""
            INSERT INTO users (name, username, email, password, date_of_birth, location, role, active)
            VALUES (%s, %s, %s, %s, %s, %s, 'user', 1)
        """, (name, username, email, hashed_pw, dob, location))
        conn.commit()
        cursor.close(); conn.close()
        flash("Registered successfully. Please log in.", "success")
        return redirect(url_for('auth.login'))
    return render_template('register.html')

@auth_bp.route('/login', methods=['GET', 'POST'])
@limiter.limit("5/minute;50/hour", key_func=lambda: request.form.get("email") or request.remote_addr)
def login():
    if request.method == 'POST':
        username_or_email = (request.form.get('username') or request.form.get('email') or request.form.get('username_or_email') or '').strip()
        password = request.form.get('password') or ''

        if not username_or_email or not password:
            flash("Please enter both username/email and password.", "warning")
            return redirect(url_for('auth.login'))

        email_candidate = username_or_email.lower()
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM users WHERE username=%s OR email=%s", (username_or_email, email_candidate))
        user = cursor.fetchone()
        cursor.close(); conn.close()

        if user and int(user.get("active", 1)) == 1 and verify_and_upgrade_password(password, user['password'], user['id']):
            session.clear()
            session.permanent = True
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['name'] = user.get('name')
            session['role'] = user.get('role', 'user')
            session['authn_time'] = int(time.time())
            flash("Logged in successfully!", "success")
            if user.get('role') == 'admin':
                return redirect(url_for('admin_bp.dashboard'))
            return redirect(url_for('calendar.tournament_calendar'))
        else:
            flash("Invalid username/email or password.", "danger")
            return redirect(url_for('auth.login'))
    return render_template('login.html')

@auth_bp.route('/logout', methods=["GET", "POST"])
def logout():
    session.clear()
    flash("Logged out successfully.", "info")
    return redirect(url_for('auth.login'))