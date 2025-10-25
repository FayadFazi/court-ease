# 🏆 Court-Ease – Court Booking System

![Court-Ease Screenshot](https://raw.githubusercontent.com/FayadFazi/court-ease/refs/heads/main/asset/image/read-me-image.png)

---

## 📋 Overview
**Court-Ease** is a simple yet powerful **Futsal Court Booking System** built with **Flask** and **MySQL**.  
Players can **register, log in, and book courts**, while **admins** manage users, courts, and bookings through a modern dashboard.  
It also includes an interactive **calendar view (Month / Week / Day / Year)** to visualize bookings and manage events easily.

---

## ✨ Features

### 👤 User Features
- 🧍 Register and log in with **Argon2 password hashing**
- 🏟️ Book courts with **real-time conflict checks** (no overlapping times)
- 📅 View bookings in a **calendar view** (Month / Week / Day / Year)
- ✏️ Manage your bookings — view, edit, or cancel

### 👩‍💼 Admin Features
- 🔐 Admin login (`/admin/login`)
- 📊 Dashboard with charts and quick stats
- 👥 Manage users (activate, edit, delete)
- 🏟️ Manage courts (add, edit, delete)
- 📘 Manage bookings (filter, edit, delete, CSV export)
- ⏰ “Upcoming” bookings view + quick booking creation

### 🛡️ Security & UX
- 🔒 **CSRF protection** on all forms (Flask-WTF)
- ⚙️ **Rate limiting** on sensitive routes (Flask-Limiter)
- 🍪 **Hardened session cookies** and **CSP headers**
- 💻 **Responsive design** using Bootstrap 5 and scoped Tailwind utilities

---

## 🧠 Tech Stack
| Component | Technology |
|------------|-------------|
| **Backend** | Python 3, Flask 3 |
| **Database** | MySQL 8 (mysql-connector) |
| **Frontend** | Bootstrap 5, Tailwind (scoped via CDN) |
| **Charts / UI** | Chart.js |
| **Security** | passlib[argon2], Flask-WTF (CSRF), Flask-Limiter |
| **Configuration** | python-dotenv (.env) |
| **Version Control** | Git & GitHub |

---

## 🗂️ Project Structure (Key Files)

court-ease/
│
├── app.py # Main Flask app entry point
├── config.py # Configuration (DB, secret keys, limits)
├── requirements.txt # Python dependencies
├── .env # Environment variables (DB credentials, secrets)
│
├── /templates # HTML templates (Flask Jinja2)
│ ├── index.html
│ ├── login.html
│ ├── register.html
│ ├── booking.html
│ ├── admin/
│ │ ├── dashboard.html
│ │ ├── users.html
│ │ ├── courts.html
│ │ └── bookings.html
│
├── /static # CSS, JS, and images
│ ├── css/
│ ├── js/
│ └── images/
│
├── /models # Database models
├── /routes # Flask routes (user, admin, booking)
└── /asset/image # Images (read-me, UI assets)

## 🚀 Getting Started

### 1️⃣ Clone the Repository
```bash
git clone https://github.com/FayadFazi/court-ease
