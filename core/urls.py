"""URL patterns for the core app – Phase 2."""

from django.urls import path
from . import views

app_name = "core"

urlpatterns = [
    # Public
    path("", views.home, name="home"),

    # Authentication (mock OTP)
    path("login/",   views.login_view,  name="login"),
    path("verify/",  views.verify_view, name="verify"),
    path("logout/",  views.logout_view, name="logout"),

    # Protected
    path("dashboard/",              views.dashboard,      name="dashboard"),
    path("patients/",               views.patient_list,   name="patient_list"),
    path("patients/<str:patient_id>/", views.patient_detail, name="patient_detail"),
]
