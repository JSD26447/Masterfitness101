import json

from django.contrib import messages
from django.contrib.auth import authenticate, login as auth_login, logout as auth_logout
from django.contrib.auth.hashers import check_password
from django.contrib.auth.decorators import login_required
from django.contrib.auth.password_validation import validate_password
from django.contrib.admin.views.decorators import staff_member_required
from django.db import transaction
from django.db.models import Q
from django.db.models.deletion import ProtectedError
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from .forms import LoginForm, MemberForm, MembershipForm, PackageForm, PhoneForm
from .models import CheckIn, Member, Membership, Package, QRCodeToken, User
from .services import decrypt_national_id, issue_qr_token, qr_data_uri, token_digest


def home(request):
	if not request.user.is_authenticated:
		return redirect("login")
	if request.user.is_staff:
		return redirect("staff-dashboard")
	return redirect("profile")


def login_view(request):
	form = LoginForm(request.POST or None)
	if request.method == "POST" and form.is_valid():
		phone = form.cleaned_data["phone"]
		credential = form.cleaned_data["password"]
		staff_user = User.objects.filter(phone=phone, is_staff=True, is_active=True).first()
		if staff_user:
			user = authenticate(request, phone=phone, password=credential)
		else:
			member = Member.objects.select_related("user").filter(phone=phone).first()
			user = None
			if member and member.national_id_hash and check_password(credential, member.national_id_hash):
				user = member.user or User.objects.filter(phone=phone, is_staff=False).first()
				if user is None:
					user = User.objects.create_user(
						phone=phone,
						role="MEMBER",
						is_active=True,
						is_activated=True,
					)
					member.user = user
					member.save(update_fields=["user", "updated_at"])
				elif user.is_active and not user.is_activated:
					user.is_activated = True
					user.save(update_fields=["is_activated"])
				if user and (not user.is_active or user.is_staff):
					user = None
		if user and user.is_active:
			if user.is_staff:
				auth_login(request, user)
			else:
				auth_login(request, user, backend="django.contrib.auth.backends.ModelBackend")
			request.session.set_expiry(60 * 60 * 24 * 30 if form.cleaned_data["remember_me"] else 0)
			return redirect("home")
		form.add_error(None, "ข้อมูลเข้าสู่ระบบไม่ถูกต้อง")
	return render(request, "myapp/auth/login.html", {"form": form})


@require_POST
def logout_view(request):
	auth_logout(request)
	return redirect("login")


@login_required
def profile(request):
	member = getattr(request.user, "member", None)
	if member is None:
		return redirect("scanner" if request.user.is_staff else "login")

	qr_image = None
	qr_expires_at = None
	raw_token = request.session.get("active_qr_token")
	if raw_token:
		qr_record = QRCodeToken.objects.filter(
			member=member,
			token_hash=token_digest(raw_token),
			used_at__isnull=True,
			expires_at__gt=timezone.now(),
		).first()
		if qr_record:
			qr_image = qr_data_uri(raw_token)
			qr_expires_at = qr_record.expires_at
		else:
			request.session.pop("active_qr_token", None)

	latest_membership = member.memberships.order_by("-expire_date").select_related("package").first()
	return render(request, "myapp/profile/profile.html", {
		"member": member,
		"membership": latest_membership,
		"qr_image": qr_image,
		"qr_expires_at": qr_expires_at,
	})


@login_required
@require_POST
def create_qr(request):
	member = getattr(request.user, "member", None)
	if member is None:
		return JsonResponse({"error": "ไม่พบข้อมูลสมาชิก"}, status=403)
	token = issue_qr_token(member)
	request.session["active_qr_token"] = token
	return redirect("profile")


@staff_member_required
def scanner(request):
	return render(request, "myapp/scanner/scanner.html")


@staff_member_required
def display(request):
	return render(request, "myapp/display/display.html")


def checkin_payload(checkin):
	member = checkin.member
	memberships = member.memberships.select_related("package").order_by("-expire_date")
	return {
		"id": checkin.pk,
		"member_code": member.member_code,
		"name": f"{member.first_name} {member.last_name}".strip(),
		"nickname": member.nickname,
		"phone": member.phone,
		"checked_in_at": timezone.localtime(checkin.checkin_time).strftime("%d/%m/%Y %H:%M:%S"),
		"memberships": [
			{
				"package": item.package.package_name,
				"expire_date": item.expire_date.strftime("%d/%m/%Y"),
				"status": item.get_status_display(),
			}
			for item in memberships
		],
	}


@staff_member_required
@require_POST
def scan_qr(request):
	try:
		payload = json.loads(request.body)
		token = payload.get("token", "").strip()
	except (json.JSONDecodeError, AttributeError):
		return JsonResponse({"error": "ข้อมูล QR ไม่ถูกต้อง"}, status=400)
	if not token or len(token) > 128:
		return JsonResponse({"error": "ไม่พบรหัส QR"}, status=400)

	with transaction.atomic():
		qr_record = QRCodeToken.objects.select_for_update().select_related("member").filter(
			token_hash=token_digest(token),
		).first()
		if not qr_record:
			return JsonResponse({"error": "QR ไม่ถูกต้อง"}, status=404)
		if qr_record.used_at:
			return JsonResponse({"error": "QR นี้ถูกใช้แล้ว กรุณาสร้าง QR ใหม่"}, status=409)
		if qr_record.expires_at <= timezone.now():
			return JsonResponse({"error": "QR หมดอายุแล้ว กรุณาสร้างใหม่"}, status=410)

		now = timezone.now()
		qr_record.used_at = now
		qr_record.save(update_fields=["used_at"])
		checkin = CheckIn.objects.create(
			member=qr_record.member,
			method="QR",
			status="SUCCESS",
		)

	return JsonResponse({"ok": True, "member": checkin_payload(checkin)})


@staff_member_required
@require_GET
def latest_checkin(request):
	checkin = CheckIn.objects.filter(status="SUCCESS").select_related("member").order_by(
		"-checkin_time",
		"-pk",
	).first()
	if not checkin:
		return JsonResponse({"checkin": None})
	return JsonResponse({"checkin": checkin_payload(checkin)})


@staff_member_required
def staff_dashboard(request):
	query = request.GET.get("q", "").strip()
	members = Member.objects.select_related("user").order_by("first_name", "last_name")
	if query:
		members = members.filter(
			Q(member_code__icontains=query)
			| Q(first_name__icontains=query)
			| Q(last_name__icontains=query)
			| Q(nickname__icontains=query)
			| Q(phone__icontains=query)
		)
	today = timezone.localdate()
	return render(request, "myapp/staff/dashboard.html", {
		"members": members,
		"query": query,
		"member_count": Member.objects.count(),
		"active_membership_count": Membership.objects.filter(status="ACTIVE").count(),
		"today_checkin_count": CheckIn.objects.filter(checkin_time__date=today, status="SUCCESS").count(),
		"recent_checkins": CheckIn.objects.select_related("member").order_by("-checkin_time")[:8],
	})


@staff_member_required
def member_create(request):
	form = MemberForm(request.POST or None, request.FILES or None)
	if request.method == "POST" and form.is_valid():
		member = form.save()
		messages.success(request, "เพิ่มข้อมูลสมาชิกแล้ว")
		return redirect("staff-member-detail", pk=member.pk)
	return render(request, "myapp/staff/form.html", {
		"form": form,
		"title": "เพิ่มสมาชิก",
		"eyebrow": "NEW MEMBER",
		"cancel_url": "staff-dashboard",
	})


@staff_member_required
def member_detail(request, pk):
	member = get_object_or_404(Member.objects.select_related("user"), pk=pk)
	return render(request, "myapp/staff/member_detail.html", {
		"member": member,
		"national_id": decrypt_national_id(member.national_id_encrypted),
		"memberships": member.memberships.select_related("package").order_by("-expire_date"),
		"checkins": member.checkins.order_by("-checkin_time")[:20],
	})


@staff_member_required
def member_edit(request, pk):
	member = get_object_or_404(Member, pk=pk)
	form = MemberForm(request.POST or None, request.FILES or None, instance=member)
	if request.method == "POST" and form.is_valid():
		with transaction.atomic():
			member = form.save()
			if member.user_id and member.user.phone != member.phone:
				member.user.phone = member.phone
				member.user.save(update_fields=["phone"])
		messages.success(request, "บันทึกการแก้ไขสมาชิกแล้ว")
		return redirect("staff-member-detail", pk=member.pk)
	return render(request, "myapp/staff/form.html", {
		"form": form,
		"title": "แก้ไขข้อมูลสมาชิก",
		"eyebrow": "EDIT MEMBER",
		"cancel_url": "staff-member-detail",
		"cancel_pk": member.pk,
	})


@staff_member_required
def member_delete(request, pk):
	member = get_object_or_404(Member, pk=pk)
	if request.method == "POST":
		user = member.user
		with transaction.atomic():
			member.delete()
			if user and not user.is_staff:
				user.delete()
		messages.success(request, "ลบข้อมูลสมาชิกแล้ว")
		return redirect("staff-dashboard")
	return render(request, "myapp/staff/confirm_delete.html", {
		"title": "ลบสมาชิก",
		"object_name": f"{member.member_code} · {member.first_name} {member.last_name}",
		"warning": "การลบจะลบสมาชิกภาพและประวัติเช็คอินของสมาชิกคนนี้ด้วย",
		"cancel_url": "staff-member-detail",
		"cancel_pk": member.pk,
	})


@staff_member_required
@require_POST
def member_manual_checkin(request, pk):
	member = get_object_or_404(Member, pk=pk)
	CheckIn.objects.create(member=member, method="ADMIN", status="SUCCESS")
	messages.success(request, f"เช็คอิน {member.first_name} {member.last_name} เรียบร้อยแล้ว")
	return redirect("staff-member-detail", pk=member.pk)


@staff_member_required
def membership_create(request, member_pk):
	member = get_object_or_404(Member, pk=member_pk)
	form = MembershipForm(request.POST or None)
	if request.method == "POST" and form.is_valid():
		membership = form.save(commit=False)
		membership.member = member
		membership.save()
		messages.success(request, "เพิ่มสมาชิกภาพแล้ว")
		return redirect("staff-member-detail", pk=member.pk)
	return render(request, "myapp/staff/form.html", {
		"form": form,
		"title": "เพิ่มสมาชิกภาพ",
		"eyebrow": "NEW MEMBERSHIP",
		"cancel_url": "staff-member-detail",
		"cancel_pk": member.pk,
	})


@staff_member_required
def membership_edit(request, pk):
	membership = get_object_or_404(Membership.objects.select_related("member"), pk=pk)
	form = MembershipForm(request.POST or None, instance=membership)
	if request.method == "POST" and form.is_valid():
		form.save()
		messages.success(request, "บันทึกการแก้ไขสมาชิกภาพแล้ว")
		return redirect("staff-member-detail", pk=membership.member_id)
	return render(request, "myapp/staff/form.html", {
		"form": form,
		"title": "แก้ไขสมาชิกภาพ",
		"eyebrow": "EDIT MEMBERSHIP",
		"cancel_url": "staff-member-detail",
		"cancel_pk": membership.member_id,
	})


@staff_member_required
def membership_delete(request, pk):
	membership = get_object_or_404(Membership.objects.select_related("member", "package"), pk=pk)
	member_pk = membership.member_id
	if request.method == "POST":
		membership.delete()
		messages.success(request, "ลบสมาชิกภาพแล้ว")
		return redirect("staff-member-detail", pk=member_pk)
	return render(request, "myapp/staff/confirm_delete.html", {
		"title": "ลบสมาชิกภาพ",
		"object_name": f"{membership.member} · {membership.package}",
		"warning": "รายการนี้จะถูกลบถาวร",
		"cancel_url": "staff-member-detail",
		"cancel_pk": member_pk,
	})


@staff_member_required
def package_list(request):
	return render(request, "myapp/staff/packages.html", {
		"packages": Package.objects.order_by("package_name"),
	})


@staff_member_required
def package_create(request):
	form = PackageForm(request.POST or None)
	if request.method == "POST" and form.is_valid():
		form.save()
		messages.success(request, "เพิ่มแพ็กเกจแล้ว")
		return redirect("staff-packages")
	return render(request, "myapp/staff/form.html", {
		"form": form,
		"title": "เพิ่มแพ็กเกจ",
		"eyebrow": "NEW PACKAGE",
		"cancel_url": "staff-packages",
	})


@staff_member_required
def package_edit(request, pk):
	package = get_object_or_404(Package, pk=pk)
	form = PackageForm(request.POST or None, instance=package)
	if request.method == "POST" and form.is_valid():
		form.save()
		messages.success(request, "บันทึกการแก้ไขแพ็กเกจแล้ว")
		return redirect("staff-packages")
	return render(request, "myapp/staff/form.html", {
		"form": form,
		"title": "แก้ไขแพ็กเกจ",
		"eyebrow": "EDIT PACKAGE",
		"cancel_url": "staff-packages",
	})


@staff_member_required
def package_delete(request, pk):
	package = get_object_or_404(Package, pk=pk)
	if request.method == "POST":
		try:
			package.delete()
		except ProtectedError:
			messages.error(request, "แพ็กเกจนี้มีสมาชิกภาพใช้งานอยู่ จึงลบไม่ได้")
		else:
			messages.success(request, "ลบแพ็กเกจแล้ว")
		return redirect("staff-packages")
	return render(request, "myapp/staff/confirm_delete.html", {
		"title": "ลบแพ็กเกจ",
		"object_name": package.package_name,
		"warning": "แพ็กเกจที่มีสมาชิกภาพอ้างอิงอยู่จะไม่สามารถลบได้",
		"cancel_url": "staff-packages",
	})
