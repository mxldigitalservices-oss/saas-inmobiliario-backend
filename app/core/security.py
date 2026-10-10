import base64
import hashlib
import hmac
import json
import secrets
import time
from datetime import timedelta
from typing import Any, Dict, Optional, Tuple

from app.core.config import settings

_SCRYPT_N = 2 ** 14
_SCRYPT_R = 8
_SCRYPT_P = 1
_LICENSE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
_dummy_hash_cache: Optional[str] = None


def _b64e(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64d(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


# ---------------------------------------------------------------- contraseñas
def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    derived = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=_SCRYPT_N,
        r=_SCRYPT_R,
        p=_SCRYPT_P,
        dklen=32,
    )
    return "scrypt${}${}${}${}${}".format(
        _SCRYPT_N, _SCRYPT_R, _SCRYPT_P, _b64e(salt), _b64e(derived)
    )


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, n, r, p, salt_b64, expected_b64 = stored.split("$")
        if scheme != "scrypt":
            return False
        expected = _b64d(expected_b64)
        derived = hashlib.scrypt(
            password.encode("utf-8"),
            salt=_b64d(salt_b64),
            n=int(n),
            r=int(r),
            p=int(p),
            dklen=len(expected),
        )
        return hmac.compare_digest(derived, expected)
    except Exception:
        return False


def dummy_hash() -> str:
    """Hash falso para igualar tiempos de respuesta cuando el usuario no existe."""
    global _dummy_hash_cache
    if _dummy_hash_cache is None:
        _dummy_hash_cache = hash_password("dummy-password-for-timing")
    return _dummy_hash_cache


# ------------------------------------------------------------------------ JWT
def create_token(
    *,
    subject: str,
    audience: str,
    token_type: str,
    expires_delta: timedelta,
    tenant_id: Optional[str] = None,
    role: Optional[str] = None,
) -> str:
    now = int(time.time())
    payload: Dict[str, Any] = {
        "sub": subject,
        "aud": audience,
        "type": token_type,
        "iat": now,
        "exp": now + int(expires_delta.total_seconds()),
        "jti": secrets.token_hex(8),
    }
    if tenant_id:
        payload["tenant_id"] = tenant_id
    if role:
        payload["role"] = role
    header = {"alg": "HS256", "typ": "JWT"}
    signing_input = "{}.{}".format(
        _b64e(json.dumps(header, separators=(",", ":")).encode("utf-8")),
        _b64e(json.dumps(payload, separators=(",", ":")).encode("utf-8")),
    )
    signature = hmac.new(
        settings.JWT_SECRET.encode("utf-8"),
        signing_input.encode("ascii"),
        hashlib.sha256,
    ).digest()
    return "{}.{}".format(signing_input, _b64e(signature))


def decode_token(token: str, *, expected_type: str, expected_audience: str) -> Dict[str, Any]:
    """Valida firma, expiración, tipo y audiencia. Lanza ValueError si algo falla."""
    try:
        header_b64, payload_b64, signature_b64 = token.split(".")
    except ValueError:
        raise ValueError("Token malformado")
    signing_input = "{}.{}".format(header_b64, payload_b64)
    expected_sig = hmac.new(
        settings.JWT_SECRET.encode("utf-8"),
        signing_input.encode("ascii"),
        hashlib.sha256,
    ).digest()
    if not hmac.compare_digest(expected_sig, _b64d(signature_b64)):
        raise ValueError("Firma inválida")
    header = json.loads(_b64d(header_b64))
    if header.get("alg") != "HS256":
        raise ValueError("Algoritmo no soportado")
    payload = json.loads(_b64d(payload_b64))
    if int(payload.get("exp", 0)) < int(time.time()):
        raise ValueError("Token expirado")
    if payload.get("type") != expected_type:
        raise ValueError("Tipo de token incorrecto")
    if payload.get("aud") != expected_audience:
        raise ValueError("Audiencia incorrecta")
    if not payload.get("sub"):
        raise ValueError("Token sin sujeto")
    return payload


# ------------------------------------------------------------ tokens de licencia
def normalize_license_token(token: str) -> str:
    return token.strip().upper()


def hash_license_token(token: str) -> str:
    return hashlib.sha256(normalize_license_token(token).encode("utf-8")).hexdigest()


def generate_license_token() -> Tuple[str, str, str]:
    """Devuelve (token_en_claro, prefijo, hash). El claro se muestra una sola vez."""
    groups = [
        "".join(secrets.choice(_LICENSE_ALPHABET) for _ in range(4)) for _ in range(4)
    ]
    raw = "MGO-" + "-".join(groups)
    return raw, raw[:8], hash_license_token(raw)
