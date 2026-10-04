import base64
import hashlib
import io
import logging
import os
import secrets
from datetime import timedelta
from pathlib import Path

import qrcode
from cryptography.fernet import Fernet
from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.core.exceptions import ImproperlyConfigured
from django.utils import timezone

from .models import OTPVerification, QRCodeToken


logger = logging.getLogger(__name__)
OTP_LIFETIME = timedelta(minutes=5)
QR_LIFETIME = timedelta(minutes=5)
OTP_MAX_ATTEMPTS = 5
OTP_MAX_REQUESTS_PER_HOUR = 5


def _national_id_cipher():
    key = getattr(settings, "NATIONAL_ID_ENCRYPTION_KEY", "")
    if key:
        try:
            return Fernet(key.encode("ascii"))
        except (ValueError, UnicodeEncodeError):
            pass
        derived_key = base64.urlsafe_b64encode(hashlib.sha256(key.encode("utf-8")).digest())
        return Fernet(derived_key)
    if not settings.DEBUG:
        raise ImproperlyConfigured("Set NATIONAL_ID_ENCRYPTION_KEY before storing national IDs.")

    app_data = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    key_path = app_data / "MasterFitness" / "national-id.key"
    key_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with key_path.open("xb") as key_file:
            key_file.write(Fernet.generate_key())
    except FileExistsError:
        pass
    return Fernet(key_path.read_bytes().strip())


def encrypt_national_id(value):
    return _national_id_cipher().encrypt(value.encode("ascii")).decode("ascii")


def decrypt_national_id(value):
    if not value:
        return ""
    return _national_id_cipher().decrypt(value.encode("ascii")).decode("ascii")


def token_digest(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def send_otp(phone, code):
    backend = getattr(settings, "OTP_DELIVERY_BACKEND", "console")
    if backend == "console":
        if not settings.DEBUG:
            raise RuntimeError("Console OTP delivery is only allowed in DEBUG mode.")
        logger.warning("Development OTP for %s: %s", phone, code)
        return

    from django.utils.module_loading import import_string

    import_string(backend)(phone, code)


def issue_otp(phone):
    now = timezone.now()
    recent_requests = OTPVerification.objects.filter(
        phone=phone,
        created_at__gte=now - timedelta(hours=1),
    ).count()
    latest = OTPVerification.objects.filter(phone=phone).order_by("-created_at").first()
    if recent_requests >= OTP_MAX_REQUESTS_PER_HOUR:
        return False
    if latest and latest.created_at > now - timedelta(seconds=60):
        return False

    OTPVerification.objects.filter(phone=phone, is_used=False).update(is_used=True)
    code = f"{secrets.randbelow(1_000_000):06d}"
    OTPVerification.objects.create(
        phone=phone,
        otp_hash=make_password(code),
        expires_at=now + OTP_LIFETIME,
    )
    send_otp(phone, code)
    return True


def verify_otp(phone, code):
    verification = OTPVerification.objects.filter(
        phone=phone,
        is_used=False,
    ).order_by("-created_at").first()
    if not verification:
        return False
    if verification.expires_at <= timezone.now() or verification.attempt_count >= OTP_MAX_ATTEMPTS:
        verification.is_used = True
        verification.save(update_fields=["is_used"])
        return False

    verification.attempt_count += 1
    valid = check_password(code, verification.otp_hash)
    if valid:
        verification.is_used = True
    verification.save(update_fields=["attempt_count", "is_used"])
    return valid


def issue_qr_token(member):
    now = timezone.now()
    QRCodeToken.objects.filter(
        member=member,
        used_at__isnull=True,
        expires_at__gt=now,
    ).update(expires_at=now)
    token = secrets.token_urlsafe(32)
    QRCodeToken.objects.create(
        member=member,
        token_hash=token_digest(token),
        expires_at=now + QR_LIFETIME,
    )
    return token


def qr_data_uri(value):
    image = qrcode.make(value)
    output = io.BytesIO()
    image.save(output, format="PNG")
    encoded = base64.b64encode(output.getvalue()).decode("ascii")
    return f"data:image/png;base64,{encoded}"