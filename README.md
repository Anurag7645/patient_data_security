# Secure Health – Phase 3

**Cybersecurity Framework for Secure Patient Data Transmission in Healthcare Networks**

A research-review Django prototype demonstrating:
- Mock OTP authentication (email-based, single-use, 5-minute expiry, hashed storage)
- Four user roles (`Admin`, `Doctor`, `Management`, `Patient`) with strict RBAC
- Patient medical records and doctor-patient assignments
- Secure medical document uploads (PDF, JPG, PNG; max 5 MB; magic-byte validation; stored in private media directory outside public static)
- OTP-protected document sharing workflow with expiry and recipient authorization
- Application-level audit logging tracking authentication, document access, and unauthorized attempts

> **Research prototype only.** Not for clinical use. No real patient data. OTP codes are shown on-screen in demo panels for local testing.

---

## Tech Stack

| Layer     | Technology                          |
|-----------|-------------------------------------|
| Language  | Python 3 (3.10+ compatible)         |
| Framework | Django 5.2                          |
| Database  | SQLite (built-in)                   |
| Frontend  | Django Templates, Bootstrap 5, Bootstrap Icons |
| Static    | WhiteNoise                          |
| Security  | Python `secrets` + `hashlib` (standard library, zero extra dependencies) |

---

## Project Structure

```
patient_data_sec/
├── core/
│   ├── management/
│   │   └── commands/
│   │       └── seed_demo.py       # Repeatable demo data seeder
│   ├── migrations/                # Schema migrations (0001_initial, 0002_auditlog_...)
│   ├── templatetags/
│   │   └── core_tags.py           # get_role template filter
│   ├── admin.py                   # Admin registrations for all models
│   ├── apps.py
│   ├── forms.py                   # DocumentUploadForm, ShareDocumentForm
│   ├── models.py                  # UserProfile, OTPToken, PatientProfile, MedicalDocument, SharingGrant, AuditLog
│   ├── tests.py                   # 58 automated tests
│   ├── urls.py                    # Core routing
│   └── views.py                   # Auth, RBAC, Document management, Sharing, Audit
├── media_private/                 # Private document repository (not exposed to static)
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
│       ├── patient_list.html      # Patient listing
│       ├── patient_detail.html    # Patient detail view
│       ├── document_list.html     # Medical document list
│       ├── document_upload.html   # Secure upload form
│       ├── share_document.html    # OTP-protected sharing creation
│       ├── share_verify.html      # Recipient OTP verification
│       └── audit_log.html         # Admin audit log viewer
├── manage.py
├── requirements.txt
└── .gitignore
```

---

## Installation & Startup

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

# 5. Seed fictional demo data and sample documents
python manage.py seed_demo

# 6. Start the development server
python manage.py runserver
```

Open **http://127.0.0.1:8000/**

---

## Demo Accounts

All demo accounts use `@securehealth.demo` emails. Passwords are disabled — sign in using mock OTP.

| Email | Role | Access Scope |
|---|---|---|
| `admin@securehealth.demo` | Admin | Full user list, all patients, all documents, audit log, Django admin |
| `doctor1@securehealth.demo` | Doctor | Assigned patients (Chris Blake, Taylor Ford), upload/share documents |
| `doctor2@securehealth.demo` | Doctor | Assigned patients (Morgan Hayes, Jamie Ward), upload/share documents |
| `management@securehealth.demo` | Management | Patient list (demographics only; no medical records, no documents) |
| `patient1@securehealth.demo` | Patient | Own record & own documents only (Chris Blake – SH-P-0001) |
| `patient2@securehealth.demo` | Patient | Own record & own documents only (Taylor Ford – SH-P-0002) |
| `patient3@securehealth.demo` | Patient | Own record & own documents only (Morgan Hayes – SH-P-0003) |
| `patient4@securehealth.demo` | Patient | Own record & own documents only (Jamie Ward – SH-P-0004) |

---

## Key Workflows

### 1. Mock OTP Authentication
- Go to `/login/`, enter any demo email above.
- A **MOCK OTP AUTHENTICATION** panel displays the generated 6-digit code.
- Submit the code to establish an authenticated session.
- Codes expire in 5 minutes, are single-use, hashed with SHA-256 in SQLite, and enforce a 5-attempt limit.

### 2. Medical Document Uploads
- Accessible via `/patients/<id>/documents/upload/` by Admin or the patient's assigned Doctor.
- Supports PDF, JPG, and PNG files up to 5 MB with header content (magic-byte) inspection.
- Files are saved to `media_private/` with randomized UUID filenames.
- Downloads are routed through `/documents/<id>/download/` which checks authorization on every request.

### 3. OTP-Protected Document Sharing
- An authorized Doctor can share a document from `/patients/<id>/documents/` by clicking Share.
- The sender enters the registered recipient's email.
- A `SharingGrant` is generated along with a mock OTP for the recipient (valid for 15 minutes).
- The recipient navigates to `/share/<grant_id>/verify/` and verifies using the code.
- Once verified, the recipient can download the document at `/share/<grant_id>/download/`.
- Access is strictly denied to unauthorized users or upon grant expiration.

### 4. Basic Audit Logging
- Administrators can visit `/audit/` or access it from the dashboard.
- Displays events chronologically (newest first) with filters for action and outcome (`success`, `denied`, `failed`, `info`).
- Captures login attempts, patient record views, uploads, downloads, sharing grants, and access violations.

---

## Route Overview

| URL | Access | Purpose |
|---|---|---|
| `/` | Public | Landing page |
| `/login/` | Public | Step 1: Email entry |
| `/verify/` | Session | Step 2: OTP verification |
| `/logout/` | Authenticated | Terminate session |
| `/dashboard/` | Authenticated | Role-tailored dashboard |
| `/patients/` | Admin, Doctor, Management | Patient directory |
| `/patients/<id>/` | RBAC-enforced | Patient demographics & records |
| `/patients/<id>/documents/` | Admin, Doctor (assigned), Patient (own) | Medical documents listing |
| `/patients/<id>/documents/upload/` | Admin, Doctor (assigned) | Document upload form |
| `/documents/<id>/download/` | RBAC-enforced | Private document download |
| `/documents/<id>/share/` | Admin, Doctor (assigned) | Create sharing grant |
| `/share/<grant_id>/verify/` | Designated recipient | OTP verification for sharing |
| `/share/<grant_id>/download/` | Verified recipient | Download shared document |
| `/audit/` | Admin only | System audit log |
| `/admin/` | Admin | Django admin interface |

---

## Running Tests

```bash
python manage.py test core --verbosity=2
```

**58 tests, 0 failures** verifying:
- Mock OTP generation, hashing, verification, expiry, and attempt limits
- RBAC permissions for Admin, Doctor, Management, and Patient
- Cross-patient and unassigned doctor access rejections
- File upload validations (size, extension, magic bytes)
- Private document download authorizations
- OTP-protected sharing grants (recipient identity check, verification, expiration)
- Audit log record generation and admin-only viewing permissions
