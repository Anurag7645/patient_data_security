"""
Management command: seed_demo

Creates repeatable fictional demonstration data.
Safe to rerun – existing users, patient records, and documents are not duplicated.

Usage:
    python manage.py seed_demo
"""

import io
import os
from datetime import date

from django.contrib.auth.models import User
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand

from core.models import MedicalDocument, OTPToken, PatientProfile, Role, UserProfile


# ─────────────────────────────────────────────────────────────────────────────
# Demo accounts
# ─────────────────────────────────────────────────────────────────────────────

DEMO_USERS = [
    # (username, email, first_name, last_name, role, is_staff, is_superuser)
    ("admin_sh",      "admin@securehealth.demo",      "Alex",    "Morgan",  Role.ADMIN,      True,  True),
    ("dr_carter",     "doctor1@securehealth.demo",    "Dr. Sam", "Carter",  Role.DOCTOR,     False, False),
    ("dr_patel",      "doctor2@securehealth.demo",    "Dr. Ria", "Patel",   Role.DOCTOR,     False, False),
    ("mgmt_chen",     "management@securehealth.demo", "Jordan",  "Chen",    Role.MANAGEMENT, False, False),
    ("patient_blake", "patient1@securehealth.demo",   "Chris",   "Blake",   Role.PATIENT,    False, False),
    ("patient_ford",  "patient2@securehealth.demo",   "Taylor",  "Ford",    Role.PATIENT,    False, False),
    ("patient_hayes", "patient3@securehealth.demo",   "Morgan",  "Hayes",   Role.PATIENT,    False, False),
    ("patient_ward",  "patient4@securehealth.demo",   "Jamie",   "Ward",    Role.PATIENT,    False, False),
]

# ─────────────────────────────────────────────────────────────────────────────
# Patient records
# ─────────────────────────────────────────────────────────────────────────────
# (username, patient_id, dob, gender, blood_group, phone, address,
#  allergies, medical_history, medications, assigned_doctor_username)

DEMO_PATIENTS = [
    (
        "patient_blake", "SH-P-0001",
        date(1985, 4, 12), "M", "O+",
        "+44 7700 000001",
        "12 Elmwood Avenue, London, EC1A 1BB",
        "Penicillin, Sulfa drugs",
        "Appendectomy (2010). Hypertension diagnosed 2018.",
        "Amlodipine 5mg daily, Lisinopril 10mg daily",
        "dr_carter",
    ),
    (
        "patient_ford", "SH-P-0002",
        date(1992, 9, 3), "F", "A+",
        "+44 7700 000002",
        "7 Birch Lane, Manchester, M1 2WD",
        "None known",
        "Type 2 diabetes diagnosed 2020. No surgical history.",
        "Metformin 500mg twice daily",
        "dr_carter",
    ),
    (
        "patient_hayes", "SH-P-0003",
        date(1978, 1, 27), "F", "B-",
        "+44 7700 000003",
        "3 Cedar Road, Birmingham, B1 1BB",
        "Aspirin",
        "Asthma (childhood). Mild depression managed since 2015.",
        "Salbutamol inhaler PRN, Sertraline 50mg daily",
        "dr_patel",
    ),
    (
        "patient_ward", "SH-P-0004",
        date(2001, 6, 18), "M", "AB+",
        "+44 7700 000004",
        "22 Poplar Street, Leeds, LS1 1BA",
        "Latex, Ibuprofen",
        "Fractured right wrist (2019). No chronic conditions.",
        "None",
        "dr_patel",
    ),
]


# ─────────────────────────────────────────────────────────────────────────────
# Demo documents – minimal valid PDF bytes (fictional, not real medical data)
# ─────────────────────────────────────────────────────────────────────────────

def _minimal_pdf(title: str) -> bytes:
    """Returns the smallest valid PDF that renders a title line."""
    body = (
        "%PDF-1.4\n"
        "1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
        "2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
        "3 0 obj<</Type/Page/MediaBox[0 0 612 792]/Parent 2 0 R"
        "/Contents 4 0 R/Resources<</Font<</F1<</Type/Font"
        "/Subtype/Type1/BaseFont/Helvetica>>>>>>>>>>endobj\n"
    )
    stream = f"BT /F1 14 Tf 72 720 Td ({title} - FICTIONAL DEMO DATA) Tj ET"
    body += (
        f"4 0 obj<</Length {len(stream)}>>\nstream\n{stream}\nendstream endobj\n"
        "xref\n0 5\n0000000000 65535 f \n"
        "trailer<</Size 5/Root 1 0 R>>\nstartxref\n0\n%%EOF\n"
    )
    return body.encode()


DEMO_DOCUMENTS = [
    # (patient_username, doctor_username, display_name, doc_type)
    ("patient_blake", "dr_carter", "Blood Panel Oct 2026 - DEMO",    "lab_result"),
    ("patient_blake", "dr_carter", "Hypertension Prescription - DEMO","prescription"),
    ("patient_ford",  "dr_carter", "HbA1c Result Oct 2026 - DEMO",   "lab_result"),
    ("patient_hayes", "dr_patel",  "Asthma Referral Letter - DEMO",  "referral"),
]


# ─────────────────────────────────────────────────────────────────────────────

class Command(BaseCommand):
    help = "Seed fictional demonstration data for Secure Health Phase 2 + 3."

    def handle(self, *args, **options):
        self.stdout.write(self.style.MIGRATE_HEADING("Seeding demo data…"))

        created_users: dict[str, User] = {}

        # ── Create / update users ─────────────────────────────────────────
        for username, email, first, last, role, is_staff, is_superuser in DEMO_USERS:
            user, created = User.objects.get_or_create(
                username=username,
                defaults={
                    "email":        email,
                    "first_name":   first,
                    "last_name":    last,
                    "is_staff":     is_staff,
                    "is_superuser": is_superuser,
                },
            )
            if created:
                user.set_unusable_password()
                user.save()
                self.stdout.write(f"  Created user: {username} ({email})")
            else:
                updated = False
                for field, val in [("email", email), ("first_name", first), ("last_name", last)]:
                    if getattr(user, field) != val:
                        setattr(user, field, val)
                        updated = True
                if updated:
                    user.save()
                self.stdout.write(f"  Exists  user: {username}")

            _profile, _p_created = UserProfile.objects.get_or_create(
                user=user, defaults={"role": role},
            )
            if not _p_created and _profile.role != role:
                _profile.role = role
                _profile.save()

            created_users[username] = user

        # ── Create patient profiles ───────────────────────────────────────
        created_patients: dict[str, PatientProfile] = {}
        for (
            username, patient_id, dob, gender, blood_group,
            phone, address, allergies, history, meds, doctor_username
        ) in DEMO_PATIENTS:
            patient_user = created_users[username]
            doctor_user  = created_users[doctor_username]

            _pp, _pp_created = PatientProfile.objects.get_or_create(
                patient_user=patient_user,
                defaults={
                    "patient_id":           patient_id,
                    "date_of_birth":        dob,
                    "gender":               gender,
                    "blood_group":          blood_group,
                    "phone":                phone,
                    "address":              address,
                    "allergies":            allergies,
                    "medical_history":      history,
                    "current_medications":  meds,
                    "assigned_doctor":      doctor_user,
                },
            )
            status = "Created" if _pp_created else "Exists "
            self.stdout.write(f"  {status} patient: {patient_id} ({username})")
            created_patients[username] = _pp

        # ── Create demo documents ─────────────────────────────────────────
        self.stdout.write("  Seeding demo documents…")
        for pat_username, doc_username, display_name, doc_type in DEMO_DOCUMENTS:
            profile = created_patients.get(pat_username)
            uploader = created_users.get(doc_username)
            if not profile or not uploader:
                continue

            # Only create if a doc with this display_name doesn't already exist
            if MedicalDocument.objects.filter(patient=profile, display_name=display_name).exists():
                self.stdout.write(f"    Exists  doc: {display_name}")
                continue

            pdf_bytes = _minimal_pdf(display_name)
            doc = MedicalDocument(
                patient=profile,
                uploaded_by=uploader,
                display_name=display_name,
                doc_type=doc_type,
                file_size_bytes=len(pdf_bytes),
            )
            safe_name = f"demo_{display_name[:20].replace(' ', '_').lower()}.pdf"
            doc.stored_file.save(safe_name, ContentFile(pdf_bytes), save=True)
            self.stdout.write(f"    Created doc: {display_name}")

        self.stdout.write(self.style.SUCCESS("\nDemo data ready.\n"))
        self.stdout.write("Demo accounts (use email + OTP at /login/):")
        self.stdout.write("  admin@securehealth.demo        → Admin")
        self.stdout.write("  doctor1@securehealth.demo      → Doctor (2 patients)")
        self.stdout.write("  doctor2@securehealth.demo      → Doctor (2 patients)")
        self.stdout.write("  management@securehealth.demo   → Management")
        self.stdout.write("  patient1@securehealth.demo     → Patient (Chris Blake)")
        self.stdout.write("  patient2@securehealth.demo     → Patient (Taylor Ford)")
        self.stdout.write("  patient3@securehealth.demo     → Patient (Morgan Hayes)")
        self.stdout.write("  patient4@securehealth.demo     → Patient (Jamie Ward)")
