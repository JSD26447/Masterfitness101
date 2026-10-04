import re

from django import forms
from django.contrib.auth.hashers import make_password

from .models import Member, Membership, Package, User
from .services import encrypt_national_id


class PhoneForm(forms.Form):
    phone = forms.CharField(label="เบอร์โทรศัพท์", max_length=10)

    def clean_phone(self):
        phone = self.cleaned_data["phone"].strip()
        if not re.fullmatch(r"0\d{9}", phone):
            raise forms.ValidationError("กรุณากรอกเบอร์โทรศัพท์ 10 หลัก")
        return phone


class LoginForm(PhoneForm):
    phone = forms.CharField(label="เบอร์โทรศัพท์ / ชื่อผู้ดูแลระบบ", max_length=10)
    password = forms.CharField(
        label="เลขบัตรประชาชน (สมาชิก) / รหัสผ่าน (แอดมิน)",
        widget=forms.PasswordInput,
    )
    remember_me = forms.BooleanField(label="จดจำการเข้าสู่ระบบ", required=False)

    def clean_phone(self):
        phone = self.cleaned_data["phone"].strip()
        if re.fullmatch(r"0\d{9}", phone):
            return phone
        if User.objects.filter(phone=phone, is_staff=True, is_active=True).exists():
            return phone
        raise forms.ValidationError("กรุณากรอกเบอร์โทรศัพท์ 10 หลัก หรือชื่อบัญชีผู้ดูแลระบบ")


class MemberForm(forms.ModelForm):
    national_id = forms.CharField(
        label="เลขบัตรประชาชน",
        max_length=13,
        required=False,
        widget=forms.PasswordInput(render_value=False),
        help_text="ใช้เข้าสู่ระบบ ระบบเก็บค่าแบบเข้ารหัสและมี hash สำหรับตรวจรหัส",
    )

    class Meta:
        model = Member
        fields = (
            "member_code",
            "first_name",
            "last_name",
            "nickname",
            "phone",
            "birth_date",
            "gender",
            "photo",
            "line_id",
            "facebook",
        )
        labels = {
            "member_code": "รหัสสมาชิก",
            "first_name": "ชื่อ",
            "last_name": "นามสกุล",
            "nickname": "ชื่อเล่น",
            "phone": "เบอร์โทรศัพท์",
            "birth_date": "วันเกิด",
            "gender": "เพศ",
            "photo": "รูปโปรไฟล์",
            "line_id": "LINE ID",
            "facebook": "Facebook",
        }
        widgets = {"birth_date": forms.DateInput(attrs={"type": "date"})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["national_id"].required = not bool(
            self.instance.pk and self.instance.national_id_hash
        )
        self.order_fields([
            "member_code", "first_name", "last_name", "nickname", "phone",
            "birth_date", "gender", "photo", "national_id", "line_id", "facebook",
        ])

    def clean_phone(self):
        phone = self.cleaned_data["phone"].strip()
        if not re.fullmatch(r"0\d{9}", phone):
            raise forms.ValidationError("กรุณากรอกเบอร์โทรศัพท์ 10 หลัก")
        users = User.objects.filter(phone=phone)
        if self.instance.user_id:
            users = users.exclude(pk=self.instance.user_id)
        if users.exists():
            raise forms.ValidationError("เบอร์นี้ถูกใช้กับบัญชีเข้าสู่ระบบแล้ว")
        return phone

    def clean_national_id(self):
        national_id = self.cleaned_data["national_id"].strip()
        if not national_id:
            if self.instance.pk and self.instance.national_id_hash:
                return ""
            raise forms.ValidationError("กรุณากรอกเลขบัตรประชาชน 13 หลัก")
        if not re.fullmatch(r"\d{13}", national_id):
            raise forms.ValidationError("เลขบัตรประชาชนต้องเป็นตัวเลข 13 หลัก")
        checksum = sum(int(digit) * (13 - index) for index, digit in enumerate(national_id[:12]))
        if (11 - checksum % 11) % 10 != int(national_id[-1]):
            raise forms.ValidationError("เลขบัตรประชาชนไม่ถูกต้อง")
        return national_id

    def save(self, commit=True):
        member = super().save(commit=False)
        national_id = self.cleaned_data.get("national_id")
        if national_id:
            member.national_id_hash = make_password(national_id)
            member.national_id_encrypted = encrypt_national_id(national_id)
        if not commit:
            return member

        member.save()
        self.save_m2m()
        return member


class MembershipForm(forms.ModelForm):
    class Meta:
        model = Membership
        fields = ("package", "start_date", "expire_date", "status")
        labels = {
            "package": "แพ็กเกจ",
            "start_date": "วันที่เริ่มต้น",
            "expire_date": "วันหมดอายุ",
            "status": "สถานะ",
        }
        widgets = {
            "start_date": forms.DateInput(attrs={"type": "date"}),
            "expire_date": forms.DateInput(attrs={"type": "date"}),
        }


class PackageForm(forms.ModelForm):
    class Meta:
        model = Package
        fields = ("package_name", "duration_days", "price", "description", "is_active")
        labels = {
            "package_name": "ชื่อแพ็กเกจ",
            "duration_days": "จำนวนวัน",
            "price": "ราคา (บาท)",
            "description": "รายละเอียด",
            "is_active": "เปิดใช้งานแพ็กเกจ",
        }