"""
Views for the core app – Phase 2 + Phase 3.

Authentication flow
───────────────────
  /login/   – Step 1: user enters registered demo email → OTP generated & shown
  /verify/  – Step 2: user enters the six-digit code → session established
  /logout/  – Clears session

Role-based pages (Phase 2)
────────────────
  /dashboard/        – role-specific overview (all authenticated users)
  /patients/         – patient list  (admin, doctor, management)
  /patients/<id>/    – patient detail with RBAC enforcement

Document management (Phase 3)
──────────────────────────────
  /patients/<id>/documents/          – document list for a patient
  /patients/<id>/documents/upload/   – upload form (admin, doctor-assigned)
  /documents/<doc_id>/download/      – authenticated private download
  /documents/<doc_id>/share/         – create sharing grant (doctor)
  /share/<grant_id>/verify/          – recipient OTP verification
  /share/<grant_id>/download/        – shared document download (verified only)

Audit (Phase 3)
───────────────
  /audit/   – audit log page (admin only)
"""

import mimetypes
import os

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.models import User
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .forms import DocumentUploadForm, ShareDocumentForm
from .models import (
    AuditLog, AuditOutcome,
    MedicalDocument, OTPToken,
    PatientProfile, Role,
    SharingGrant, UserProfile,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _require_auth(request):
    """Return a redirect if the user is not authenticated, else None."""
    if not request.user.is_authenticated:
        return redirect("core:login")
    return None


def _get_role(user) -> str:
    try:
        return user.profile.role
    except UserProfile.DoesNotExist:
        return ""


def _can_access_patient(role, user, profile) -> bool:
    """True if the role/user combination is allowed to see this patient."""
    if role == Role.ADMIN:
        return True
    if role == Role.DOCTOR:
        return profile.assigned_doctor == user
    if role == Role.PATIENT:
        try:
            return user.patient_profile.pk == profile.pk
        except PatientProfile.DoesNotExist:
            return False
    return False   # management, unknown


# ── Public pages ──────────────────────────────────────────────────────────────

def home(request):
    """Public landing page."""
    return render(request, "core/home.html")


# ── OTP Authentication ────────────────────────────────────────────────────────

def login_view(request):
    """
    Step 1 – Email entry.
    Generates a mock OTP and renders it in a clearly labelled demo panel.
    """
    if request.user.is_authenticated:
        return redirect("core:dashboard")

    otp_plaintext = None

    if request.method == "POST":
        email = request.POST.get("email", "").strip().lower()

        try:
            user = User.objects.get(email__iexact=email)
        except User.DoesNotExist:
            AuditLog.log(action="otp_request", outcome=AuditOutcome.FAILED,
                         reason=f"Unknown email: {email}")
            messages.error(request, "No demo account found for that email address.")
            return render(request, "core/login.html")

        _token, otp_plaintext = OTPToken.generate_for(user)
        AuditLog.log(action="otp_request", outcome=AuditOutcome.INFO,
                     user=user, resource_type="User", resource_id=user.pk,
                     reason="OTP generated")

        request.session["otp_user_id"] = user.pk
        request.session["otp_email"]   = email

    return render(request, "core/login.html", {"otp_plaintext": otp_plaintext})


def verify_view(request):
    """Step 2 – OTP entry and verification."""
    if request.user.is_authenticated:
        return redirect("core:dashboard")

    user_id = request.session.get("otp_user_id")
    email   = request.session.get("otp_email", "")

    if not user_id:
        messages.error(request, "Please enter your email first.")
        return redirect("core:login")

    try:
        user = User.objects.get(pk=user_id)
    except User.DoesNotExist:
        messages.error(request, "Session expired. Please try again.")
        return redirect("core:login")

    if request.method == "POST":
        code = request.POST.get("otp_code", "").strip()

        token = (
            OTPToken.objects
            .filter(user=user, used=False)
            .order_by("-created_at")
            .first()
        )

        if token is None:
            AuditLog.log(action="otp_verify", outcome=AuditOutcome.FAILED,
                         user=user, resource_type="User", resource_id=user.pk,
                         reason="No active token")
            messages.error(request, "No active OTP found. Please request a new code.")
            return redirect("core:login")

        if token.is_expired:
            AuditLog.log(action="otp_verify", outcome=AuditOutcome.FAILED,
                         user=user, resource_type="User", resource_id=user.pk,
                         reason="Token expired")
            messages.error(request, "Your OTP has expired. Please request a new code.")
            return redirect("core:login")

        if token.attempts_exceeded:
            AuditLog.log(action="otp_verify", outcome=AuditOutcome.DENIED,
                         user=user, resource_type="User", resource_id=user.pk,
                         reason="Attempt limit reached")
            messages.error(request, "Too many failed attempts. Please request a new code.")
            return redirect("core:login")

        if token.verify(code):
            request.session.pop("otp_user_id", None)
            request.session.pop("otp_email",   None)
            login(request, user)
            AuditLog.log(action="otp_verify", outcome=AuditOutcome.SUCCESS,
                         user=user, resource_type="User", resource_id=user.pk)
            messages.success(request, f"Welcome, {user.get_full_name() or user.username}!")
            return redirect("core:dashboard")
        else:
            remaining = OTPToken.OTP_MAX_ATTEMPTS - token.attempts
            AuditLog.log(action="otp_verify", outcome=AuditOutcome.FAILED,
                         user=user, resource_type="User", resource_id=user.pk,
                         reason=f"Wrong code, {remaining} attempts left")
            if remaining <= 0:
                messages.error(request, "Too many failed attempts. Please request a new code.")
                return redirect("core:login")
            messages.error(request, f"Incorrect code. {remaining} attempt(s) remaining.")

    return render(request, "core/verify.html", {"email": email})


def logout_view(request):
    """Logout and redirect to home."""
    logout(request)
    return redirect("core:home")


# ── Dashboard ─────────────────────────────────────────────────────────────────

def dashboard(request):
    """Role-specific dashboard."""
    redir = _require_auth(request)
    if redir:
        return redir

    role = _get_role(request.user)
    ctx  = {"role": role}

    if role == Role.ADMIN:
        ctx["total_users"]    = User.objects.count()
        ctx["total_patients"] = PatientProfile.objects.count()
        ctx["total_doctors"]  = UserProfile.objects.filter(role=Role.DOCTOR).count()
        ctx["recent_users"]   = User.objects.order_by("-date_joined")[:5]
        ctx["total_docs"]     = MedicalDocument.objects.count()

    elif role == Role.DOCTOR:
        ctx["assigned_patients"] = PatientProfile.objects.filter(
            assigned_doctor=request.user
        ).select_related("patient_user")

    elif role == Role.MANAGEMENT:
        ctx["total_patients"] = PatientProfile.objects.count()
        ctx["total_doctors"]  = UserProfile.objects.filter(role=Role.DOCTOR).count()

    elif role == Role.PATIENT:
        try:
            ctx["patient_profile"] = request.user.patient_profile
        except PatientProfile.DoesNotExist:
            ctx["patient_profile"] = None

    return render(request, "core/dashboard.html", ctx)


# ── Patient list ──────────────────────────────────────────────────────────────

def patient_list(request):
    redir = _require_auth(request)
    if redir:
        return redir

    role = _get_role(request.user)

    if role == Role.PATIENT:
        messages.error(request, "You do not have permission to view the patient list.")
        return redirect("core:dashboard")

    if role not in (Role.ADMIN, Role.DOCTOR, Role.MANAGEMENT):
        messages.error(request, "Access denied.")
        return redirect("core:dashboard")

    if role == Role.DOCTOR:
        patients = PatientProfile.objects.filter(
            assigned_doctor=request.user
        ).select_related("patient_user", "assigned_doctor")
    else:
        patients = PatientProfile.objects.all().select_related("patient_user", "assigned_doctor")

    return render(request, "core/patient_list.html", {"patients": patients, "role": role})


# ── Patient detail ────────────────────────────────────────────────────────────

def patient_detail(request, patient_id):
    redir = _require_auth(request)
    if redir:
        return redir

    role    = _get_role(request.user)
    profile = get_object_or_404(PatientProfile, patient_id=patient_id)

    if role == Role.ADMIN:
        pass
    elif role == Role.DOCTOR:
        if profile.assigned_doctor != request.user:
            AuditLog.log(action="patient_access", outcome=AuditOutcome.DENIED,
                         user=request.user, resource_type="PatientProfile",
                         resource_id=patient_id, reason="Doctor not assigned")
            messages.error(request, "You are not authorised to view this patient's record.")
            return redirect("core:patient_list")
    elif role == Role.MANAGEMENT:
        pass
    elif role == Role.PATIENT:
        try:
            own = request.user.patient_profile
        except PatientProfile.DoesNotExist:
            messages.error(request, "No patient record associated with your account.")
            return redirect("core:dashboard")
        if own.pk != profile.pk:
            AuditLog.log(action="patient_access", outcome=AuditOutcome.DENIED,
                         user=request.user, resource_type="PatientProfile",
                         resource_id=patient_id, reason="Patient accessing other record")
            messages.error(request, "You can only view your own record.")
            return redirect("core:dashboard")
    else:
        messages.error(request, "Access denied.")
        return redirect("core:dashboard")

    AuditLog.log(action="patient_access", outcome=AuditOutcome.SUCCESS,
                 user=request.user, resource_type="PatientProfile", resource_id=patient_id)

    return render(request, "core/patient_detail.html", {"profile": profile, "role": role})


# ── Document list ─────────────────────────────────────────────────────────────

def document_list(request, patient_id):
    """
    List documents for a patient.
    Access: admin (any), doctor (assigned only), patient (own only).
    Management: denied.
    """
    redir = _require_auth(request)
    if redir:
        return redir

    role    = _get_role(request.user)
    profile = get_object_or_404(PatientProfile, patient_id=patient_id)

    if role == Role.MANAGEMENT:
        AuditLog.log(action="doc_list", outcome=AuditOutcome.DENIED,
                     user=request.user, resource_type="PatientProfile",
                     resource_id=patient_id, reason="Management role denied")
        messages.error(request, "Management does not have access to medical documents.")
        return redirect("core:patient_detail", patient_id=patient_id)

    if not _can_access_patient(role, request.user, profile):
        AuditLog.log(action="doc_list", outcome=AuditOutcome.DENIED,
                     user=request.user, resource_type="PatientProfile",
                     resource_id=patient_id, reason="RBAC denied")
        messages.error(request, "You are not authorised to view this patient's documents.")
        return redirect("core:dashboard")

    docs = profile.documents.select_related("uploaded_by").all()
    ctx  = {"profile": profile, "docs": docs, "role": role}
    return render(request, "core/document_list.html", ctx)


# ── Document upload ───────────────────────────────────────────────────────────

def document_upload(request, patient_id):
    """
    Upload a document for a patient.
    Access: admin (any), doctor (assigned only).
    """
    redir = _require_auth(request)
    if redir:
        return redir

    role    = _get_role(request.user)
    profile = get_object_or_404(PatientProfile, patient_id=patient_id)

    # Only admin or assigned doctor may upload
    if role == Role.ADMIN:
        pass
    elif role == Role.DOCTOR:
        if profile.assigned_doctor != request.user:
            AuditLog.log(action="doc_upload", outcome=AuditOutcome.DENIED,
                         user=request.user, resource_type="PatientProfile",
                         resource_id=patient_id, reason="Doctor not assigned")
            messages.error(request, "You may only upload documents for your assigned patients.")
            return redirect("core:patient_list")
    else:
        AuditLog.log(action="doc_upload", outcome=AuditOutcome.DENIED,
                     user=request.user, resource_type="PatientProfile",
                     resource_id=patient_id, reason=f"Role {role} not permitted")
        messages.error(request, "You do not have permission to upload documents.")
        return redirect("core:patient_detail", patient_id=patient_id)

    form = DocumentUploadForm(request.POST or None, request.FILES or None)

    if request.method == "POST" and form.is_valid():
        f = form.cleaned_data["file"]
        doc = MedicalDocument(
            patient=profile,
            uploaded_by=request.user,
            display_name=form.cleaned_data["display_name"],
            doc_type=form.cleaned_data["doc_type"],
            file_size_bytes=f.size,
        )
        doc.stored_file = f
        doc.save()

        AuditLog.log(action="doc_upload", outcome=AuditOutcome.SUCCESS,
                     user=request.user, resource_type="MedicalDocument",
                     resource_id=doc.pk,
                     reason=f"Uploaded for patient {patient_id}")
        messages.success(request, f"Document '{doc.display_name}' uploaded successfully.")
        return redirect("core:document_list", patient_id=patient_id)

    ctx = {"profile": profile, "form": form, "role": role}
    return render(request, "core/document_upload.html", ctx)


# ── Document download ─────────────────────────────────────────────────────────

def document_download(request, doc_id):
    """
    Private authenticated download. The file path is NEVER exposed in the URL.
    Access: admin, assigned doctor, or the patient whose record it belongs to.
    Management: always denied.
    """
    redir = _require_auth(request)
    if redir:
        return redir

    role = _get_role(request.user)
    doc  = get_object_or_404(MedicalDocument, pk=doc_id)

    def _deny(reason):
        AuditLog.log(action="doc_download", outcome=AuditOutcome.DENIED,
                     user=request.user, resource_type="MedicalDocument",
                     resource_id=doc_id, reason=reason)
        messages.error(request, "You are not authorised to download this document.")
        return redirect("core:dashboard")

    if role == Role.MANAGEMENT:
        return _deny("Management role denied")
    if not _can_access_patient(role, request.user, doc.patient):
        return _deny("RBAC denied")

    # Serve the file
    file_path = doc.stored_file.path
    if not os.path.exists(file_path):
        raise Http404("Document file not found.")

    AuditLog.log(action="doc_download", outcome=AuditOutcome.SUCCESS,
                 user=request.user, resource_type="MedicalDocument", resource_id=doc_id)

    mime_type, _ = mimetypes.guess_type(file_path)
    response = FileResponse(
        open(file_path, "rb"),
        content_type=mime_type or "application/octet-stream",
        as_attachment=True,
        filename=doc.display_name,
    )
    return response


# ── Share document ────────────────────────────────────────────────────────────

def share_document(request, doc_id):
    """
    Doctor creates an OTP-protected sharing grant for a document.
    DEMO: The mock OTP is shown on-screen so the recipient can verify it.
    """
    redir = _require_auth(request)
    if redir:
        return redir

    role = _get_role(request.user)
    doc  = get_object_or_404(MedicalDocument, pk=doc_id)

    # Only admin or assigned doctor may share
    if role not in (Role.ADMIN, Role.DOCTOR):
        messages.error(request, "Only doctors or admins may share documents.")
        return redirect("core:dashboard")
    if role == Role.DOCTOR and doc.patient.assigned_doctor != request.user:
        AuditLog.log(action="share_create", outcome=AuditOutcome.DENIED,
                     user=request.user, resource_type="MedicalDocument",
                     resource_id=doc_id, reason="Doctor not assigned")
        messages.error(request, "You may only share documents for your assigned patients.")
        return redirect("core:patient_list")

    form = ShareDocumentForm(request.POST or None)
    grant_otp = None

    if request.method == "POST" and form.is_valid():
        recipient = form.get_recipient()

        from datetime import timedelta
        from django.conf import settings as dj_settings
        expiry_minutes = getattr(dj_settings, "SHARING_GRANT_MINUTES", 15)

        # Generate an OTP for the recipient
        otp_token, otp_plaintext = OTPToken.generate_for(recipient)

        grant = SharingGrant.objects.create(
            document=doc,
            created_by=request.user,
            recipient=recipient,
            otp_token=otp_token,
            expires_at=timezone.now() + timedelta(minutes=expiry_minutes),
        )

        AuditLog.log(action="share_create", outcome=AuditOutcome.SUCCESS,
                     user=request.user, resource_type="SharingGrant",
                     resource_id=grant.pk,
                     reason=f"Shared with {recipient.username}")

        grant_otp = otp_plaintext
        messages.success(
            request,
            f"Sharing request created for {recipient.get_full_name() or recipient.username}. "
            f"Show them the OTP below — it expires in {expiry_minutes} minutes."
        )
        return render(request, "core/share_document.html", {
            "doc": doc, "form": form, "role": role,
            "grant": grant, "grant_otp": grant_otp,
        })

    ctx = {"doc": doc, "form": form, "role": role, "grant_otp": grant_otp}
    return render(request, "core/share_document.html", ctx)


# ── Sharing grant verification ────────────────────────────────────────────────

def share_verify(request, grant_id):
    """
    Recipient verifies their OTP to activate a sharing grant.
    Only the intended recipient may access this URL.
    """
    redir = _require_auth(request)
    if redir:
        return redir

    grant = get_object_or_404(SharingGrant, pk=grant_id)

    # Identity check: only the recipient may verify
    if request.user != grant.recipient:
        AuditLog.log(action="share_verify", outcome=AuditOutcome.DENIED,
                     user=request.user, resource_type="SharingGrant",
                     resource_id=grant_id, reason="Not the intended recipient")
        messages.error(request, "This sharing request is not addressed to you.")
        return redirect("core:dashboard")

    if grant.is_expired:
        AuditLog.log(action="share_verify", outcome=AuditOutcome.DENIED,
                     user=request.user, resource_type="SharingGrant",
                     resource_id=grant_id, reason="Grant expired")
        messages.error(request, "This sharing link has expired.")
        return redirect("core:dashboard")

    if grant.verified:
        # Already verified — go straight to download
        return redirect("core:share_download", grant_id=grant_id)

    otp_plaintext = None

    if request.method == "POST":
        action = request.POST.get("action", "")

        if action == "request_otp":
            # Re-issue OTP for this grant
            otp_token, otp_plaintext = OTPToken.generate_for(grant.recipient)
            grant.otp_token = otp_token
            grant.save(update_fields=["otp_token"])

        elif action == "verify":
            code  = request.POST.get("otp_code", "").strip()
            token = grant.otp_token

            if token is None or token.used or token.is_expired:
                AuditLog.log(action="share_verify", outcome=AuditOutcome.FAILED,
                             user=request.user, resource_type="SharingGrant",
                             resource_id=grant_id, reason="No valid token")
                messages.error(request, "No valid OTP. Please request a new code.")
            elif token.attempts_exceeded:
                AuditLog.log(action="share_verify", outcome=AuditOutcome.DENIED,
                             user=request.user, resource_type="SharingGrant",
                             resource_id=grant_id, reason="Attempt limit")
                messages.error(request, "Too many failed attempts.")
            elif token.verify(code):
                grant.verified = True
                grant.save(update_fields=["verified"])
                AuditLog.log(action="share_verify", outcome=AuditOutcome.SUCCESS,
                             user=request.user, resource_type="SharingGrant",
                             resource_id=grant_id)
                messages.success(request, "Identity verified. You may now download the document.")
                return redirect("core:share_download", grant_id=grant_id)
            else:
                remaining = OTPToken.OTP_MAX_ATTEMPTS - token.attempts
                AuditLog.log(action="share_verify", outcome=AuditOutcome.FAILED,
                             user=request.user, resource_type="SharingGrant",
                             resource_id=grant_id, reason=f"Wrong code, {remaining} left")
                messages.error(request, f"Incorrect code. {remaining} attempt(s) remaining.")

    ctx = {"grant": grant, "otp_plaintext": otp_plaintext}
    return render(request, "core/share_verify.html", ctx)


# ── Sharing grant download ────────────────────────────────────────────────────

def share_download(request, grant_id):
    """
    Serve the shared document after verifying: recipient identity, grant validity.
    """
    redir = _require_auth(request)
    if redir:
        return redir

    grant = get_object_or_404(SharingGrant, pk=grant_id)

    def _deny(reason):
        AuditLog.log(action="share_download", outcome=AuditOutcome.DENIED,
                     user=request.user, resource_type="SharingGrant",
                     resource_id=grant_id, reason=reason)
        messages.error(request, "Access to this shared document was denied.")
        return redirect("core:dashboard")

    if request.user != grant.recipient:
        return _deny("Not the recipient")
    if not grant.verified:
        return _deny("Grant not verified")
    if grant.is_expired:
        return _deny("Grant expired")

    doc = grant.document
    file_path = doc.stored_file.path
    if not os.path.exists(file_path):
        raise Http404("Shared document file not found.")

    AuditLog.log(action="share_download", outcome=AuditOutcome.SUCCESS,
                 user=request.user, resource_type="SharingGrant", resource_id=grant_id)

    mime_type, _ = mimetypes.guess_type(file_path)
    return FileResponse(
        open(file_path, "rb"),
        content_type=mime_type or "application/octet-stream",
        as_attachment=True,
        filename=doc.display_name,
    )


# ── Audit log page ────────────────────────────────────────────────────────────

def audit_log(request):
    """Admin-only view of audit log entries with basic filtering."""
    redir = _require_auth(request)
    if redir:
        return redir

    role = _get_role(request.user)
    if role != Role.ADMIN:
        AuditLog.log(action="audit_access", outcome=AuditOutcome.DENIED,
                     user=request.user, reason="Non-admin attempted audit access")
        messages.error(request, "Audit log is restricted to administrators.")
        return redirect("core:dashboard")

    qs = AuditLog.objects.select_related("user").all()

    # Filters
    action_filter  = request.GET.get("action", "").strip()
    outcome_filter = request.GET.get("outcome", "").strip()

    if action_filter:
        qs = qs.filter(action__icontains=action_filter)
    if outcome_filter:
        qs = qs.filter(outcome=outcome_filter)

    ctx = {
        "logs":           qs[:200],
        "role":           role,
        "action_filter":  action_filter,
        "outcome_filter": outcome_filter,
        "outcome_choices": AuditOutcome.choices,
    }
    return render(request, "core/audit_log.html", ctx)
