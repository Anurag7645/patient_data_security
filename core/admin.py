"""Admin registrations for core models – Phase 2 + Phase 3."""

from django.contrib import admin
from .models import AuditLog, MedicalDocument, OTPToken, PatientProfile, SharingGrant, UserProfile


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display  = ("user", "role")
    list_filter   = ("role",)
    search_fields = ("user__username", "user__email")


@admin.register(OTPToken)
class OTPTokenAdmin(admin.ModelAdmin):
    list_display   = ("user", "created_at", "expires_at", "used", "attempts")
    list_filter    = ("used",)
    search_fields  = ("user__username",)
    readonly_fields = ("code_hash", "created_at", "expires_at", "attempts")


@admin.register(PatientProfile)
class PatientProfileAdmin(admin.ModelAdmin):
    list_display  = ("patient_id", "full_name", "blood_group", "assigned_doctor")
    list_filter   = ("blood_group", "gender")
    search_fields = ("patient_id", "patient_user__first_name", "patient_user__last_name")
    raw_id_fields = ("patient_user", "assigned_doctor")


@admin.register(MedicalDocument)
class MedicalDocumentAdmin(admin.ModelAdmin):
    list_display    = ("display_name", "patient", "doc_type", "uploaded_by", "uploaded_at", "file_size_bytes")
    list_filter     = ("doc_type",)
    search_fields   = ("display_name", "patient__patient_id")
    readonly_fields = ("stored_file", "uploaded_at", "file_size_bytes")
    raw_id_fields   = ("patient", "uploaded_by")


@admin.register(SharingGrant)
class SharingGrantAdmin(admin.ModelAdmin):
    list_display  = ("pk", "document", "created_by", "recipient", "verified", "expires_at", "is_expired")
    list_filter   = ("verified",)
    search_fields = ("recipient__username", "document__display_name")
    readonly_fields = ("created_at", "otp_token")

    def is_expired(self, obj):
        return obj.is_expired
    is_expired.boolean = True


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display  = ("timestamp", "user", "action", "resource_type", "resource_id", "outcome", "reason")
    list_filter   = ("outcome", "action")
    search_fields = ("user__username", "action", "resource_id")
    readonly_fields = ("timestamp", "user", "action", "resource_type", "resource_id", "outcome", "reason")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
