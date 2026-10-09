"""
Tests for the core app – Phase 2.

Covers:
  OTP flow   – success, wrong code, expired, reused, attempt limit, unknown email
  Roles      – each role's dashboard access
  RBAC       – doctor→assigned, doctor→unrelated, patient→own, patient→other,
               management→patient list (no medical edit)
"""

from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from .models import OTPToken, PatientProfile, Role, UserProfile


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def make_user(username, email, role, first="Test", last="User"):
    user = User.objects.create_user(
        username=username, email=email,
        first_name=first, last_name=last,
        password=None,
    )
    user.set_unusable_password()
    user.save()
    UserProfile.objects.create(user=user, role=role)
    return user


def make_patient(user, patient_id, doctor=None):
    from datetime import date
    return PatientProfile.objects.create(
        patient_user=user,
        patient_id=patient_id,
        date_of_birth=date(1990, 1, 1),
        gender="M",
        blood_group="O+",
        phone="0000",
        address="Demo St",
        allergies="None",
        medical_history="None",
        current_medications="None",
        assigned_doctor=doctor,
    )


def otp_login(client, user):
    """Full OTP login flow for a test user. Returns the plaintext OTP."""
    token, plaintext = OTPToken.generate_for(user)
    client.session["otp_user_id"] = user.pk
    client.session["otp_email"]   = user.email
    client.session.save()
    resp = client.post(reverse("core:verify"), {"otp_code": plaintext})
    return resp, plaintext


# ─────────────────────────────────────────────────────────────────────────────
# OTP model tests
# ─────────────────────────────────────────────────────────────────────────────

class OTPModelTests(TestCase):

    def setUp(self):
        self.user = make_user("otp_user", "otp@test.demo", Role.PATIENT)

    def test_generate_returns_six_digit_string(self):
        _token, plaintext = OTPToken.generate_for(self.user)
        self.assertEqual(len(plaintext), 6)
        self.assertTrue(plaintext.isdigit())

    def test_verify_correct_code(self):
        token, plaintext = OTPToken.generate_for(self.user)
        self.assertTrue(token.verify(plaintext))

    def test_verify_wrong_code(self):
        token, plaintext = OTPToken.generate_for(self.user)
        wrong = "000000" if plaintext != "000000" else "111111"
        self.assertFalse(token.verify(wrong))

    def test_verify_marks_used_on_success(self):
        token, plaintext = OTPToken.generate_for(self.user)
        token.verify(plaintext)
        token.refresh_from_db()
        self.assertTrue(token.used)

    def test_reused_otp_rejected(self):
        token, plaintext = OTPToken.generate_for(self.user)
        token.verify(plaintext)   # first use
        # Manually reset used=False to simulate re-attempt with same token object
        token.refresh_from_db()
        self.assertFalse(token.verify(plaintext))   # already marked used

    def test_expired_otp_rejected(self):
        token, plaintext = OTPToken.generate_for(self.user)
        # Move expiry to the past
        token.expires_at = timezone.now() - timedelta(seconds=1)
        token.save()
        self.assertFalse(token.verify(plaintext))

    def test_attempt_limit_enforced(self):
        token, plaintext = OTPToken.generate_for(self.user)
        wrong = "000000" if plaintext != "000000" else "111111"
        for _ in range(OTPToken.OTP_MAX_ATTEMPTS):
            token.verify(wrong)
        token.refresh_from_db()
        self.assertTrue(token.attempts_exceeded)
        # Even correct code should be rejected now
        self.assertFalse(token.verify(plaintext))

    def test_new_otp_invalidates_previous(self):
        token1, _  = OTPToken.generate_for(self.user)
        _token2, _ = OTPToken.generate_for(self.user)
        token1.refresh_from_db()
        self.assertTrue(token1.used)


# ─────────────────────────────────────────────────────────────────────────────
# Login view tests
# ─────────────────────────────────────────────────────────────────────────────

class LoginViewTests(TestCase):

    def setUp(self):
        self.client = Client()
        self.user = make_user("lv_patient", "lv@test.demo", Role.PATIENT)

    def test_get_login_page(self):
        resp = self.client.get(reverse("core:login"))
        self.assertEqual(resp.status_code, 200)

    def test_unknown_email_rejected(self):
        resp = self.client.post(reverse("core:login"), {"email": "nobody@nowhere.demo"})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "No demo account")

    def test_known_email_shows_otp_panel(self):
        resp = self.client.post(reverse("core:login"), {"email": self.user.email})
        self.assertEqual(resp.status_code, 200)
        self.assertIn("otp_plaintext", resp.context)
        self.assertIsNotNone(resp.context["otp_plaintext"])

    def test_known_email_sets_session(self):
        self.client.post(reverse("core:login"), {"email": self.user.email})
        self.assertEqual(self.client.session.get("otp_user_id"), self.user.pk)


# ─────────────────────────────────────────────────────────────────────────────
# Verify view tests
# ─────────────────────────────────────────────────────────────────────────────

class VerifyViewTests(TestCase):

    def setUp(self):
        self.client = Client()
        self.user = make_user("vv_patient", "vv@test.demo", Role.PATIENT)

    def _set_session(self):
        session = self.client.session
        session["otp_user_id"] = self.user.pk
        session["otp_email"]   = self.user.email
        session.save()

    def test_verify_without_session_redirects(self):
        resp = self.client.get(reverse("core:verify"))
        self.assertRedirects(resp, reverse("core:login"))

    def test_correct_otp_logs_in(self):
        self._set_session()
        token, plaintext = OTPToken.generate_for(self.user)
        resp = self.client.post(reverse("core:verify"), {"otp_code": plaintext})
        self.assertRedirects(resp, reverse("core:dashboard"))
        # User should now be authenticated
        resp2 = self.client.get(reverse("core:dashboard"))
        self.assertEqual(resp2.status_code, 200)

    def test_wrong_otp_shows_error(self):
        self._set_session()
        token, plaintext = OTPToken.generate_for(self.user)
        wrong = "000000" if plaintext != "000000" else "111111"
        resp = self.client.post(reverse("core:verify"), {"otp_code": wrong})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Incorrect code")

    def test_expired_otp_redirects_to_login(self):
        self._set_session()
        token, plaintext = OTPToken.generate_for(self.user)
        token.expires_at = timezone.now() - timedelta(seconds=1)
        token.save()
        resp = self.client.post(reverse("core:verify"), {"otp_code": plaintext})
        self.assertRedirects(resp, reverse("core:login"))

    def test_reused_otp_redirects(self):
        self._set_session()
        token, plaintext = OTPToken.generate_for(self.user)
        # Mark used
        token.used = True
        token.save()
        resp = self.client.post(reverse("core:verify"), {"otp_code": plaintext})
        # No active token → redirect to login
        self.assertRedirects(resp, reverse("core:login"))

    def test_attempt_limit_redirects(self):
        self._set_session()
        token, plaintext = OTPToken.generate_for(self.user)
        wrong = "000000" if plaintext != "000000" else "111111"
        for _ in range(OTPToken.OTP_MAX_ATTEMPTS):
            token.verify(wrong)
        token.refresh_from_db()
        resp = self.client.post(reverse("core:verify"), {"otp_code": plaintext})
        self.assertRedirects(resp, reverse("core:login"))


# ─────────────────────────────────────────────────────────────────────────────
# Dashboard RBAC tests
# ─────────────────────────────────────────────────────────────────────────────

class DashboardRBACTests(TestCase):

    def setUp(self):
        self.client  = Client()
        self.admin   = make_user("dash_admin", "dadmin@t.demo",  Role.ADMIN,      "Admin",  "User")
        self.doctor  = make_user("dash_doc",   "ddoc@t.demo",    Role.DOCTOR,     "Doc",    "User")
        self.mgmt    = make_user("dash_mgmt",  "dmgmt@t.demo",   Role.MANAGEMENT, "Mgmt",   "User")
        self.patient = make_user("dash_pat",   "dpat@t.demo",    Role.PATIENT,    "Pat",    "User")

    def _login(self, user):
        self.client.force_login(user)

    def test_unauthenticated_redirects(self):
        resp = self.client.get(reverse("core:dashboard"))
        self.assertRedirects(resp, reverse("core:login"))

    def test_admin_dashboard(self):
        self._login(self.admin)
        resp = self.client.get(reverse("core:dashboard"))
        self.assertEqual(resp.status_code, 200)
        self.assertIn("total_users", resp.context)

    def test_doctor_dashboard(self):
        self._login(self.doctor)
        resp = self.client.get(reverse("core:dashboard"))
        self.assertEqual(resp.status_code, 200)
        self.assertIn("assigned_patients", resp.context)

    def test_management_dashboard(self):
        self._login(self.mgmt)
        resp = self.client.get(reverse("core:dashboard"))
        self.assertEqual(resp.status_code, 200)
        self.assertIn("total_patients", resp.context)

    def test_patient_dashboard(self):
        self._login(self.patient)
        resp = self.client.get(reverse("core:dashboard"))
        self.assertEqual(resp.status_code, 200)
        self.assertIn("patient_profile", resp.context)


# ─────────────────────────────────────────────────────────────────────────────
# Patient list RBAC tests
# ─────────────────────────────────────────────────────────────────────────────

class PatientListRBACTests(TestCase):

    def setUp(self):
        self.client  = Client()
        self.admin   = make_user("pl_admin",   "pladm@t.demo",  Role.ADMIN)
        self.doctor  = make_user("pl_doc",     "pldoc@t.demo",  Role.DOCTOR)
        self.mgmt    = make_user("pl_mgmt",    "plmgmt@t.demo", Role.MANAGEMENT)
        self.patient = make_user("pl_patient", "plpat@t.demo",  Role.PATIENT)

    def test_admin_can_see_list(self):
        self.client.force_login(self.admin)
        resp = self.client.get(reverse("core:patient_list"))
        self.assertEqual(resp.status_code, 200)

    def test_doctor_can_see_list(self):
        self.client.force_login(self.doctor)
        resp = self.client.get(reverse("core:patient_list"))
        self.assertEqual(resp.status_code, 200)

    def test_management_can_see_list(self):
        self.client.force_login(self.mgmt)
        resp = self.client.get(reverse("core:patient_list"))
        self.assertEqual(resp.status_code, 200)

    def test_patient_cannot_see_list(self):
        self.client.force_login(self.patient)
        resp = self.client.get(reverse("core:patient_list"))
        self.assertRedirects(resp, reverse("core:dashboard"))

    def test_unauthenticated_redirects(self):
        resp = self.client.get(reverse("core:patient_list"))
        self.assertRedirects(resp, reverse("core:login"))


# ─────────────────────────────────────────────────────────────────────────────
# Patient detail RBAC tests
# ─────────────────────────────────────────────────────────────────────────────

class PatientDetailRBACTests(TestCase):

    def setUp(self):
        self.client  = Client()
        self.doctor1 = make_user("pd_doc1",   "pd_doc1@t.demo", Role.DOCTOR,  "Doc1", "")
        self.doctor2 = make_user("pd_doc2",   "pd_doc2@t.demo", Role.DOCTOR,  "Doc2", "")
        self.admin   = make_user("pd_admin",  "pd_adm@t.demo",  Role.ADMIN)
        self.mgmt    = make_user("pd_mgmt",   "pd_mgt@t.demo",  Role.MANAGEMENT)
        self.pat1u   = make_user("pd_pat1",   "pd_p1@t.demo",   Role.PATIENT, "Pat", "One")
        self.pat2u   = make_user("pd_pat2",   "pd_p2@t.demo",   Role.PATIENT, "Pat", "Two")
        self.pat1    = make_patient(self.pat1u, "TST-0001", doctor=self.doctor1)
        self.pat2    = make_patient(self.pat2u, "TST-0002", doctor=self.doctor2)

    def _url(self, pid):
        return reverse("core:patient_detail", kwargs={"patient_id": pid})

    # Admin
    def test_admin_can_view_any_patient(self):
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(self._url("TST-0001")).status_code, 200)
        self.assertEqual(self.client.get(self._url("TST-0002")).status_code, 200)

    # Doctor – assigned
    def test_doctor_can_view_assigned_patient(self):
        self.client.force_login(self.doctor1)
        self.assertEqual(self.client.get(self._url("TST-0001")).status_code, 200)

    # Doctor – unrelated (must be denied)
    def test_doctor_denied_unrelated_patient(self):
        self.client.force_login(self.doctor1)
        resp = self.client.get(self._url("TST-0002"))
        self.assertRedirects(resp, reverse("core:patient_list"))

    # Management
    def test_management_can_view_any_patient(self):
        self.client.force_login(self.mgmt)
        self.assertEqual(self.client.get(self._url("TST-0001")).status_code, 200)

    # Patient – own record
    def test_patient_can_view_own_record(self):
        self.client.force_login(self.pat1u)
        self.assertEqual(self.client.get(self._url("TST-0001")).status_code, 200)

    # Patient – another patient's record (must be denied)
    def test_patient_denied_another_patients_record(self):
        self.client.force_login(self.pat1u)
        resp = self.client.get(self._url("TST-0002"))
        self.assertRedirects(resp, reverse("core:dashboard"))

    # Unauthenticated
    def test_unauthenticated_redirects(self):
        resp = self.client.get(self._url("TST-0001"))
        self.assertRedirects(resp, reverse("core:login"))

    # 404 for nonexistent patient
    def test_nonexistent_patient_404(self):
        self.client.force_login(self.admin)
        resp = self.client.get(self._url("TST-9999"))
        self.assertEqual(resp.status_code, 404)


# ─────────────────────────────────────────────────────────────────────────────
# Phase 3 Tests: Documents, Sharing, Audit Logging
# ─────────────────────────────────────────────────────────────────────────────

import shutil
import tempfile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings

from .models import AuditLog, AuditOutcome, MedicalDocument, SharingGrant


def make_sample_pdf(name="test.pdf", content=b"%PDF-1.4 sample content"):
    return SimpleUploadedFile(name, content, content_type="application/pdf")


def make_sample_png(name="test.png", content=b"\x89PNG\r\n\x1a\n\x00\x00\x00"):
    return SimpleUploadedFile(name, content, content_type="image/png")


def make_sample_jpg(name="test.jpg", content=b"\xff\xd8\xff\xe0\x00\x10JFIF"):
    return SimpleUploadedFile(name, content, content_type="image/jpeg")


class DocumentUploadTests(TestCase):

    def setUp(self):
        self.temp_media = tempfile.mkdtemp()
        self.settings_override = override_settings(MEDIA_ROOT=self.temp_media)
        self.settings_override.enable()

        self.client = Client()
        self.admin = make_user("up_admin", "upadmin@test.demo", Role.ADMIN)
        self.doc1 = make_user("up_doc1", "updoc1@test.demo", Role.DOCTOR)
        self.doc2 = make_user("up_doc2", "updoc2@test.demo", Role.DOCTOR)
        self.pat_user = make_user("up_pat", "uppat@test.demo", Role.PATIENT)
        self.patient = make_patient(self.pat_user, "P-UP-001", doctor=self.doc1)

    def tearDown(self):
        self.settings_override.disable()
        shutil.rmtree(self.temp_media, ignore_errors=True)

    def test_doctor_can_upload_valid_pdf_for_assigned_patient(self):
        self.client.force_login(self.doc1)
        pdf = make_sample_pdf()
        url = reverse("core:document_upload", kwargs={"patient_id": self.patient.patient_id})
        resp = self.client.post(url, {
            "display_name": "Blood Report",
            "doc_type": "lab_result",
            "file": pdf,
        })
        self.assertRedirects(resp, reverse("core:document_list", kwargs={"patient_id": self.patient.patient_id}))
        self.assertEqual(MedicalDocument.objects.count(), 1)
        doc = MedicalDocument.objects.first()
        self.assertEqual(doc.display_name, "Blood Report")
        self.assertEqual(doc.uploaded_by, self.doc1)
        # Verify audit log recorded
        self.assertTrue(AuditLog.objects.filter(action="doc_upload", outcome=AuditOutcome.SUCCESS).exists())

    def test_admin_can_upload_document(self):
        self.client.force_login(self.admin)
        png = make_sample_png()
        url = reverse("core:document_upload", kwargs={"patient_id": self.patient.patient_id})
        resp = self.client.post(url, {
            "display_name": "Scan Image",
            "doc_type": "imaging",
            "file": png,
        })
        self.assertRedirects(resp, reverse("core:document_list", kwargs={"patient_id": self.patient.patient_id}))
        self.assertEqual(MedicalDocument.objects.count(), 1)

    def test_unassigned_doctor_denied_upload(self):
        self.client.force_login(self.doc2)
        pdf = make_sample_pdf()
        url = reverse("core:document_upload", kwargs={"patient_id": self.patient.patient_id})
        resp = self.client.post(url, {
            "display_name": "Blood Report",
            "doc_type": "lab_result",
            "file": pdf,
        })
        self.assertRedirects(resp, reverse("core:patient_list"))
        self.assertEqual(MedicalDocument.objects.count(), 0)
        self.assertTrue(AuditLog.objects.filter(action="doc_upload", outcome=AuditOutcome.DENIED).exists())

    def test_patient_denied_upload(self):
        self.client.force_login(self.pat_user)
        pdf = make_sample_pdf()
        url = reverse("core:document_upload", kwargs={"patient_id": self.patient.patient_id})
        resp = self.client.post(url, {
            "display_name": "My Report",
            "doc_type": "lab_result",
            "file": pdf,
        })
        self.assertRedirects(resp, reverse("core:patient_detail", kwargs={"patient_id": self.patient.patient_id}))
        self.assertEqual(MedicalDocument.objects.count(), 0)

    def test_upload_invalid_file_extension(self):
        self.client.force_login(self.doc1)
        bad_file = SimpleUploadedFile("script.py", b"print('malicious')", content_type="text/x-python")
        url = reverse("core:document_upload", kwargs={"patient_id": self.patient.patient_id})
        resp = self.client.post(url, {
            "display_name": "Script",
            "doc_type": "other",
            "file": bad_file,
        })
        self.assertEqual(resp.status_code, 200)
        self.assertFormError(resp.context["form"], "file", "File type '.py' is not allowed. Accepted: pdf, jpg, jpeg, png.")
        self.assertEqual(MedicalDocument.objects.count(), 0)

    def test_upload_spoofed_pdf_content_rejected(self):
        self.client.force_login(self.doc1)
        spoofed = SimpleUploadedFile("fake.pdf", b"This is not a real PDF header", content_type="application/pdf")
        url = reverse("core:document_upload", kwargs={"patient_id": self.patient.patient_id})
        resp = self.client.post(url, {
            "display_name": "Fake PDF",
            "doc_type": "lab_result",
            "file": spoofed,
        })
        self.assertEqual(resp.status_code, 200)
        self.assertFormError(resp.context["form"], "file", "File does not appear to be a valid PDF.")

    def test_upload_size_limit_enforced(self):
        self.client.force_login(self.doc1)
        large_content = b"%PDF-1.4 " + b"0" * (5 * 1024 * 1024 + 100)
        large_file = SimpleUploadedFile("large.pdf", large_content, content_type="application/pdf")
        url = reverse("core:document_upload", kwargs={"patient_id": self.patient.patient_id})
        resp = self.client.post(url, {
            "display_name": "Too Large",
            "doc_type": "lab_result",
            "file": large_file,
        })
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.context["form"].errors)


class DocumentAccessAndDownloadTests(TestCase):

    def setUp(self):
        self.temp_media = tempfile.mkdtemp()
        self.settings_override = override_settings(MEDIA_ROOT=self.temp_media)
        self.settings_override.enable()

        self.client = Client()
        self.admin = make_user("acc_admin", "accadmin@test.demo", Role.ADMIN)
        self.doc1 = make_user("acc_doc1", "accdoc1@test.demo", Role.DOCTOR)
        self.doc2 = make_user("acc_doc2", "accdoc2@test.demo", Role.DOCTOR)
        self.mgmt = make_user("acc_mgmt", "accmgmt@test.demo", Role.MANAGEMENT)
        self.pat1_u = make_user("acc_pat1", "accpat1@test.demo", Role.PATIENT)
        self.pat2_u = make_user("acc_pat2", "accpat2@test.demo", Role.PATIENT)
        self.pat1 = make_patient(self.pat1_u, "P-ACC-001", doctor=self.doc1)
        self.pat2 = make_patient(self.pat2_u, "P-ACC-002", doctor=self.doc2)

        # Create a document for patient 1
        pdf = make_sample_pdf()
        self.doc = MedicalDocument.objects.create(
            patient=self.pat1,
            uploaded_by=self.doc1,
            display_name="Blood Count.pdf",
            stored_file=pdf,
            doc_type="lab_result",
            file_size_bytes=len(b"%PDF-1.4 sample content"),
        )

    def tearDown(self):
        self.settings_override.disable()
        shutil.rmtree(self.temp_media, ignore_errors=True)

    def test_assigned_doctor_can_view_document_list(self):
        self.client.force_login(self.doc1)
        resp = self.client.get(reverse("core:document_list", kwargs={"patient_id": self.pat1.patient_id}))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Blood Count.pdf")

    def test_unassigned_doctor_denied_document_list(self):
        self.client.force_login(self.doc2)
        resp = self.client.get(reverse("core:document_list", kwargs={"patient_id": self.pat1.patient_id}))
        self.assertRedirects(resp, reverse("core:dashboard"))

    def test_management_denied_document_list(self):
        self.client.force_login(self.mgmt)
        resp = self.client.get(reverse("core:document_list", kwargs={"patient_id": self.pat1.patient_id}))
        self.assertRedirects(resp, reverse("core:patient_detail", kwargs={"patient_id": self.pat1.patient_id}))
        self.assertTrue(AuditLog.objects.filter(action="doc_list", outcome=AuditOutcome.DENIED).exists())

    def test_patient_can_view_own_document_list(self):
        self.client.force_login(self.pat1_u)
        resp = self.client.get(reverse("core:document_list", kwargs={"patient_id": self.pat1.patient_id}))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Blood Count.pdf")

    def test_patient_denied_other_patient_document_list(self):
        self.client.force_login(self.pat2_u)
        resp = self.client.get(reverse("core:document_list", kwargs={"patient_id": self.pat1.patient_id}))
        self.assertRedirects(resp, reverse("core:dashboard"))

    def test_authorized_download_patient_and_doctor(self):
        # Patient downloading own document
        self.client.force_login(self.pat1_u)
        resp = self.client.get(reverse("core:document_download", kwargs={"doc_id": self.doc.pk}))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["Content-Disposition"], 'attachment; filename="Blood Count.pdf"')

        # Assigned doctor downloading document
        self.client.force_login(self.doc1)
        resp = self.client.get(reverse("core:document_download", kwargs={"doc_id": self.doc.pk}))
        self.assertEqual(resp.status_code, 200)

    def test_unauthorized_download_denied(self):
        # Unassigned doctor
        self.client.force_login(self.doc2)
        resp = self.client.get(reverse("core:document_download", kwargs={"doc_id": self.doc.pk}))
        self.assertRedirects(resp, reverse("core:dashboard"))

        # Management
        self.client.force_login(self.mgmt)
        resp = self.client.get(reverse("core:document_download", kwargs={"doc_id": self.doc.pk}))
        self.assertRedirects(resp, reverse("core:dashboard"))

        # Other patient
        self.client.force_login(self.pat2_u)
        resp = self.client.get(reverse("core:document_download", kwargs={"doc_id": self.doc.pk}))
        self.assertRedirects(resp, reverse("core:dashboard"))

        # Audit log has denied events
        self.assertTrue(AuditLog.objects.filter(action="doc_download", outcome=AuditOutcome.DENIED).exists())


class OTPProtectedSharingTests(TestCase):

    def setUp(self):
        self.temp_media = tempfile.mkdtemp()
        self.settings_override = override_settings(MEDIA_ROOT=self.temp_media)
        self.settings_override.enable()

        self.client = Client()
        self.doc1 = make_user("sh_doc1", "shdoc1@test.demo", Role.DOCTOR)
        self.doc2 = make_user("sh_doc2", "shdoc2@test.demo", Role.DOCTOR)
        self.recipient_user = make_user("sh_recip", "shrecip@test.demo", Role.DOCTOR)
        self.intruder_user = make_user("sh_intrud", "shintrud@test.demo", Role.PATIENT)
        self.pat_u = make_user("sh_pat", "shpat@test.demo", Role.PATIENT)
        self.patient = make_patient(self.pat_u, "P-SH-001", doctor=self.doc1)

        pdf = make_sample_pdf()
        self.doc = MedicalDocument.objects.create(
            patient=self.patient,
            uploaded_by=self.doc1,
            display_name="Confidential Consultation.pdf",
            stored_file=pdf,
            doc_type="referral",
            file_size_bytes=len(b"%PDF-1.4 sample content"),
        )

    def tearDown(self):
        self.settings_override.disable()
        shutil.rmtree(self.temp_media, ignore_errors=True)

    def test_doctor_creates_sharing_grant(self):
        self.client.force_login(self.doc1)
        url = reverse("core:share_document", kwargs={"doc_id": self.doc.pk})
        resp = self.client.post(url, {"recipient_email": self.recipient_user.email})
        self.assertEqual(resp.status_code, 200)
        self.assertIn("grant_otp", resp.context)
        self.assertEqual(SharingGrant.objects.count(), 1)
        grant = SharingGrant.objects.first()
        self.assertEqual(grant.recipient, self.recipient_user)
        self.assertFalse(grant.verified)
        self.assertTrue(AuditLog.objects.filter(action="share_create", outcome=AuditOutcome.SUCCESS).exists())

    def test_unassigned_doctor_cannot_create_share(self):
        self.client.force_login(self.doc2)
        url = reverse("core:share_document", kwargs={"doc_id": self.doc.pk})
        resp = self.client.post(url, {"recipient_email": self.recipient_user.email})
        self.assertRedirects(resp, reverse("core:patient_list"))
        self.assertEqual(SharingGrant.objects.count(), 0)

    def test_recipient_verifies_otp_and_downloads_shared_document(self):
        token, otp_code = OTPToken.generate_for(self.recipient_user)
        grant = SharingGrant.objects.create(
            document=self.doc,
            created_by=self.doc1,
            recipient=self.recipient_user,
            otp_token=token,
            expires_at=timezone.now() + timedelta(minutes=15),
        )

        # Login recipient
        self.client.force_login(self.recipient_user)

        # Verify with correct code
        verify_url = reverse("core:share_verify", kwargs={"grant_id": grant.pk})
        resp = self.client.post(verify_url, {"action": "verify", "otp_code": otp_code})
        self.assertRedirects(resp, reverse("core:share_download", kwargs={"grant_id": grant.pk}))

        grant.refresh_from_db()
        self.assertTrue(grant.verified)

        # Download document
        dl_url = reverse("core:share_download", kwargs={"grant_id": grant.pk})
        resp_dl = self.client.get(dl_url)
        self.assertEqual(resp_dl.status_code, 200)
        self.assertEqual(resp_dl["Content-Disposition"], 'attachment; filename="Confidential Consultation.pdf"')
        self.assertTrue(AuditLog.objects.filter(action="share_download", outcome=AuditOutcome.SUCCESS).exists())

    def test_intruder_cannot_verify_or_download_grant(self):
        token, otp_code = OTPToken.generate_for(self.recipient_user)
        grant = SharingGrant.objects.create(
            document=self.doc,
            created_by=self.doc1,
            recipient=self.recipient_user,
            otp_token=token,
            expires_at=timezone.now() + timedelta(minutes=15),
        )

        self.client.force_login(self.intruder_user)

        # Intruder attempts to verify
        verify_url = reverse("core:share_verify", kwargs={"grant_id": grant.pk})
        resp = self.client.post(verify_url, {"action": "verify", "otp_code": otp_code})
        self.assertRedirects(resp, reverse("core:dashboard"))
        grant.refresh_from_db()
        self.assertFalse(grant.verified)

        # Intruder attempts to download
        dl_url = reverse("core:share_download", kwargs={"grant_id": grant.pk})
        resp_dl = self.client.get(dl_url)
        self.assertRedirects(resp_dl, reverse("core:dashboard"))

    def test_expired_grant_denied_verification_and_download(self):
        token, otp_code = OTPToken.generate_for(self.recipient_user)
        grant = SharingGrant.objects.create(
            document=self.doc,
            created_by=self.doc1,
            recipient=self.recipient_user,
            otp_token=token,
            verified=False,
            expires_at=timezone.now() - timedelta(minutes=1),
        )

        self.client.force_login(self.recipient_user)
        verify_url = reverse("core:share_verify", kwargs={"grant_id": grant.pk})
        resp = self.client.post(verify_url, {"action": "verify", "otp_code": otp_code})
        self.assertRedirects(resp, reverse("core:dashboard"))

        # Even if artificially verified, expired grant cannot download
        grant.verified = True
        grant.save()
        dl_url = reverse("core:share_download", kwargs={"grant_id": grant.pk})
        resp_dl = self.client.get(dl_url)
        self.assertRedirects(resp_dl, reverse("core:dashboard"))


class AuditLogTests(TestCase):

    def setUp(self):
        self.client = Client()
        self.admin = make_user("aud_admin", "audadmin@test.demo", Role.ADMIN)
        self.doctor = make_user("aud_doc", "auddoc@test.demo", Role.DOCTOR)

    def test_admin_can_access_audit_log(self):
        AuditLog.log(action="test_action", outcome=AuditOutcome.SUCCESS, user=self.admin)
        self.client.force_login(self.admin)
        resp = self.client.get(reverse("core:audit_log"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "test_action")

    def test_non_admin_denied_audit_log(self):
        self.client.force_login(self.doctor)
        resp = self.client.get(reverse("core:audit_log"))
        self.assertRedirects(resp, reverse("core:dashboard"))
        self.assertTrue(AuditLog.objects.filter(action="audit_access", outcome=AuditOutcome.DENIED).exists())

    def test_audit_log_filtering(self):
        AuditLog.log(action="event_alpha", outcome=AuditOutcome.SUCCESS)
        AuditLog.log(action="event_beta", outcome=AuditOutcome.DENIED)

        self.client.force_login(self.admin)
        resp = self.client.get(reverse("core:audit_log") + "?action=event_alpha")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "event_alpha")
        self.assertNotContains(resp, "event_beta")


class IntegrationAndStartupTests(TestCase):
    """Explicit tests for startup imports, form validation, and Phase 3 URL routing."""

    def test_startup_imports(self):
        """Ensure DocumentUploadForm, ShareDocumentForm and all Phase 3 views are importable."""
        from core.forms import DocumentUploadForm, ShareDocumentForm
        from core import views

        self.assertTrue(callable(DocumentUploadForm))
        self.assertTrue(callable(ShareDocumentForm))
        self.assertTrue(hasattr(views, "document_list"))
        self.assertTrue(hasattr(views, "document_upload"))
        self.assertTrue(hasattr(views, "document_download"))
        self.assertTrue(hasattr(views, "share_document"))
        self.assertTrue(hasattr(views, "share_verify"))
        self.assertTrue(hasattr(views, "share_download"))
        self.assertTrue(hasattr(views, "audit_log"))

    def test_phase3_url_reversal(self):
        """Ensure all Phase 3 URL names reverse properly without NoReverseMatch."""
        self.assertEqual(reverse("core:document_list", kwargs={"patient_id": "P001"}), "/patients/P001/documents/")
        self.assertEqual(reverse("core:document_upload", kwargs={"patient_id": "P001"}), "/patients/P001/documents/upload/")
        self.assertEqual(reverse("core:document_download", kwargs={"doc_id": 1}), "/documents/1/download/")
        self.assertEqual(reverse("core:share_document", kwargs={"doc_id": 1}), "/documents/1/share/")
        self.assertEqual(reverse("core:share_verify", kwargs={"grant_id": 1}), "/share/1/verify/")
        self.assertEqual(reverse("core:share_download", kwargs={"grant_id": 1}), "/share/1/download/")
        self.assertEqual(reverse("core:audit_log"), "/audit/")

    def test_share_document_form_validation(self):
        """Test recipient lookup and validation on ShareDocumentForm."""
        from core.forms import ShareDocumentForm
        user = make_user("recipient_test", "recip_test@securehealth.demo", Role.DOCTOR)

        # Non-existent user
        form_invalid = ShareDocumentForm(data={"recipient_email": "nonexistent@demo.com"})
        self.assertFalse(form_invalid.is_valid())
        self.assertIn("recipient_email", form_invalid.errors)

        # Existing user
        form_valid = ShareDocumentForm(data={"recipient_email": "recip_test@securehealth.demo"})
        self.assertTrue(form_valid.is_valid())
        self.assertEqual(form_valid.get_recipient(), user)
