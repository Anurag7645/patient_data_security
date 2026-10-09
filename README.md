# Secure Health – Phase 2

**Cybersecurity Framework for Secure Patient Data Transmission in Healthcare Networks**

A research-review Django prototype demonstrating mock OTP authentication, four user roles, and role-based patient data access. Built as a companion to the original research presentation.

> **Research prototype only.** Not for clinical use. No real patient data. OTP codes are shown on-screen for demonstration.

---

## Tech Stack

| Layer     | Technology                          |
|-----------|-------------------------------------|
| Language  | Python 3 (3.10+ compatible)         |
| Framework | Django 5.2                          |
| Database  | SQLite (built-in)                   |
| Frontend  | Django Templates, Bootstrap 5, Bootstrap Icons |
| Static    | WhiteNoise                          |
| OTP       | Python `secrets` + `hashlib` (stdlib, no external package) |

---

## Project Structure

```
patient_data_sec/
├── core/
│   ├── management/
│   │   └── commands/
│   │       └── seed_demo.py       # Demo data seeder
│   ├── migrations/
│   ├── templatetags/
│   │   └── core_tags.py           # get_role template filter
│   ├── admin.py
│   ├── apps.py
│   ├── models.py                  # UserProfile, OTPToken, PatientProfile
│   ├── tests.py                   # 36 tests
│   ├── urls.py
│   └── views.py
├── secure_health/
│   ├── settings.py
│   ├── urls.py
│   └── wsgi.py
├── static/
│   └── css/main.css
├── templates/
│   ├── base.html
│   └── core/
│       ├── home.html
│       ├── login.html             # Step 1: email entry + OTP panel
│       ├── verify.html            # Step 2: code entry
│       ├── dashboard.html         # Role-specific dashboard
│       ├── patient_list.html
│       └── patient_detail.html
├── manage.py
├── requirements.txt
└── .gitignore
```

---

## Installation

```bash
# 1. Enter the project directory
cd patient_data_sec

# 2. Create and activate a virtual environment
python3 -m venv venv
source venv/bin/activate        # Linux / macOS
# venv\Scripts\activate.bat     # Windows

# 3. Install dependencies
pip install -r requirements.txt

# 4. Apply migrations
python manage.py migrate

# 5. Seed demo data
python manage.py seed_demo

# 6. Start the development server
python manage.py runserver
```

Open **http://127.0.0.1:8000/**

---

## Mock OTP Login Flow

1. Go to **http://127.0.0.1:8000/login/**
2. Enter a demo email (see accounts below).
3. A clearly labelled **MOCK OTP AUTHENTICATION** panel shows the six-digit code.
4. Enter the code to sign in.

> Codes expire after **5 minutes**, are **single-use**, and allow a maximum of **5 attempts**.

---

## Demo Accounts

All accounts use `@securehealth.demo` emails. Passwords are disabled — use the OTP flow.

| Email | Role | Access |
|---|---|---|
| `admin@securehealth.demo` | Admin | Full user list, all patients, Django admin |
| `doctor1@securehealth.demo` | Doctor | Assigned patients (Chris Blake, Taylor Ford) |
| `doctor2@securehealth.demo` | Doctor | Assigned patients (Morgan Hayes, Jamie Ward) |
| `management@securehealth.demo` | Management | Patient list (demographics only, no medical data) |
| `patient1@securehealth.demo` | Patient | Own record only (Chris Blake – SH-P-0001) |
| `patient2@securehealth.demo` | Patient | Own record only (Taylor Ford – SH-P-0002) |
| `patient3@securehealth.demo` | Patient | Own record only (Morgan Hayes – SH-P-0003) |
| `patient4@securehealth.demo` | Patient | Own record only (Jamie Ward – SH-P-0004) |

---

## Pages

| URL | Auth | Description |
|---|---|---|
| `/` | Public | Home page with framework overview |
| `/login/` | Public | Email entry → mock OTP panel |
| `/verify/` | Session | OTP code verification |
| `/dashboard/` | Required | Role-specific dashboard |
| `/patients/` | Admin / Doctor / Management | Patient list |
| `/patients/<id>/` | RBAC-enforced | Patient detail |
| `/logout/` | Required | Clears session |
| `/admin/` | Admin | Django admin panel |

---

## Running Tests

```bash
python manage.py test core --verbosity=2
```

**36 tests, 0 failures** covering:
- OTP generation, verification, expiry, reuse, attempt limits, new-code invalidation
- Unknown email rejection
- Each role's dashboard
- Doctor access to assigned / unrelated patients
- Patient access to own / another patient's record
- Management restrictions

---

## Phase Roadmap

- **Phase 1** ✅ – Foundation, home page, navigation, SQLite, Bootstrap layout
- **Phase 2** ✅ – Mock OTP auth, 4 roles, patient records, RBAC, seeded demo data, 36 tests
- **Phase 3** – Threat modelling visualisations, compliance reports
- **Phase 4** – Incident response module, policy documentation
