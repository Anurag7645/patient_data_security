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
