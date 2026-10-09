"""URL patterns for the core app – Phase 2 + Phase 3."""

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

    # Protected – Phase 2
    path("dashboard/",                     views.dashboard,      name="dashboard"),
    path("patients/",                      views.patient_list,   name="patient_list"),
    path("patients/<str:patient_id>/",     views.patient_detail, name="patient_detail"),

    # Documents – Phase 3
    path("patients/<str:patient_id>/documents/",        views.document_list,   name="document_list"),
    path("patients/<str:patient_id>/documents/upload/", views.document_upload, name="document_upload"),
    path("documents/<int:doc_id>/download/",            views.document_download, name="document_download"),
    path("documents/<int:doc_id>/share/",               views.share_document,  name="share_document"),

    # Sharing grants – Phase 3
    path("share/<int:grant_id>/verify/",   views.share_verify,   name="share_verify"),
    path("share/<int:grant_id>/download/", views.share_download, name="share_download"),

    # Audit – Phase 3 (admin only)
    path("audit/", views.audit_log, name="audit_log"),
]
