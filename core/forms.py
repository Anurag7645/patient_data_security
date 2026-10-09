"""
Forms for the core app – Phase 3.

DocumentUploadForm  – validates file type, size, and doc_type.
ShareDocumentForm   – doctor selects a registered recipient for OTP-sharing.
"""

import os

from django import forms
from django.conf import settings
from django.contrib.auth.models import User

from .models import DOC_TYPE_CHOICES, MedicalDocument


# ── Document upload ───────────────────────────────────────────────────────────

class DocumentUploadForm(forms.Form):
    display_name = forms.CharField(
        max_length=255,
        label="Document Name",
        help_text="A short descriptive name, e.g. 'Blood Panel – Oct 2026'.",
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Enter document name"}),
    )
    doc_type = forms.ChoiceField(
        choices=DOC_TYPE_CHOICES,
        label="Document Type",
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    file = forms.FileField(
        label="File (PDF, JPG, PNG — max 5 MB)",
        widget=forms.FileInput(attrs={"class": "form-control", "accept": ".pdf,.jpg,.jpeg,.png"}),
    )

    def clean_file(self):
        f = self.cleaned_data.get("file")
        if not f:
            return f

        # ── Size check ────────────────────────────────────────────────────────
        max_bytes = getattr(settings, "MAX_UPLOAD_BYTES", 5 * 1024 * 1024)
        if f.size > max_bytes:
            raise forms.ValidationError(
                f"File too large ({f.size // 1024} KB). Maximum is {max_bytes // 1024 // 1024} MB."
            )

        # ── Extension check ───────────────────────────────────────────────────
        allowed = getattr(settings, "ALLOWED_DOC_TYPES", ["pdf", "jpg", "jpeg", "png"])
        ext = os.path.splitext(f.name)[1].lstrip(".").lower()
        if ext not in allowed:
            raise forms.ValidationError(
                f"File type '.{ext}' is not allowed. Accepted: {', '.join(allowed)}."
            )

        # ── Magic-byte / content inspection ───────────────────────────────────
        header = f.read(8)
        f.seek(0)
        if ext == "pdf":
            if not header.startswith(b"%PDF"):
                raise forms.ValidationError("File does not appear to be a valid PDF.")
        elif ext in ("jpg", "jpeg"):
            if not header[:2] == b"\xff\xd8":
                raise forms.ValidationError("File does not appear to be a valid JPEG.")
        elif ext == "png":
            if not header[:8] == b"\x89PNG\r\n\x1a\n":
                raise forms.ValidationError("File does not appear to be a valid PNG.")

        return f


# ── Sharing ───────────────────────────────────────────────────────────────────

class ShareDocumentForm(forms.Form):
    recipient_email = forms.EmailField(
        label="Recipient Email",
        help_text="Email of the registered user who should receive access.",
        widget=forms.EmailInput(attrs={
            "class": "form-control",
            "placeholder": "recipient@securehealth.demo",
        }),
    )

    def clean_recipient_email(self):
        email = self.cleaned_data.get("recipient_email", "").strip().lower()
        try:
            user = User.objects.get(email__iexact=email)
        except User.DoesNotExist:
            raise forms.ValidationError("No registered user found with that email address.")
        self._recipient_user = user
        return email

    def get_recipient(self) -> User:
        return getattr(self, "_recipient_user", None)
