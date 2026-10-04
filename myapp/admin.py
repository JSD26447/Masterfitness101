from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .forms import MemberForm
from .models import CheckIn, Member, Membership, OTPVerification, Package, QRCodeToken, User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
	ordering = ("phone",)
	list_display = ("phone", "role", "is_activated", "is_staff", "is_active")
	search_fields = ("phone",)
	fieldsets = (
		(None, {"fields": ("phone", "password")}),
		("สิทธิ์และสถานะ", {"fields": ("role", "is_activated", "is_active", "is_staff", "is_superuser", "groups", "user_permissions")}),
		("วันที่", {"fields": ("last_login", "date_joined", "created_at")}),
	)
	add_fieldsets = (
		(None, {"classes": ("wide",), "fields": ("phone", "password1", "password2", "role", "is_staff", "is_active")}),
	)
	readonly_fields = ("created_at", "date_joined", "last_login")


@admin.register(Member)
class MemberAdmin(admin.ModelAdmin):
	form = MemberForm
	list_display = ("member_code", "first_name", "last_name", "nickname", "phone", "user")
	search_fields = ("member_code", "first_name", "last_name", "nickname", "phone")
	list_filter = ("gender",)


@admin.register(Package)
class PackageAdmin(admin.ModelAdmin):
	list_display = ("package_name", "duration_days", "price", "is_active")
	list_filter = ("is_active",)
	search_fields = ("package_name",)


@admin.register(Membership)
class MembershipAdmin(admin.ModelAdmin):
	list_display = ("member", "package", "start_date", "expire_date", "status")
	list_filter = ("status", "package")
	search_fields = ("member__member_code", "member__phone", "member__first_name")


@admin.register(CheckIn)
class CheckInAdmin(admin.ModelAdmin):
	list_display = ("member", "checkin_time", "method", "status")
	list_filter = ("status", "method", "checkin_time")
	search_fields = ("member__member_code", "member__phone", "member__first_name")
	readonly_fields = ("member", "checkin_time", "method", "status")


@admin.register(OTPVerification)
class OTPVerificationAdmin(admin.ModelAdmin):
	list_display = ("phone", "expires_at", "is_used", "attempt_count", "created_at")
	list_filter = ("is_used", "created_at")
	search_fields = ("phone",)
	readonly_fields = ("phone", "otp_hash", "expires_at", "is_used", "attempt_count", "created_at")


@admin.register(QRCodeToken)
class QRCodeTokenAdmin(admin.ModelAdmin):
	list_display = ("member", "expires_at", "used_at", "created_at")
	list_filter = ("expires_at", "used_at")
	search_fields = ("member__member_code", "member__phone")
	readonly_fields = ("member", "token_hash", "expires_at", "used_at", "created_at")
