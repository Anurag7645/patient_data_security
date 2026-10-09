"""
Management command: seed_demo

Creates repeatable fictional demonstration data.
Safe to rerun – existing users and patient records are not duplicated.

Usage:
    python manage.py seed_demo
"""

from datetime import date

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand

from core.models import OTPToken, PatientProfile, Role, UserProfile


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

class Command(BaseCommand):
    help = "Seed fictional demonstration data for Secure Health Phase 2."

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
                # Set an unusable password – login is OTP-only
                user.set_unusable_password()
                user.save()
                self.stdout.write(f"  Created user: {username} ({email})")
            else:
                # Ensure email and names are up to date on reruns
                updated = False
                for field, val in [("email", email), ("first_name", first), ("last_name", last)]:
                    if getattr(user, field) != val:
                        setattr(user, field, val)
                        updated = True
                if updated:
                    user.save()
                self.stdout.write(f"  Exists  user: {username}")

            # ── UserProfile ────────────────────────────────────────────────
            _profile, _p_created = UserProfile.objects.get_or_create(
                user=user,
                defaults={"role": role},
            )
            if not _p_created and _profile.role != role:
                _profile.role = role
                _profile.save()

            created_users[username] = user

        # ── Create patient profiles ───────────────────────────────────────
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
