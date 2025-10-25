from flask import Blueprint, render_template, session, redirect, url_for, flash, request
from datetime import date, datetime, timedelta
import calendar as cal
from court_booking.config import get_db_connection

calendar_bp = Blueprint("calendar", __name__)

def _to_minutes(val) -> int:
    """Convert MySQL TIME (timedelta or 'HH:MM:SS') to minutes after midnight."""
    if val is None:
        return 0
    try:
        from datetime import timedelta as _td
        if isinstance(val, _td):
            return int(val.total_seconds() // 60) % (24 * 60)
    except Exception:
        pass
    s = str(val)
    try:
        hh, mm, *_ = s.split(":")
        return int(hh) * 60 + int(mm)
    except Exception:
        return 0

def _hour_labels(start_h: int, end_h: int):
    out = []
    for h in range(start_h, end_h):
        if h == 0: out.append("12AM")
        elif h < 12: out.append(f"{h}AM")
        elif h == 12: out.append("12PM")
        else: out.append(f"{h-12}PM")
    return out

def fetch_bookings(start_d: date, end_d: date):
    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)
    cur.execute("""
        SELECT b.booking_date, b.start_time, b.end_time, c.court_name
        FROM bookings b
        JOIN courts c ON b.court_id = c.id
        WHERE b.booking_date BETWEEN %s AND %s
        ORDER BY b.booking_date, b.start_time
    """, (start_d, end_d))
    rows = cur.fetchall()
    cur.close(); conn.close()
    return rows

@calendar_bp.route("/tournament_calendar")
def tournament_calendar():
    if "user_id" not in session:
        flash("Please login first.", "warning")
        return redirect(url_for("auth.login"))

    today = date.today()
    view = (request.args.get("view") or "month").lower()

    
    d_param = request.args.get("d")
    try:
        focus = datetime.strptime(d_param, "%Y-%m-%d").date() if d_param else today
    except Exception:
        focus = today

   
    try:
        year = int(request.args.get("year", focus.year))
    except Exception:
        year = focus.year
    try:
        month = int(request.args.get("month", focus.month))
    except Exception:
        month = focus.month
    month = min(12, max(1, month))

    
    court_colors = {
        "Court A": "#22c55e",
        "Court B": "#3b82f6",
        "Court C": "#f59e0b",
        "Court D": "#ec4899",
    }

   
    nav_prev_d = focus
    nav_next_d = focus

    
    hours_start, hours_end = 6, 22  
    slot_minutes = 30
    row_px = 22
    rows_count = (hours_end - hours_start) * (60 // slot_minutes)
    rows_iter = list(range(rows_count))

    context = {
        "name": session.get("name"),
        "username": session.get("username"),
        "today": today.isoformat(),
        "view": view,
        "focus": focus.isoformat(),
        "year": year,
        "month": month,
        "month_name": cal.month_name[month],
    }

    if view == "month":
        first = date(year, month, 1)
        start = first - timedelta(days=first.weekday())  
        end = start + timedelta(days=41)                 
        rows = fetch_bookings(start, end)

        
        bookings_by_day = {}
        for r in rows:
            bookings_by_day.setdefault(r["booking_date"], []).append(r)

        
        days = []
        dptr = start
        while dptr <= end:
            days.append({
                "date": dptr,
                "day": dptr.day,
                "month_in_view": dptr.month == month,
                "is_today": dptr == today,
                "bookings": bookings_by_day.get(dptr, []),
            })
            dptr += timedelta(days=1)

        
        prev_month = 12 if month == 1 else month - 1
        prev_year = year - 1 if month == 1 else year
        next_month = 1 if month == 12 else month + 1
        next_year = year + 1 if month == 12 else year
        nav_prev_d = date(prev_year, prev_month, 15)
        nav_next_d = date(next_year, next_month, 15)

        context.update({
            "days": days,
        })

    elif view == "week":
        start = focus - timedelta(days=focus.weekday())  
        end = start + timedelta(days=6)
        rows = fetch_bookings(start, end)

        week_days = [start + timedelta(days=i) for i in range(7)]
        week_day_labels = [d.strftime('%a ') + str(d.day) for d in week_days]
        week_hour_labels = _hour_labels(hours_start, hours_end)

        week_events = []
        for r in rows:
            day_idx0 = (r["booking_date"] - start).days  
            smin = _to_minutes(r["start_time"])
            emin = _to_minutes(r["end_time"])
            if emin <= smin:
                emin = smin + slot_minutes
            
            smin = max(smin, hours_start * 60)
            emin = max(emin, smin + slot_minutes)
            row_start = int((smin - hours_start * 60) / slot_minutes)
            row_end = int((emin - hours_start * 60) / slot_minutes)
            row_end = max(row_end, row_start + 1)
            color = court_colors.get(r["court_name"], "#6366f1")
            top = f"{row_start * row_px}px"
            height = f"{(row_end - row_start) * row_px}px"
            left = f"calc(({day_idx0}) * (100% / 7) + 2px)"
            week_events.append({
                "left": left,
                "top": top,
                "height": height,
                "bg": color,
                "title": r["court_name"],
                "time_label": str(r["start_time"])[:5],
            })

        nav_prev_d = start - timedelta(days=7)
        nav_next_d = start + timedelta(days=7)

        context.update({
            "week_title": f"{week_days[0].strftime('%b %d')} – {week_days[-1].strftime('%b %d, %Y')}",
            "week_day_labels": week_day_labels,
            "week_hour_labels": week_hour_labels,
            "rows_iter": rows_iter,
            "week_events": week_events,
        })

    elif view == "day":
        rows = fetch_bookings(focus, focus)
        day_hour_labels = _hour_labels(hours_start, hours_end)

        day_events = []
        for r in rows:
            smin = _to_minutes(r["start_time"])
            emin = _to_minutes(r["end_time"])
            if emin <= smin:
                emin = smin + slot_minutes
            smin = max(smin, hours_start * 60)
            emin = max(emin, smin + slot_minutes)
            row_start = int((smin - hours_start * 60) / slot_minutes)
            row_end = int((emin - hours_start * 60) / slot_minutes)
            row_end = max(row_end, row_start + 1)
            color = court_colors.get(r["court_name"], "#6366f1")
            top = f"{row_start * row_px}px"
            height = f"{(row_end - row_start) * row_px}px"
            day_events.append({
                "top": top,
                "height": height,
                "bg": color,
                "title": r["court_name"],
                "time_label": str(r["start_time"])[:5],
            })

       
        first = date(focus.year, focus.month, 1)
        grid_start = first - timedelta(days=first.weekday())
        grid_end = grid_start + timedelta(days=41)
        mini_days = []
        dptr = grid_start
        while dptr <= grid_end:
            mini_days.append({
                "date_iso": dptr.isoformat(),
                "day": dptr.day,
                "in_month": dptr.month == focus.month,
                "is_selected": dptr == focus,
            })
            dptr += timedelta(days=1)

        nav_prev_d = focus - timedelta(days=1)
        nav_next_d = focus + timedelta(days=1)

        context.update({
            "day_title": focus.strftime("%B %d, %Y"),
            "day_hour_labels": day_hour_labels,
            "rows_iter": rows_iter,
            "day_events": day_events,
            "mini_days": mini_days,
            "month_name": cal.month_name[focus.month],
            "year": focus.year,
        })

    elif view == "year":
        y = year
       
        rows = fetch_bookings(date(y, 1, 1), date(y, 12, 31))
        booked_dates = {r["booking_date"] for r in rows}

        year_months = []
        for m in range(1, 13):
            first = date(y, m, 1)
            grid_start = first - timedelta(days=first.weekday())
            grid_end = grid_start + timedelta(days=41)
            cells = []
            dptr = grid_start
            while dptr <= grid_end:
                cells.append({
                    "date_iso": dptr.isoformat(),
                    "day": dptr.day,
                    "in_month": dptr.month == m,
                    "has": dptr in booked_dates,
                })
                dptr += timedelta(days=1)
            year_months.append({
                "name": cal.month_name[m],
                "days": cells,
            })

        nav_prev_d = date(y - 1, 6, 15)
        nav_next_d = date(y + 1, 6, 15)

        context.update({"year_months": year_months})

    else:
        return redirect(url_for("calendar.tournament_calendar", view="month", year=year, month=month))

   
    context.update({
        "nav_prev_d": nav_prev_d.isoformat(),
        "nav_next_d": nav_next_d.isoformat(),
    })

    return render_template("tournament_calendar.html", **context)