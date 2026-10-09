"""
Views for the core app – Phase 2.

Authentication flow
───────────────────
  /login/   – Step 1: user enters registered demo email → OTP generated & shown
  /verify/  – Step 2: user enters the six-digit code → session established
  /logout/  – Clears session

Role-based pages
────────────────
  /dashboard/        – role-specific overview (all authenticated users)
  /patients/         – patient list  (admin, doctor, management)
  /patients/<id>/    – patient detail with RBAC enforcement
"""

from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.models import User
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .models import OTPToken, PatientProfile, Role, UserProfile


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
            messages.error(request, "No demo account found for that email address.")
            return render(request, "core/login.html")

        # Generate OTP and display it in the demo panel
        _token, otp_plaintext = OTPToken.generate_for(user)

        # Store the user PK in session so /verify/ knows who to authenticate
        request.session["otp_user_id"] = user.pk
        request.session["otp_email"]   = email

    return render(request, "core/login.html", {"otp_plaintext": otp_plaintext})


def verify_view(request):
    """
    Step 2 – OTP entry and verification.
    """
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

        # Fetch the most recent unused token
        token = (
            OTPToken.objects
            .filter(user=user, used=False)
            .order_by("-created_at")
            .first()
        )

        if token is None:
            messages.error(request, "No active OTP found. Please request a new code.")
            return redirect("core:login")

        if token.is_expired:
            messages.error(request, "Your OTP has expired. Please request a new code.")
            return redirect("core:login")

        if token.attempts_exceeded:
            messages.error(request, "Too many failed attempts. Please request a new code.")
            return redirect("core:login")

        if token.verify(code):
            # Clear OTP session keys before establishing auth session
            request.session.pop("otp_user_id", None)
            request.session.pop("otp_email",   None)
            login(request, user)
            messages.success(request, f"Welcome, {user.get_full_name() or user.username}!")
            return redirect("core:dashboard")
        else:
            remaining = OTPToken.OTP_MAX_ATTEMPTS - token.attempts
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
    """
    Patient list – accessible by admin, doctor, management.
    Doctors only see their assigned patients.
    """
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
    """
    Patient detail – RBAC enforced in the view.

    Admin     → any patient
    Doctor    → assigned patients only
    Management→ read-only, cannot access medical details (limited fields shown in template)
    Patient   → own record only
    """
    redir = _require_auth(request)
    if redir:
        return redir

    role    = _get_role(request.user)
    profile = get_object_or_404(PatientProfile, patient_id=patient_id)

    # ── Permission checks ──────────────────────────────────────────────────
    if role == Role.ADMIN:
        pass  # full access

    elif role == Role.DOCTOR:
        if profile.assigned_doctor != request.user:
            messages.error(request, "You are not authorised to view this patient's record.")
            return redirect("core:patient_list")

    elif role == Role.MANAGEMENT:
        pass  # read-only limited view; template controls visible fields

    elif role == Role.PATIENT:
        try:
            own = request.user.patient_profile
        except PatientProfile.DoesNotExist:
            messages.error(request, "No patient record associated with your account.")
            return redirect("core:dashboard")
        if own.pk != profile.pk:
            messages.error(request, "You can only view your own record.")
            return redirect("core:dashboard")

    else:
        messages.error(request, "Access denied.")
        return redirect("core:dashboard")

    return render(request, "core/patient_detail.html", {"profile": profile, "role": role})
