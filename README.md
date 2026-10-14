# Secure Health

**Cybersecurity Framework for Secure Patient Data Transmission in Healthcare Networks**

An academic prototype demonstrating core cybersecurity concepts for healthcare
data management. Built with Django 5.2, SQLite, and Bootstrap 5.

> **⚠ PROTOTYPE DISCLAIMER**  
> All patient records, documents, and user accounts are entirely fictional.  
> This system is **not** suitable for real clinical use, HIPAA compliance,
> production deployment, or any actual healthcare application.

---

## Technology Stack

| Layer        | Technology                                              |
|--------------|---------------------------------------------------------|
| Backend      | Python 3.12+, Django 5.2                               |
| Database     | SQLite (local file `db.sqlite3`)                        |
| Frontend     | Django Templates, Bootstrap 5.3, Bootstrap Icons        |
| Auth         | Mock OTP (SHA-256 hashed, session-based)               |
| PDF reports  | ReportLab 4.2.5                                         |
| Static files | WhiteNoise 6.9                                          |

---

## Implemented Features

### Phase 1 — Project Foundation
- Django project structure with SQLite
- Bootstrap 5 UI with custom CSS
- Public home page and navigation bar

### Phase 2 — Authentication & Role-Based Access Control
- **Mock OTP login** — email entry → 6-digit code shown on screen → session
- Four roles: **Admin**, **Doctor**, **Management**, **Patient**
- Role-specific dashboards
- Patient record list and detail views with RBAC enforcement
- Audit logging for access attempts

### Phase 3 — Medical Documents & Secure Sharing
- Private medical document uploads (PDF, JPG, PNG; max 5 MB)
- File extension + magic-byte content validation
- Authenticated download endpoint (never a public URL)
- **OTP-protected document sharing** — doctor creates grant → recipient verifies with mock OTP → time-limited access
- Sharing grant expiry (default 15 minutes)
- Application-level **audit log** (admin-only view)

### Final Phase — PDF Patient Reports
- On-demand **patient summary PDF** generated with ReportLab
- Secure branding, demographics, medical history, prototype disclaimer
- Page numbers in footer
- Same RBAC as patient detail (Admin, assigned Doctor, own Patient; Management denied)
- Never stored publicly — generated in memory and returned as download
- Audit logged on every generation attempt

---

## Excluded Features (Not Implemented)

The following are explicitly **not implemented** and should not be claimed as completed:

- Real email or SMS delivery (OTPs appear on screen only)
- End-to-end encryption
- Tamper-proof or immutable audit logs
- HIPAA or regulatory compliance
- Production secrets management
- Face recognition or biometric authentication
- Emergency access workflows
- Consent management
- External cloud services, Docker, Celery, Redis, PostgreSQL
- REST API

---

## Installation

### 1. Prerequisites

- Python 3.12 or later
- `git`

### 2. Clone the repository

```bash
git clone https://github.com/Anurag7645/patient_data_security.git
cd patient_data_security
```

### 3. Create and activate a virtual environment

```bash
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
```

### 4. Install dependencies

```bash
pip install -r requirements.txt
```

Dependencies installed:

- `Django==5.2`
- `whitenoise==6.9.0`
- `reportlab==4.2.5`
- `pillow>=9.0.0`
- `chardet>=3.0.0`

### 5. Apply database migrations

```bash
python manage.py migrate
```

### 6. Seed fictional demo data

```bash
python manage.py seed_demo
```

This creates repeatable fictional accounts and patient records. Safe to rerun.

### 7. Collect static files

```bash
python manage.py collectstatic --noinput
```

### 8. Start the development server

```bash
python manage.py runserver
```

Open **http://127.0.0.1:8000/** in your browser.

---

## Demo Accounts

All accounts use **mock OTP authentication** — no real email is sent.

| Email                              | Role       | Notes                        |
|------------------------------------|------------|------------------------------|
| `admin@securehealth.demo`          | Admin      | Full access                  |
| `doctor1@securehealth.demo`        | Doctor     | Assigned: Patient 1 & 2      |
| `doctor2@securehealth.demo`        | Doctor     | Assigned: Patient 3 & 4      |
| `management@securehealth.demo`     | Management | Read-only; no medical docs   |
| `patient1@securehealth.demo`       | Patient    | Chris Blake (SH-P-0001)      |
| `patient2@securehealth.demo`       | Patient    | Taylor Ford (SH-P-0002)      |
| `patient3@securehealth.demo`       | Patient    | Morgan Hayes (SH-P-0003)     |
| `patient4@securehealth.demo`       | Patient    | Jamie Ward (SH-P-0004)       |

### OTP Demonstration Procedure

1. Go to **http://127.0.0.1:8000/login/**
2. Enter a demo email address and click **Send OTP**.
3. The page shows a clearly labelled **"DEMO OTP"** panel with the 6-digit code.
4. Copy the code and click **Verify OTP**.
5. On success you are redirected to the role-specific dashboard.

OTPs expire after **5 minutes** and are single-use. Up to **5 attempts** are allowed before the token is locked.

---

## PDF Report Generation

1. Log in as Admin, an assigned Doctor, or a Patient.
2. Navigate to any accessible patient's detail page.
3. Click the **"Generate PDF Report"** button (red outline, PDF icon).
4. The browser downloads `report_<patient_id>.pdf`.

Management role and unauthenticated users receive a denial. All generation attempts are recorded in the audit log.

---

## Automated Tests

```bash
python manage.py test core --verbosity=2
```

**Actual test results (last run):**

```
Ran 73 tests in ~1.0s
OK
```

Test classes:

| Class | Tests | What is covered |
|---|---|---|
| `OTPModelTests` | 7 | Token generation, verification, expiry, reuse, attempt limit |
| `LoginViewTests` | 4 | Login page, unknown email, OTP panel, session |
| `VerifyViewTests` | 6 | Correct/wrong/expired/reused OTP, attempt limit |
| `DashboardRBACTests` | 5 | All four role dashboards + unauthenticated |
| `PatientListRBACTests` | 5 | List access per role |
| `PatientDetailRBACTests` | 8 | Detail access per role, 404 |
| `DocumentUploadTests` | 7 | Upload auth, file validation, size limit |
| `DocumentAccessAndDownloadTests` | 5 | List + download per role |
| `OTPProtectedSharingTests` | 5 | Grant creation, OTP verify, expired grant, intruder |
| `AuditLogTests` | 3 | Admin access, non-admin denial, filtering |
| `IntegrationAndStartupTests` | 3 | Imports, URL reversal, form validation |
| `PatientPDFReportTests` | 12 | Admin/doctor/patient access, denial, content-type, filename, PDF content, empty fields, audit |

---

## Security Notes

| Control | Status |
|---|---|
| CSRF protection | ✅ Enabled for all state-changing forms |
| Session authentication | ✅ Django session middleware |
| OTP hashing | ✅ SHA-256; plaintext never stored |
| Role enforcement | ✅ Server-side in every view |
| Private file storage | ✅ `media_private/`; never served via static URL |
| File validation | ✅ Extension + magic-byte header checks |
| Upload size limit | ✅ 5 MB |
| Audit logging | ✅ All key actions logged; no secrets in logs |
| `SECRET_KEY` | ⚠ Hardcoded development key — **replace before any deployment** |
| `DEBUG = True` | ⚠ Development mode — **set `False` in production** |
| `ALLOWED_HOSTS` | ⚠ `localhost` only — **restrict in production** |
| Audit log integrity | ⚠ Application-level only — **not tamper-proof** |
| Encryption at rest | ❌ Not implemented |
| TLS/HTTPS | ❌ Not configured (use a reverse proxy in production) |

---

## Project Structure

```
patient_data_sec/
├── core/
│   ├── forms.py                  # DocumentUploadForm, ShareDocumentForm
│   ├── models.py                 # UserProfile, OTPToken, PatientProfile,
│   │                             #   MedicalDocument, SharingGrant, AuditLog
│   ├── views.py                  # All views including generate_patient_report
│   ├── urls.py                   # All URL patterns
│   ├── tests.py                  # 73 automated tests
│   ├── admin.py
│   ├── templatetags/core_tags.py
│   └── management/commands/
│       └── seed_demo.py          # Idempotent demo data seeder
├── secure_health/
│   ├── settings.py
│   └── urls.py
├── templates/
│   ├── base.html
│   └── core/                     # home, login, verify, dashboard,
│                                 #   patient_list, patient_detail,
│                                 #   document_list, document_upload,
│                                 #   share_document, share_verify, audit_log
├── static/css/main.css
├── media_private/                # Private uploads (gitignored)
├── staticfiles/                  # collectstatic output (gitignored)
├── db.sqlite3                    # SQLite database (gitignored)
├── requirements.txt
├── .gitignore
└── README.md
```
