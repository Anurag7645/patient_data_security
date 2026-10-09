"""
Models for the core app – Phase 2.

Three models extend the built-in Django User:
  UserProfile  – stores the role (admin / doctor / management / patient).
  OTPToken     – single-use, time-limited OTP for mock authentication.
  PatientProfile – full patient record; links a User (role=patient) to their
                   medical details and an assigned Doctor user.
"""

import hashlib
import secrets
from datetime import timedelta

from django.contrib.auth.models import User
from django.db import models
from django.utils import timezone


# ── Role choices ──────────────────────────────────────────────────────────────

class Role(models.TextChoices):
    ADMIN      = "admin",      "Admin"
    DOCTOR     = "doctor",     "Doctor"
    MANAGEMENT = "management", "Management"
    PATIENT    = "patient",    "Patient"


# ── User profile ──────────────────────────────────────────────────────────────

class UserProfile(models.Model):
    """One-to-one extension of Django's User model that stores the role."""

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.PATIENT)

    class Meta:
        verbose_name = "User Profile"

    def __str__(self):
        return f"{self.user.username} ({self.get_role_display()})"

    # Convenience helpers
    @property
    def is_admin(self):
        return self.role == Role.ADMIN

    @property
    def is_doctor(self):
        return self.role == Role.DOCTOR

    @property
    def is_management(self):
        return self.role == Role.MANAGEMENT

    @property
    def is_patient(self):
        return self.role == Role.PATIENT


# ── OTP token ─────────────────────────────────────────────────────────────────

OTP_EXPIRY_MINUTES  = 5
OTP_MAX_ATTEMPTS    = 5


class OTPToken(models.Model):
    """
    Mock OTP for demonstration purposes.

    The six-digit code is stored as a SHA-256 hash (not plaintext).
    Each user may have at most one active token at a time;
    requesting a new OTP invalidates the previous one.
    """

    # Expose constants as class attributes so tests can reference them
    OTP_MAX_ATTEMPTS   = OTP_MAX_ATTEMPTS
    OTP_EXPIRY_MINUTES = OTP_EXPIRY_MINUTES

    user        = models.ForeignKey(User, on_delete=models.CASCADE, related_name="otp_tokens")
    code_hash   = models.CharField(max_length=64)          # SHA-256 hex
    created_at  = models.DateTimeField(auto_now_add=True)
    expires_at  = models.DateTimeField()
    used        = models.BooleanField(default=False)
    attempts    = models.PositiveSmallIntegerField(default=0)

    class Meta:
        verbose_name = "OTP Token"
        ordering = ["-created_at"]

    def __str__(self):
        return f"OTP for {self.user.username} (used={self.used})"

    # ── Class-level helpers ───────────────────────────────────────────────────

    @classmethod
    def _hash(cls, code: str) -> str:
        return hashlib.sha256(code.encode()).hexdigest()

    @classmethod
    def generate_for(cls, user: User) -> tuple["OTPToken", str]:
        """
        Invalidate any previous tokens for *user*, create a new one,
        and return (token_instance, plaintext_code).
        """
        # Invalidate old tokens
        cls.objects.filter(user=user, used=False).update(used=True)

        plaintext = f"{secrets.randbelow(900000) + 100000:06d}"
        token = cls.objects.create(
            user       = user,
            code_hash  = cls._hash(plaintext),
            expires_at = timezone.now() + timedelta(minutes=OTP_EXPIRY_MINUTES),
        )
        return token, plaintext

    # ── Instance helpers ──────────────────────────────────────────────────────

    @property
    def is_expired(self) -> bool:
        return timezone.now() > self.expires_at

    @property
    def attempts_exceeded(self) -> bool:
        return self.attempts >= OTP_MAX_ATTEMPTS

    def verify(self, code: str) -> bool:
        """
        Check *code* against stored hash.
        Increments attempt counter regardless of outcome.
        Returns True only on correct, unexpired, unused, within-attempt-limit code.
        """
        if self.used or self.is_expired or self.attempts_exceeded:
            return False
        self.attempts += 1
        correct = self.code_hash == self._hash(code)
        if correct:
            self.used = True
        self.save(update_fields=["attempts", "used"])
        return correct


# ── Patient profile ───────────────────────────────────────────────────────────

BLOOD_GROUPS = [
    ("A+","A+"), ("A-","A-"),
    ("B+","B+"), ("B-","B-"),
    ("AB+","AB+"), ("AB-","AB-"),
    ("O+","O+"), ("O-","O-"),
]

GENDER_CHOICES = [
    ("M", "Male"),
    ("F", "Female"),
    ("O", "Other"),
    ("U", "Prefer not to say"),
]


class PatientProfile(models.Model):
    """Full medical record for a patient user."""

    # Identity
    patient_user    = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name="patient_profile",
        limit_choices_to={"profile__role": Role.PATIENT},
    )
    patient_id      = models.CharField(max_length=20, unique=True)
    date_of_birth   = models.DateField()
    gender          = models.CharField(max_length=1, choices=GENDER_CHOICES)
    blood_group     = models.CharField(max_length=4, choices=BLOOD_GROUPS)

    # Contact
    phone           = models.CharField(max_length=20, blank=True)
    address         = models.TextField(blank=True)

    # Medical
    allergies           = models.TextField(blank=True, help_text="Comma-separated list of known allergies.")
    medical_history     = models.TextField(blank=True)
    current_medications = models.TextField(blank=True, help_text="Comma-separated list of current medications.")

    # Doctor assignment
    assigned_doctor = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="assigned_patients",
        limit_choices_to={"profile__role": Role.DOCTOR},
    )

    created_at  = models.DateTimeField(auto_now_add=True)
    updated_at  = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Patient Profile"
        ordering = ["patient_id"]

    def __str__(self):
        return f"{self.patient_id} – {self.patient_user.get_full_name() or self.patient_user.username}"

    @property
    def full_name(self):
        return self.patient_user.get_full_name() or self.patient_user.username

    @property
    def age(self):
        from datetime import date
        today = date.today()
        dob = self.date_of_birth
        return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
