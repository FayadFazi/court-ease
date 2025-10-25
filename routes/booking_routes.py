from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from court_booking.config import get_db_connection
from datetime import datetime, timedelta
from extensions import limiter

booking_bp = Blueprint('booking', __name__)

def _login_required() -> bool:
    return 'user_id' in session

@booking_bp.route('/dashboard')
def dashboard():
    if not _login_required():
        flash("Please login first.", "warning")
        return redirect(url_for('auth.login'))

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT b.id, c.court_name, b.booking_date, b.start_time, b.end_time
        FROM bookings b
        JOIN courts c ON b.court_id = c.id
        WHERE b.user_id=%s
        ORDER BY b.booking_date ASC, b.start_time ASC
    """, (session['user_id'],))
    bookings = cursor.fetchall()
    cursor.close(); conn.close()
    return render_template('dashboard.html', name=session.get('name'), username=session.get('username'), bookings=bookings)

@booking_bp.route('/book', methods=['GET', 'POST'])
@limiter.limit("20/hour;100/day")
def book():
    if not _login_required():
        flash("Please login first.", "warning")
        return redirect(url_for('auth.login'))

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    if request.method == 'POST':
        court_id = request.form['court_id']
        booking_date = request.form['date']
        start_time_input = request.form['start_time']  
        end_time_input = request.form['end_time']

        try:
            start_dt = datetime.strptime(start_time_input.strip(), "%H:%M")
            end_dt = datetime.strptime(end_time_input.strip(), "%H:%M")
            if end_dt <= start_dt:
                end_dt += timedelta(days=1)
            start_db = start_dt.strftime("%H:%M:%S")
            end_db = end_dt.strftime("%H:%M:%S")
            start_display = start_dt.strftime("%I:%M %p")
            end_display = end_dt.strftime("%I:%M %p")
        except ValueError:
            flash("Invalid time format. Please use hh:mm", "danger")
            cursor.close(); conn.close()
            return redirect(url_for('booking.book'))

        cursor.execute("""
            SELECT 1 FROM bookings
            WHERE court_id=%s AND booking_date=%s
              AND NOT (end_time <= %s OR start_time >= %s)
        """, (court_id, booking_date, start_db, end_db))
        if cursor.fetchone():
            flash("This court is already booked during that time slot.", "warning")
            cursor.close(); conn.close()
            return redirect(url_for('booking.book'))

        cursor.execute("""
            INSERT INTO bookings (court_id, user_id, booking_date, start_time, end_time)
            VALUES (%s, %s, %s, %s, %s)
        """, (court_id, session['user_id'], booking_date, start_db, end_db))
        conn.commit()
        cursor.close(); conn.close()

        flash(f"Booking confirmed: {start_display} - {end_display}", "success")
        return redirect(url_for('booking.manage_bookings'))

    cursor.execute("SELECT * FROM courts ORDER BY court_name ASC")
    courts = cursor.fetchall()
    cursor.close(); conn.close()
    return render_template('book.html', courts=courts)

@booking_bp.route('/manage_bookings')
def manage_bookings():
    if not _login_required():
        flash("Please login first.", "warning")
        return redirect(url_for('auth.login'))

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT b.id, c.court_name, b.booking_date, b.start_time, b.end_time
        FROM bookings b
        JOIN courts c ON b.court_id = c.id
        WHERE b.user_id=%s
        ORDER BY b.booking_date ASC, b.start_time ASC
    """, (session['user_id'],))
    bookings = cursor.fetchall()
    cursor.close(); conn.close()
    return render_template('manage_bookings.html', bookings=bookings)

@booking_bp.route('/edit_booking/<int:booking_id>', methods=['GET', 'POST'])
@limiter.limit("30/hour")
def edit_booking(booking_id):
    if not _login_required():
        flash("Please login first.", "warning")
        return redirect(url_for('auth.login'))

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    if request.method == 'POST':
        court_id = request.form['court_id']
        booking_date = request.form['date']
        start_time_input = request.form['start_time']
        end_time_input = request.form['end_time']

        try:
            start_dt = datetime.strptime(start_time_input.strip(), "%H:%M")
            end_dt = datetime.strptime(end_time_input.strip(), "%H:%M")
            if end_dt <= start_dt:
                end_dt += timedelta(days=1)
            start_db = start_dt.strftime("%H:%M:%S")
            end_db = end_dt.strftime("%H:%M:%S")
            start_display = start_dt.strftime("%I:%M %p")
            end_display = end_dt.strftime("%I:%M %p")
        except ValueError:
            flash("Invalid time format. Please use hh:mm", "danger")
            cursor.close(); conn.close()
            return redirect(url_for('booking.edit_booking', booking_id=booking_id))

        
        cursor.execute("""
            SELECT 1 FROM bookings
            WHERE court_id=%s AND booking_date=%s
              AND NOT (end_time <= %s OR start_time >= %s)
              AND id <> %s
        """, (court_id, booking_date, start_db, end_db, booking_id))
        if cursor.fetchone():
            flash("This court is already booked during that time slot.", "warning")
            cursor.close(); conn.close()
            return redirect(url_for('booking.edit_booking', booking_id=booking_id))

        cursor.execute("""
            UPDATE bookings
            SET court_id=%s, booking_date=%s, start_time=%s, end_time=%s
            WHERE id=%s AND user_id=%s
        """, (court_id, booking_date, start_db, end_db, booking_id, session['user_id']))
        conn.commit()
        cursor.close(); conn.close()

        flash(f"Booking updated: {start_display} - {end_display}", "success")
        return redirect(url_for('booking.manage_bookings'))

    
    cursor.execute("SELECT * FROM bookings WHERE id=%s AND user_id=%s", (booking_id, session['user_id']))
    booking = cursor.fetchone()
    cursor.execute("SELECT * FROM courts ORDER BY court_name ASC")
    courts = cursor.fetchall()
    cursor.close(); conn.close()

    
    if booking:
        from datetime import timedelta as _td
        if isinstance(booking.get('start_time'), _td):
            total = booking['start_time'].total_seconds()
            booking['start_time_str'] = f"{int(total//3600):02d}:{int((total%3600)//60):02d}"
        else:
            booking['start_time_str'] = str(booking.get('start_time') or "")
        if isinstance(booking.get('end_time'), _td):
            total = booking['end_time'].total_seconds()
            booking['end_time_str'] = f"{int(total//3600):02d}:{int((total%3600)//60):02d}"
        else:
            booking['end_time_str'] = str(booking.get('end_time') or "")

    return render_template('edit_booking.html', booking=booking, courts=courts)


@booking_bp.route('/cancel_booking/<int:booking_id>', methods=['POST'])
@limiter.limit("30/hour")
def cancel_booking(booking_id):
    if not _login_required():
        flash("Please login first.", "warning")
        return redirect(url_for('auth.login'))

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("DELETE FROM bookings WHERE id=%s AND user_id=%s", (booking_id, session['user_id']))
    conn.commit()
    cursor.close(); conn.close()

    flash("Booking cancelled successfully.", "success")
    return redirect(url_for('booking.manage_bookings'))