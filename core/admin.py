"""Admin registrations for core models – Phase 2."""

from django.contrib import admin
from .models import UserProfile, OTPToken, PatientProfile


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display  = ("user", "role")
    list_filter   = ("role",)
    search_fields = ("user__username", "user__email")


@admin.register(OTPToken)
class OTPTokenAdmin(admin.ModelAdmin):
    list_display  = ("user", "created_at", "expires_at", "used", "attempts")
    list_filter   = ("used",)
    search_fields = ("user__username",)
    readonly_fields = ("code_hash", "created_at", "expires_at", "attempts")


@admin.register(PatientProfile)
class PatientProfileAdmin(admin.ModelAdmin):
    list_display  = ("patient_id", "full_name", "blood_group", "assigned_doctor")
    list_filter   = ("blood_group", "gender")
    search_fields = ("patient_id", "patient_user__first_name", "patient_user__last_name")
    raw_id_fields = ("patient_user", "assigned_doctor")
