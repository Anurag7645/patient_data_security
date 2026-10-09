# Secure Health – Phase 1

**Cybersecurity Framework for Secure Patient Data Transmission in Healthcare Networks**

A research-review Django prototype demonstrating core cybersecurity principles for modern healthcare networks. Built as a companion to the original research presentation.

---

## Tech Stack

| Layer     | Technology               |
|-----------|--------------------------|
| Language  | Python 3 (3.12+ recommended) |
| Framework | Django 5.2               |
| Database  | SQLite (built-in)        |
| Frontend  | Django Templates, Bootstrap 5, Bootstrap Icons |
| Static    | WhiteNoise               |

---

## Project Structure

```
patient_data_sec/
├── core/                  # Main app: views, URLs
│   ├── migrations/
│   ├── apps.py
│   ├── urls.py
│   └── views.py
├── secure_health/         # Django project package
│   ├── settings.py
│   ├── urls.py
│   └── wsgi.py
├── static/
│   └── css/main.css       # Custom styles
├── templates/
│   ├── base.html          # Shared layout
│   └── core/
│       ├── home.html      # Landing page
│       ├── dashboard.html # Auth-protected dashboard
│       └── login.html     # Sign-in form
├── manage.py
├── requirements.txt
└── .gitignore
```

---

## Installation

### 1. Clone / enter the project directory

```bash
cd patient_data_sec
```

### 2. Create and activate a virtual environment

```bash
python3 -m venv venv
source venv/bin/activate        # Linux / macOS
# venv\Scripts\activate.bat     # Windows
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Apply migrations

```bash
python manage.py migrate
```

### 5. Create an admin / superuser (optional, for login testing)

```bash
python manage.py createsuperuser
```

### 6. Collect static files (optional for development)

```bash
python manage.py collectstatic --no-input
```

### 7. Start the development server

```bash
python manage.py runserver
```

Open **http://127.0.0.1:8000/** in your browser.

---

## Pages (Phase 1)

| URL         | Description                              |
|-------------|------------------------------------------|
| `/`         | Public home page with framework overview |
| `/login/`   | Sign-in form                             |
| `/dashboard/` | Auth-protected dashboard              |
| `/logout/`  | Logs out and redirects to home           |
| `/admin/`   | Django admin panel                       |

---

## Phase Roadmap

- **Phase 1** ✅ – Foundation, home page, login, SQLite, navigation
- **Phase 2** – User roles, auth hardening, audit log model
- **Phase 3** – Threat modelling visualisations, compliance reports
- **Phase 4** – Incident response module, policy documentation

---

## Notes

- `DEBUG = True` and `SECRET_KEY` are set for development only. Change both before any deployment.
- No SMTP, email, React, Docker, PostgreSQL, or cloud services are used in Phase 1.
# patient_data_security
