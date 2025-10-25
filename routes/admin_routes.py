from flask import Blueprint, render_template, redirect, url_for, session, flash, request, abort, Response
from functools import wraps
from extensions import limiter
from court_booking.config import get_db_connection
from security import verify_and_upgrade_password, fresh_admin_required, ensure_not_last_active_admin
import time, math, csv, io
from datetime import date, datetime, timedelta
import calendar as _cal

admin_bp = Blueprint('admin_bp', __name__, template_folder='templates')


def _parse_int(val, default, lo=1, hi=1000):
    try:
        x = int(val)
        return max(lo, min(hi, x))
    except Exception:
        return default

def _to_hhmm(v):
    from datetime import timedelta as _td
    if v is None: return "00:00"
    if isinstance(v, _td):
        secs = int(v.total_seconds()) % 86400
        h, m = secs // 3600, (secs % 3600) // 60
        return f"{h:02d}:{m:02d}"
    s = str(v)
    if len(s) >= 5: return s[:5]
    try:
        return datetime.strptime(s, "%H:%M:%S").strftime("%H:%M")
    except Exception:
        return s

def _ordinal(n: int) -> str:
    return f"{n}{'th' if 11<=n%100<=13 else {1:'st',2:'nd',3:'rd'}.get(n%10,'th')}"

def _month_bounds(y: int, m: int):
    first = date(y, m, 1)
    last_day = _cal.monthrange(y, m)[1]
    last = date(y, m, last_day)
    start = first - timedelta(days=first.weekday())
    end = last + timedelta(days=(6 - last.weekday()))
    return first, last, start, end


@admin_bp.before_request
def restrict_to_admins():
    if request.endpoint in ("admin_bp.login", "static"):
        return
    uid = session.get("user_id")
    role = session.get("role")
    if not uid or role != "admin":
        flash("Access denied. Admins only.", "danger")
        return redirect(url_for("auth.login"))
    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT id, role, active FROM users WHERE id=%s", (uid,))
    user = cur.fetchone()
    cur.close(); conn.close()
    if not user or user["role"] != "admin" or int(user.get("active", 1)) != 1:
        session.clear()
        abort(403)

def admin_required(f):
    @wraps(f)
    def wrapper(*a, **kw):
        if "user_id" not in session or session.get("role") != "admin":
            flash("Access denied. Admins only.", "danger")
            return redirect(url_for("auth.login"))
        return f(*a, **kw)
    return wrapper


@admin_bp.route("/admin/login", methods=["GET", "POST"])
@limiter.limit("5/minute;50/hour", key_func=lambda: request.form.get("username") or request.remote_addr)
def login():
    if request.method == "POST":
        username_or_email = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""

        conn = get_db_connection()
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT * FROM users WHERE username=%s OR email=%s", (username_or_email, username_or_email))
        user = cur.fetchone()
        cur.close(); conn.close()

        if user and user.get("role") == "admin" and int(user.get("active", 1)) == 1:
            if verify_and_upgrade_password(password, user["password"], user["id"]):
                session.clear()
                session["user_id"] = user["id"]
                session["username"] = user["username"]
                session["role"] = user["role"]
                session["authn_time"] = int(time.time())
                flash("Logged in successfully!", "success")
                return redirect(url_for("admin_bp.dashboard"))

        flash("Invalid admin credentials.", "danger")
        return redirect(url_for("admin_bp.login"))
    return render_template("admin_login.html")


@admin_bp.route("/admin/dashboard")
@admin_required
def dashboard():
    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)

    cur.execute("SELECT COUNT(*) AS c FROM users"); total_users = cur.fetchone()["c"]
    cur.execute("SELECT COUNT(*) AS c FROM users WHERE active=1"); active_users = cur.fetchone()["c"]
    cur.execute("SELECT COUNT(*) AS c FROM bookings"); total_bookings = cur.fetchone()["c"]
    cur.execute("SELECT COUNT(*) AS c FROM courts"); total_courts = cur.fetchone()["c"]

    cur.execute("""
        SELECT booking_date AS d, COUNT(*) AS c
        FROM bookings
        WHERE booking_date >= DATE_SUB(CURDATE(), INTERVAL 14 DAY)
        GROUP BY booking_date
        ORDER BY booking_date ASC
    """)
    trend = cur.fetchall()
    bookings_labels = [str(r["d"]) for r in trend]
    bookings_counts = [int(r["c"]) for r in trend]

    cur.execute("""
        SELECT b.id, u.username, c.court_name, b.booking_date, b.start_time, b.end_time
        FROM bookings b
        JOIN users u ON b.user_id = u.id
        JOIN courts c ON b.court_id = c.id
        ORDER BY b.booking_date DESC, b.start_time DESC
        LIMIT 10
    """)
    bookings = cur.fetchall()

    cur.close(); conn.close()

    stats = {
        "total_users": total_users,
        "active_users": active_users,
        "inactive_users": max(0, total_users - active_users),
        "total_bookings": total_bookings,
        "total_courts": total_courts,
    }
    return render_template(
        "admin_dashboard.html",
        stats=stats,
        bookings_labels=bookings_labels,
        bookings_counts=bookings_counts,
        bookings=bookings,
    )


@admin_bp.route("/admin/manage_bookings")
@admin_required
def admin_manage_bookings():
    q = (request.args.get("q") or "").strip()
    court_id = (request.args.get("court_id") or "").strip()
    date_from = (request.args.get("from") or "").strip()
    date_to = (request.args.get("to") or "").strip()
    page = _parse_int(request.args.get("page"), 1, 1, 100000)
    per_page = _parse_int(request.args.get("per_page"), 20, 1, 100)

    where, params = [], []
    if q:
        where.append("(u.username LIKE %s OR u.email LIKE %s)")
        like = f"%{q}%"; params.extend([like, like])
    if court_id:
        where.append("b.court_id = %s"); params.append(court_id)
    if date_from:
        where.append("b.booking_date >= %s"); params.append(date_from)
    if date_to:
        where.append("b.booking_date <= %s"); params.append(date_to)
    where_sql = "WHERE " + " AND ".join(where) if where else ""

    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)

    cur.execute(f"""
        SELECT COUNT(*) AS cnt
        FROM bookings b
        JOIN users u ON b.user_id = u.id
        {where_sql}
    """, params)
    total = cur.fetchone()["cnt"]

    offset = (page - 1) * per_page
    cur.execute(f"""
        SELECT b.id, u.username, c.court_name, b.booking_date, b.start_time, b.end_time
        FROM bookings b
        JOIN users u ON b.user_id = u.id
        JOIN courts c ON b.court_id = c.id
        {where_sql}
        ORDER BY b.booking_date DESC, b.start_time DESC
        LIMIT %s OFFSET %s
    """, params + [per_page, offset])
    bookings = cur.fetchall()

    cur2 = conn.cursor(dictionary=True)
    cur2.execute("SELECT id, court_name FROM courts ORDER BY court_name ASC")
    courts = cur2.fetchall()
    cur2.close(); cur.close(); conn.close()

    pages = max(1, math.ceil(total / per_page))
    return render_template("admin_bookings.html",
                           bookings=bookings, courts=courts,
                           total=total, page=page, pages=pages, per_page=per_page,
                           q=q, court_id=court_id, date_from=date_from, date_to=date_to)

@admin_bp.route("/admin/export_bookings.csv")
@admin_required
def export_bookings_csv():
    q = (request.args.get("q") or "").strip()
    court_id = (request.args.get("court_id") or "").strip()
    date_from = (request.args.get("from") or "").strip()
    date_to = (request.args.get("to") or "").strip()

    where, params = [], []
    if q:
        where.append("(u.username LIKE %s OR u.email LIKE %s)")
        like = f"%{q}%"; params.extend([like, like])
    if court_id:
        where.append("b.court_id = %s"); params.append(court_id)
    if date_from:
        where.append("b.booking_date >= %s"); params.append(date_from)
    if date_to:
        where.append("b.booking_date <= %s"); params.append(date_to)
    where_sql = "WHERE " + " AND ".join(where) if where else ""

    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)
    cur.execute(f"""
        SELECT b.id, u.username, u.email, c.court_name, b.booking_date, b.start_time, b.end_time
        FROM bookings b
        JOIN users u ON b.user_id = u.id
        JOIN courts c ON b.court_id = c.id
        {where_sql}
        ORDER BY b.booking_date DESC, b.start_time DESC
    """, params)
    rows = cur.fetchall()
    cur.close(); conn.close()

    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["ID","Username","Email","Court","Date","Start","End"])
    for r in rows:
        w.writerow([r["id"], r["username"], r["email"], r["court_name"], r["booking_date"], r["start_time"], r["end_time"]])

    return Response(out.getvalue(),
                    mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=bookings_export.csv"})

@admin_bp.route("/admin/edit_booking/<int:booking_id>", methods=["GET", "POST"])
@admin_required
def admin_edit_booking(booking_id):
    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)
    if request.method == "POST":
        court_id = request.form.get("court_id")
        booking_date = request.form.get("booking_date")
        start_time = request.form.get("start_time")
        end_time = request.form.get("end_time")
        cur.execute("""
            UPDATE bookings
            SET court_id=%s, booking_date=%s, start_time=%s, end_time=%s
            WHERE id=%s
        """, (court_id, booking_date, start_time, end_time, booking_id))
        conn.commit()
        flash("Booking updated successfully!", "success")
        cur.close(); conn.close()
        return redirect(url_for("admin_bp.admin_manage_bookings"))

    cur.execute("""
        SELECT b.*, u.username, c.court_name
        FROM bookings b
        JOIN users u ON b.user_id = u.id
        JOIN courts c ON b.court_id = c.id
        WHERE b.id=%s
    """, (booking_id,))
    booking = cur.fetchone()
    cur.execute("SELECT id, court_name FROM courts ORDER BY court_name ASC")
    courts = cur.fetchall()
    cur.close(); conn.close()

    if not booking:
        flash("Booking not found.", "danger")
        return redirect(url_for("admin_bp.admin_manage_bookings"))
    return render_template("admin_edit_booking.html", booking=booking, courts=courts)

@admin_bp.route("/admin/delete_booking/<int:booking_id>", methods=["POST"])
@admin_required
@limiter.limit("20/hour")
def admin_delete_booking(booking_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM bookings WHERE id=%s", (booking_id,))
    conn.commit()
    cur.close(); conn.close()
    flash("Booking deleted successfully!", "success")
    return redirect(url_for("admin_bp.admin_manage_bookings"))


@admin_bp.route("/admin/manage_users")
@admin_required
def admin_manage_users():
    q = (request.args.get("q") or "").strip()
    role = (request.args.get("role") or "").strip()
    active = request.args.get("active")
    page = _parse_int(request.args.get("page"), 1, 1, 100000)
    per_page = _parse_int(request.args.get("per_page"), 20, 1, 100)

    where, params = [], []
    if q:
        like = f"%{q}%"
        where.append("(name LIKE %s OR username LIKE %s OR email LIKE %s)")
        params.extend([like, like, like])
    if role in ("user","admin"):
        where.append("role = %s"); params.append(role)
    if active in ("0","1"):
        where.append("active = %s"); params.append(int(active))
    where_sql = "WHERE " + " AND ".join(where) if where else ""

    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)
    cur.execute(f"SELECT COUNT(*) AS cnt FROM users {where_sql}", params)
    total = cur.fetchone()["cnt"]

    offset = (page - 1) * per_page
    cur.execute(f"""
        SELECT id, name, username, email, role, active
        FROM users
        {where_sql}
        ORDER BY id ASC
        LIMIT %s OFFSET %s
    """, params + [per_page, offset])
    users = cur.fetchall()
    cur.close(); conn.close()

    pages = max(1, math.ceil(total / per_page))
    return render_template("admin_manage_users.html",
                           users=users, total=total, page=page, pages=pages, per_page=per_page,
                           q=q, role=role, active=active)

@admin_bp.route("/admin/edit_user/<int:user_id>", methods=["GET", "POST"])
@admin_required
@fresh_admin_required(600)
def admin_edit_user(user_id):
    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)
    if request.method == "POST":
        name = request.form.get("name")
        username = request.form.get("username")
        email = request.form.get("email")
        role = request.form.get("role")
        active = 1 if request.form.get("active") == "1" else 0

        if not ensure_not_last_active_admin(user_id, new_role=role, deleting=False):
            flash("Operation blocked: would remove the last active admin.", "danger")
            cur.close(); conn.close()
            return redirect(url_for("admin_bp.admin_manage_users"))

        cur.execute("""
            UPDATE users SET name=%s, username=%s, email=%s, role=%s, active=%s
            WHERE id=%s
        """, (name, username, email, role, active, user_id))
        conn.commit()
        flash("User updated successfully!", "success")
        cur.close(); conn.close()
        return redirect(url_for("admin_bp.admin_manage_users"))

    cur.execute("SELECT * FROM users WHERE id=%s", (user_id,))
    user = cur.fetchone()
    cur.close(); conn.close()
    if not user:
        flash("User not found.", "danger")
        return redirect(url_for("admin_bp.admin_manage_users"))
    return render_template("admin_edit_user.html", user=user)

@admin_bp.route("/admin/delete_user/<int:user_id>", methods=["POST"])
@admin_required
@fresh_admin_required(600)
@limiter.limit("20/hour")
def admin_delete_user(user_id):
    if not ensure_not_last_active_admin(user_id, deleting=True):
        flash("Operation blocked: cannot delete the last active admin.", "danger")
        return redirect(url_for("admin_bp.admin_manage_users"))
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM users WHERE id=%s", (user_id,))
    conn.commit()
    cur.close(); conn.close()
    flash("User deleted successfully!", "success")
    return redirect(url_for("admin_bp.admin_manage_users"))


@admin_bp.route("/admin/courts")
@admin_required
def manage_courts():
    conn = get_db_connection(); cur = conn.cursor(dictionary=True)
    cur.execute("SELECT id, court_name, status FROM courts ORDER BY court_name ASC")
    courts = cur.fetchall()
    cur.close(); conn.close()
    return render_template("admin_courts.html", courts=courts)

@admin_bp.route("/admin/edit_court/<int:court_id>", methods=["GET", "POST"])
@admin_required
@fresh_admin_required(600)
def edit_court(court_id):
    conn = get_db_connection(); cur = conn.cursor(dictionary=True)
    if request.method == "POST":
        name = request.form.get("name") or ""
        status = request.form.get("status") or "Available"
        if court_id == 0:
            cur.execute("INSERT INTO courts (court_name, status) VALUES (%s, %s)", (name, status))
        else:
            cur.execute("UPDATE courts SET court_name=%s, status=%s WHERE id=%s", (name, status, court_id))
        conn.commit()
        cur.close(); conn.close()
        flash("Court saved.", "success")
        return redirect(url_for("admin_bp.manage_courts"))
    court = None
    if court_id != 0:
        cur.execute("SELECT id, court_name, status FROM courts WHERE id=%s", (court_id,))
        court = cur.fetchone()
    cur.close(); conn.close()
    return render_template("admin_edit_court.html", court=court)

@admin_bp.route("/admin/delete_court/<int:court_id>", methods=["POST"])
@admin_required
@fresh_admin_required(600)
@limiter.limit("20/hour")
def delete_court(court_id):
    conn = get_db_connection(); cur = conn.cursor()
    cur.execute("DELETE FROM courts WHERE id=%s", (court_id,))
    conn.commit()
    cur.close(); conn.close()
    flash("Court deleted.", "success")
    return redirect(url_for("admin_bp.manage_courts"))


@admin_bp.route("/admin/upcoming")
@admin_required
def upcoming():
    from datetime import date as _date, datetime as _dt, timedelta as _td
    import calendar as _calmod

    today = _date.today()

    
    try:
        y = int(request.args.get("year", today.year))
    except Exception:
        y = today.year
    try:
        m = int(request.args.get("month", today.month))
    except Exception:
        m = today.month
    if m < 1 or m > 12:
        m = today.month

    
    first = _date(y, m, 1)
    last_day = _calmod.monthrange(y, m)[1]
    last = _date(y, m, last_day)
    grid_start = first - _td(days=first.weekday())
    grid_end = last + _td(days=(6 - last.weekday()))

   
    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)
    cur.execute("""
      SELECT b.id, u.username, u.email, c.court_name, b.booking_date, b.start_time, b.end_time
      FROM bookings b
      JOIN users u ON b.user_id = u.id
      JOIN courts c ON b.court_id = c.id
      WHERE b.booking_date BETWEEN %s AND %s
      ORDER BY b.booking_date ASC, b.start_time ASC
    """, (first, last))
    rows = cur.fetchall()
    cur.close()
    conn.close()

    
    def _ordinal(n: int) -> str:
        return f"{n}{'th' if 11 <= n % 100 <= 13 else {1:'st',2:'nd',3:'rd'}.get(n%10, 'th')}"
    def _to_hhmm(v) -> str:
        if v is None:
            return "00:00"
        if isinstance(v, _td):
            secs = int(v.total_seconds()) % 86400
            h, m2 = secs // 3600, (secs % 3600) // 60
            return f"{h:02d}:{m2:02d}"
        s = str(v)
        if len(s) >= 5:
            return s[:5]
        try:
            return _dt.strptime(s, "%H:%M:%S").strftime("%H:%M")
        except Exception:
            return s

   
    items = []
    for r in rows:
        d = r["booking_date"]
        if isinstance(d, _dt):
            d = d.date()
        if not d:
            continue
        if d < today:
            continue
        items.append({
            "id": r["id"],
            "username": r["username"],
            "email": r["email"],
            "court_name": r["court_name"],
            "date_str": f"{_calmod.month_name[d.month]} {_ordinal(d.day)}, {d.year} at {_to_hhmm(r['start_time'])}",
        })

    
    weeks = []
    curd = grid_start
    while curd <= grid_end:
        week = []
        for _ in range(7):
            week.append({
                "day": curd.day,
                "in_month": 1 if curd.month == m else 0,
                "is_today": 1 if curd == today else 0,
            })
            curd += _td(days=1)
        weeks.append(week)

    
    prev_month = 12 if m == 1 else m - 1
    prev_year = y - 1 if m == 1 else y
    next_month = 1 if m == 12 else m + 1
    next_year = y + 1 if m == 12 else y

    return render_template(
        "admin_upcoming.html",
        items=items,
        year=y,
        month=m,
        month_name=_calmod.month_name[m],
        weeks=weeks,
        prev_year=prev_year,
        prev_month=prev_month,
        next_year=next_year,
        next_month=next_month,
        today_year=today.year,
        today_month=today.month,
    )

        
@admin_bp.route("/admin/book", methods=["GET", "POST"])
@admin_required
def create_booking():
    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)

    if request.method == "POST":
        user_id = request.form.get("user_id")
        court_id = request.form.get("court_id")
        booking_date = request.form.get("date")
        start_time = request.form.get("start_time")
        end_time = request.form.get("end_time")

        
        cur.execute("""
          SELECT 1 FROM bookings
          WHERE court_id=%s AND booking_date=%s
            AND NOT (end_time <= %s OR start_time >= %s)
        """, (court_id, booking_date, start_time, end_time))
        conflict = cur.fetchone()
        if conflict:
            flash("This court is already booked during that time slot.", "warning")
        else:
            cur.execute("""
              INSERT INTO bookings (court_id, user_id, booking_date, start_time, end_time)
              VALUES (%s, %s, %s, %s, %s)
            """, (court_id, user_id, booking_date, start_time, end_time))
            conn.commit()
            flash("Booking created.", "success")
            cur.close(); conn.close()
            return redirect(url_for("admin_bp.upcoming"))

    
    cur.execute("SELECT id, username, email FROM users WHERE active=1 ORDER BY username ASC")
    users = cur.fetchall()
    cur.execute("SELECT id, court_name FROM courts ORDER BY court_name ASC")
    courts = cur.fetchall()
    cur.close(); conn.close()
    return render_template("admin_create_booking.html", users=users, courts=courts)

   
    days = []
    curd = grid_start
    while curd <= grid_end:
        days.append({
            "day": curd.day,
            "in_month": (curd.month == m),
            "is_today": (curd == today),
        })
        curd += timedelta(days=1)
    weeks = [days[i:i+7] for i in range(0, len(days), 7)]

    prev_m = (m - 1) or 12
    prev_y = y - 1 if prev_m == 12 else y
    next_m = (m + 1) if m < 12 else 1
    next_y = y + 1 if next_m == 1 else y

    return render_template("admin_upcoming.html",
                           items=items,
                           year=y, month=m, month_name=_cal.month_name[m],
                           weeks=weeks,
                           prev_year=prev_y, prev_month=prev_m,
                           next_year=next_y, next_month=next_m)