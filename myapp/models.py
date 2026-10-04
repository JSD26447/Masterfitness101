from django.db import models
from django.contrib.auth.models import AbstractUser, BaseUserManager


# =========================================
# USER MANAGER
# =========================================
class UserManager(BaseUserManager):

    def create_user(self, phone, password=None, **extra_fields):
        if not phone:
            raise ValueError("กรุณาระบุเบอร์โทรศัพท์")

        user = self.model(phone=phone, **extra_fields)

        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()

        user.save(using=self._db)
        return user

    def create_superuser(self, phone, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_active", True)
        extra_fields.setdefault("is_activated", True)
        extra_fields.setdefault("role", "ADMIN")

        return self.create_user(phone, password, **extra_fields)


# =========================================
# USER
# สำหรับ Login
# =========================================
class User(AbstractUser):

    ROLE_CHOICES = [
        ("ADMIN", "Admin"),
        ("MEMBER", "Member"),
    ]

    username = None

    phone = models.CharField(
        max_length=10,
        unique=True
    )

    role = models.CharField(
        max_length=10,
        choices=ROLE_CHOICES,
        default="MEMBER"
    )

    is_activated = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)

    USERNAME_FIELD = "phone"
    REQUIRED_FIELDS = []

    objects = UserManager()

    def __str__(self):
        return self.phone


# =========================================
# MEMBER
# ข้อมูลสมาชิกฟิตเนส
# =========================================
class Member(models.Model):

    user = models.OneToOneField(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="member"
    )

    member_code = models.CharField(
        max_length=20,
        unique=True
    )

    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)

    nickname = models.CharField(
        max_length=50,
        blank=True
    )

    phone = models.CharField(
        max_length=10,
        unique=True
    )

    national_id_hash = models.CharField(
        max_length=128,
        blank=True,
        editable=False
    )

    national_id_encrypted = models.TextField(
        blank=True,
        editable=False
    )

    birth_date = models.DateField(
        null=True,
        blank=True
    )

    gender = models.CharField(
        max_length=20,
        blank=True
    )

    photo = models.ImageField(
        upload_to="members/",
        null=True,
        blank=True
    )

    line_id = models.CharField(
        max_length=100,
        blank=True
    )

    facebook = models.CharField(
        max_length=200,
        blank=True
    )

    created_at = models.DateTimeField(auto_now_add=True)

    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.member_code} - {self.first_name} {self.last_name}"


# =========================================
# PACKAGE
# แพ็กเกจฟิตเนส
# =========================================
class Package(models.Model):

    package_name = models.CharField(max_length=100)

    duration_days = models.PositiveIntegerField()

    price = models.DecimalField(
        max_digits=10,
        decimal_places=2
    )

    description = models.TextField(blank=True)

    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.package_name


# =========================================
# MEMBERSHIP
# สมาชิกใช้ Package อะไร
# =========================================
class Membership(models.Model):

    STATUS_CHOICES = [
        ("ACTIVE", "ใช้งานได้"),
        ("EXPIRED", "หมดอายุ"),
        ("CANCELLED", "ยกเลิก"),
    ]

    member = models.ForeignKey(
        Member,
        on_delete=models.CASCADE,
        related_name="memberships"
    )

    package = models.ForeignKey(
        Package,
        on_delete=models.PROTECT,
        related_name="memberships"
    )

    start_date = models.DateField()

    expire_date = models.DateField()

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="ACTIVE"
    )

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.member} - {self.package}"


# =========================================
# CHECK-IN
# ประวัติเข้าฟิตเนส
# =========================================
class CheckIn(models.Model):

    METHOD_CHOICES = [
        ("QR", "QR Code"),
        ("ADMIN", "Admin"),
    ]

    STATUS_CHOICES = [
        ("SUCCESS", "สำเร็จ"),
        ("FAILED", "ไม่สำเร็จ"),
    ]

    member = models.ForeignKey(
        Member,
        on_delete=models.CASCADE,
        related_name="checkins"
    )

    checkin_time = models.DateTimeField(auto_now_add=True)

    method = models.CharField(
        max_length=20,
        choices=METHOD_CHOICES,
        default="QR"
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="SUCCESS"
    )

    def __str__(self):
        return f"{self.member} - {self.checkin_time}"


# =========================================
# OTP
# =========================================
class OTPVerification(models.Model):

    phone = models.CharField(max_length=10)

    # ไม่ควรเก็บ OTP จริงเป็น plain text
    otp_hash = models.CharField(max_length=255)

    expires_at = models.DateTimeField()

    is_used = models.BooleanField(default=False)

    attempt_count = models.PositiveIntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.phone


class QRCodeToken(models.Model):
    member = models.ForeignKey(
        Member,
        on_delete=models.CASCADE,
        related_name="qr_tokens"
    )
    token_hash = models.CharField(max_length=64, unique=True)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.member} - {self.expires_at}"