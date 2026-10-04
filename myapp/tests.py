import json
from datetime import timedelta

from django.contrib.auth.hashers import check_password
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .forms import MemberForm
from .models import CheckIn, Member, Membership, Package, QRCodeToken, User
from .services import decrypt_national_id, token_digest


@override_settings(NATIONAL_ID_ENCRYPTION_KEY="test-only-encryption-key")
class MemberNationalIdTests(TestCase):
	def setUp(self):
		self.staff = User.objects.create_superuser(phone="0891234567", password="staff-password")
		self.national_id = "1234567890121"
		self.member_data = {
			"member_code": "M-1001",
			"first_name": "Test",
			"last_name": "Member",
			"nickname": "Tester",
			"phone": "0812345678",
			"national_id": self.national_id,
			"birth_date": "1995-04-12",
			"gender": "อื่นๆ",
			"line_id": "",
			"facebook": "",
		}

	def test_member_can_login_with_national_id_and_raw_id_is_not_stored(self):
		self.client.force_login(self.staff)
		response = self.client.post(reverse("staff-member-create"), self.member_data)
		member = Member.objects.get(member_code="M-1001")
		self.assertRedirects(response, reverse("staff-member-detail", args=[member.pk]))
		self.assertTrue(check_password(self.national_id, member.national_id_hash))
		self.assertNotIn(self.national_id, member.national_id_hash)
		self.assertNotEqual(member.national_id_encrypted, self.national_id)
		self.assertEqual(decrypt_national_id(member.national_id_encrypted), self.national_id)
		self.assertContains(self.client.get(reverse("staff-member-detail", args=[member.pk])), self.national_id)
		self.assertIsNone(member.user)

		self.client.logout()
		response = self.client.post(reverse("login"), {
			"phone": member.phone,
			"password": self.national_id,
		}, follow=True)
		self.assertEqual(response.request["PATH_INFO"], reverse("profile"))
		member.refresh_from_db()
		self.assertIsNotNone(member.user)
		self.assertTrue(member.user.is_activated)
		self.assertTrue(check_password(self.national_id, member.national_id_hash))

	def test_invalid_national_id_checksum_is_rejected(self):
		invalid_data = {**self.member_data, "national_id": "1234567890122"}
		form = MemberForm(data=invalid_data)
		self.assertFalse(form.is_valid())
		self.assertIn("national_id", form.errors)


@override_settings(NATIONAL_ID_ENCRYPTION_KEY="test-only-encryption-key")
class CheckInTests(TestCase):
	def setUp(self):
		self.member_user = User.objects.create_user(
			phone="0812345678",
			password="member-password",
			is_activated=True,
		)
		self.member = Member.objects.create(
			user=self.member_user,
			member_code="M-2001",
			first_name="Check",
			last_name="In",
			nickname="Tester",
			phone=self.member_user.phone,
		)
		self.staff = User.objects.create_superuser(
			phone="0899999999",
			password="staff-password",
		)
		self.token = "valid-one-time-qr-token"
		self.qr = QRCodeToken.objects.create(
			member=self.member,
			token_hash=token_digest(self.token),
			expires_at=timezone.now() + timedelta(minutes=5),
		)

	def test_member_can_issue_five_minute_qr(self):
		self.client.force_login(self.member_user)
		response = self.client.post(reverse("create-qr"))
		self.assertRedirects(response, reverse("profile"))
		token = self.client.session["active_qr_token"]
		issued = QRCodeToken.objects.get(token_hash=token_digest(token))
		self.assertEqual(issued.member, self.member)
		self.assertGreater(issued.expires_at, timezone.now() + timedelta(minutes=4, seconds=50))
		self.assertLess(issued.expires_at, timezone.now() + timedelta(minutes=5, seconds=5))
		self.assertEqual(self.client.get(reverse("profile")).status_code, 200)

	def test_staff_scanner_display_and_admin_pages_load(self):
		self.client.force_login(self.staff)
		scanner_response = self.client.get(reverse("scanner"))
		self.assertEqual(scanner_response.status_code, 200)
		self.assertContains(scanner_response, "myapp/vendor/jsQR.js")
		self.assertContains(scanner_response, "scanner.js?v=3")
		self.assertEqual(self.client.get(reverse("display")).status_code, 200)
		self.assertEqual(self.client.get("/admin/myapp/user/add/").status_code, 200)

	def test_admin_can_create_a_member_login(self):
		self.client.force_login(self.staff)
		response = self.client.post("/admin/myapp/user/add/", {
			"phone": "0801112233",
			"password1": "AdminStrong#29Password",
			"password2": "AdminStrong#29Password",
			"role": "MEMBER",
			"is_active": "on",
		})
		self.assertEqual(response.status_code, 302)
		self.assertTrue(User.objects.filter(phone="0801112233").exists())

	def test_staff_scan_consumes_qr_and_publishes_latest_checkin(self):
		self.client.force_login(self.staff)
		response = self.client.post(
			reverse("scan-qr"),
			data=json.dumps({"token": self.token}),
			content_type="application/json",
		)

		self.assertEqual(response.status_code, 200)
		self.assertEqual(response.json()["member"]["member_code"], self.member.member_code)
		self.assertEqual(CheckIn.objects.count(), 1)
		self.qr.refresh_from_db()
		self.assertIsNotNone(self.qr.used_at)

		response = self.client.post(
			reverse("scan-qr"),
			data=json.dumps({"token": self.token}),
			content_type="application/json",
		)
		self.assertEqual(response.status_code, 409)
		self.assertEqual(CheckIn.objects.count(), 1)

		response = self.client.get(reverse("latest-checkin"))
		self.assertEqual(response.status_code, 200)
		self.assertEqual(response.json()["checkin"]["member_code"], self.member.member_code)

	def test_expired_qr_cannot_check_in(self):
		self.qr.expires_at = timezone.now() - timedelta(seconds=1)
		self.qr.save(update_fields=["expires_at"])
		self.client.force_login(self.staff)

		response = self.client.post(
			reverse("scan-qr"),
			data=json.dumps({"token": self.token}),
			content_type="application/json",
		)

		self.assertEqual(response.status_code, 410)
		self.assertEqual(CheckIn.objects.count(), 0)

	def test_staff_dashboard_and_member_detail_are_available_to_staff(self):
		self.client.force_login(self.staff)
		response = self.client.get(reverse("staff-dashboard"))
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, self.member.member_code)
		self.assertEqual(
			self.client.get(reverse("staff-member-detail", args=[self.member.pk])).status_code,
			200,
		)
		self.assertEqual(self.client.get(reverse("staff-packages")).status_code, 200)
		self.assertEqual(self.client.get(reverse("staff-member-create")).status_code, 200)
		self.assertEqual(self.client.get(reverse("staff-member-edit", args=[self.member.pk])).status_code, 200)
		self.assertEqual(self.client.get(reverse("staff-member-delete", args=[self.member.pk])).status_code, 200)
		self.assertEqual(self.client.get(reverse("staff-membership-create", args=[self.member.pk])).status_code, 200)
		self.assertEqual(self.client.get(reverse("staff-package-create")).status_code, 200)
		package = Package.objects.create(package_name="GET Test", duration_days=30, price="1000.00")
		membership = Membership.objects.create(
			member=self.member,
			package=package,
			start_date=timezone.localdate(),
			expire_date=timezone.localdate() + timedelta(days=30),
		)
		self.assertEqual(self.client.get(reverse("staff-membership-edit", args=[membership.pk])).status_code, 200)
		self.assertEqual(self.client.get(reverse("staff-membership-delete", args=[membership.pk])).status_code, 200)
		self.assertEqual(self.client.get(reverse("staff-package-edit", args=[package.pk])).status_code, 200)
		self.assertEqual(self.client.get(reverse("staff-package-delete", args=[package.pk])).status_code, 200)

	def test_non_staff_cannot_open_management_dashboard(self):
		self.client.force_login(self.member_user)
		response = self.client.get(reverse("staff-dashboard"))
		self.assertEqual(response.status_code, 302)
		self.assertIn(reverse("login"), response.url)
		response = self.client.get(reverse("staff-member-detail", args=[self.member.pk]))
		self.assertEqual(response.status_code, 302)
		self.assertIn(reverse("login"), response.url)

	def test_staff_can_login_with_admin_identifier_from_shared_login_page(self):
		admin_user = User.objects.create_superuser(phone="admin26447", password="staff-password")
		response = self.client.post(reverse("login"), {
			"phone": "admin26447",
			"password": "staff-password",
		}, follow=True)
		self.assertEqual(response.status_code, 200)
		self.assertEqual(response.request["PATH_INFO"], reverse("staff-dashboard"))
		self.assertEqual(int(self.client.session["_auth_user_id"]), admin_user.pk)

	def test_staff_can_create_edit_delete_member_and_manual_checkin(self):
		self.client.force_login(self.staff)
		response = self.client.post(reverse("staff-member-create"), {
			"member_code": "M-3001",
			"first_name": "New",
			"last_name": "Member",
			"nickname": "Fresh",
			"phone": "0801234567",
			"national_id": "1234567890121",
			"birth_date": "1995-04-12",
			"gender": "อื่นๆ",
			"line_id": "new-line",
			"facebook": "new-facebook",
		})
		created = Member.objects.get(member_code="M-3001")
		self.assertRedirects(response, reverse("staff-member-detail", args=[created.pk]))

		response = self.client.post(reverse("staff-member-edit", args=[created.pk]), {
			"member_code": "M-3001",
			"first_name": "Updated",
			"last_name": "Member",
			"nickname": "Fresh",
			"phone": "0801234567",
			"birth_date": "1995-04-12",
			"gender": "อื่นๆ",
			"line_id": "new-line",
			"facebook": "new-facebook",
		})
		self.assertRedirects(response, reverse("staff-member-detail", args=[created.pk]))
		created.refresh_from_db()
		self.assertEqual(created.first_name, "Updated")

		response = self.client.post(reverse("staff-member-checkin", args=[created.pk]))
		self.assertRedirects(response, reverse("staff-member-detail", args=[created.pk]))
		self.assertTrue(CheckIn.objects.filter(member=created, method="ADMIN", status="SUCCESS").exists())

		response = self.client.post(reverse("staff-member-delete", args=[created.pk]))
		self.assertRedirects(response, reverse("staff-dashboard"))
		self.assertFalse(Member.objects.filter(pk=created.pk).exists())

	def test_staff_can_manage_membership_and_package(self):
		self.client.force_login(self.staff)
		response = self.client.post(reverse("staff-package-create"), {
			"package_name": "Monthly",
			"duration_days": 30,
			"price": "1200.00",
			"description": "One month",
			"is_active": "on",
		})
		package = Package.objects.get(package_name="Monthly")
		self.assertRedirects(response, reverse("staff-packages"))

		response = self.client.post(reverse("staff-membership-create", args=[self.member.pk]), {
			"package": package.pk,
			"start_date": "2026-10-01",
			"expire_date": "2026-10-31",
			"status": "ACTIVE",
		})
		membership = self.member.memberships.get(package=package)
		self.assertRedirects(response, reverse("staff-member-detail", args=[self.member.pk]))

		response = self.client.post(reverse("staff-membership-edit", args=[membership.pk]), {
			"package": package.pk,
			"start_date": "2026-10-01",
			"expire_date": "2026-11-01",
			"status": "CANCELLED",
		})
		self.assertRedirects(response, reverse("staff-member-detail", args=[self.member.pk]))
		membership.refresh_from_db()
		self.assertEqual(membership.status, "CANCELLED")

		response = self.client.post(reverse("staff-membership-delete", args=[membership.pk]))
		self.assertRedirects(response, reverse("staff-member-detail", args=[self.member.pk]))
		self.assertFalse(Membership.objects.filter(pk=membership.pk).exists())

		response = self.client.post(reverse("staff-package-edit", args=[package.pk]), {
			"package_name": "Monthly Plus",
			"duration_days": 31,
			"price": "1400.00",
			"description": "Updated",
			"is_active": "on",
		})
		self.assertRedirects(response, reverse("staff-packages"))
		package.refresh_from_db()
		self.assertEqual(package.package_name, "Monthly Plus")
		response = self.client.post(reverse("staff-package-delete", args=[package.pk]))
		self.assertRedirects(response, reverse("staff-packages"))
		self.assertFalse(Package.objects.filter(pk=package.pk).exists())
