"""Views for the core app – Phase 1."""

from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib import messages


def home(request):
    """Public landing page."""
    return render(request, "core/home.html")


def dashboard(request):
    """Basic dashboard – requires authentication."""
    if not request.user.is_authenticated:
        return redirect("core:login")

    controls = [
        {"name": "TLS/SSL Encryption",       "category": "Confidentiality", "status": "Active"},
        {"name": "Role-Based Access Control", "category": "Access Control",  "status": "Active"},
        {"name": "Audit Logging",             "category": "Accountability",  "status": "Active"},
        {"name": "Intrusion Detection",       "category": "Threat Detection","status": "Active"},
        {"name": "Network Segmentation",      "category": "Infrastructure",  "status": "Active"},
        {"name": "HIPAA Compliance Review",   "category": "Regulatory",      "status": "Review"},
    ]
    return render(request, "core/dashboard.html", {"controls": controls})


def login_view(request):
    """Login page."""
    if request.user.is_authenticated:
        return redirect("core:home")

    if request.method == "POST":
        username = request.POST.get("username", "").strip()
        password = request.POST.get("password", "")
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            next_url = request.GET.get("next", "core:dashboard")
            return redirect(next_url)
        messages.error(request, "Invalid username or password. Please try again.")

    return render(request, "core/login.html")


def logout_view(request):
    """Logout and redirect to home."""
    logout(request)
    return redirect("core:home")
