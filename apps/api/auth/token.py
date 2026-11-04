"""Token akses (JWT 15 menit), token pra-TOTP, token refresh berotasi, dan token CSRF bertanda tangan."""
from __future__ import annotations

import hashlib
import hmac
import secrets
import time
import uuid
from dataclasses import dataclass

import jwt

ALG = "HS256"


@dataclass(frozen=True)
class KlaimAkses:
    user_id: int
    sesi_id: str


def _buat(rahasia: str, isi: dict, umur_detik: int) -> str:
    now = int(time.time())
    return jwt.encode({**isi, "iat": now, "exp": now + umur_detik, "jti": uuid.uuid4().hex}, rahasia, algorithm=ALG)


def _baca(rahasia: str, token: str, jenis: str) -> dict | None:
    try:
        isi = jwt.decode(token, rahasia, algorithms=[ALG], options={"require": ["exp", "iat", "sub", "typ"]})
    except jwt.PyJWTError:
        return None
    return isi if isi.get("typ") == jenis else None


def buat_akses(rahasia: str, user_id: int, sesi_id: str, menit: int) -> str:
    return _buat(rahasia, {"sub": str(user_id), "sid": sesi_id, "typ": "akses"}, menit * 60)


def baca_akses(rahasia: str, token: str) -> KlaimAkses | None:
    isi = _baca(rahasia, token, "akses")
    if not isi or "sid" not in isi:
        return None
    try:
        return KlaimAkses(int(isi["sub"]), str(isi["sid"]))
    except (TypeError, ValueError):
        return None


def buat_pra(rahasia: str, user_id: int, menit: int) -> str:
    """Token setelah sandi benar, sebelum TOTP. Tidak memberi akses ke data."""
    return _buat(rahasia, {"sub": str(user_id), "typ": "pra"}, menit * 60)


def baca_pra(rahasia: str, token: str) -> int | None:
    isi = _baca(rahasia, token, "pra")
    try:
        return int(isi["sub"]) if isi else None
    except (TypeError, ValueError):
        return None


def refresh_baru(sesi_id: str) -> tuple[str, str]:
    """Kembalikan (token untuk cookie, hash SHA-256 untuk sec.sesi.refresh_hash). Token mentah tidak disimpan."""
    rahasia = secrets.token_urlsafe(32)
    return f"{sesi_id}.{rahasia}", hash_refresh(rahasia)


def hash_refresh(rahasia: str) -> str:
    return hashlib.sha256(rahasia.encode()).hexdigest()


def pecah_refresh(token: str) -> tuple[str, str] | None:
    if not token or "." not in token:
        return None
    sid, rahasia = token.split(".", 1)
    try:
        uuid.UUID(sid)
    except ValueError:
        return None
    return sid, rahasia


def csrf_baru(kunci: str) -> str:
    acak = secrets.token_urlsafe(24)
    sig = hmac.new(kunci.encode(), acak.encode(), hashlib.sha256).hexdigest()[:32]
    return f"{acak}.{sig}"


def csrf_sah(kunci: str, cookie: str | None, header: str | None) -> bool:
    """Double-submit bertanda tangan: cookie == header dan tanda tangan HMAC sah."""
    if not cookie or not header or not hmac.compare_digest(cookie, header) or "." not in cookie:
        return False
    acak, sig = cookie.rsplit(".", 1)
    harap = hmac.new(kunci.encode(), acak.encode(), hashlib.sha256).hexdigest()[:32]
    return hmac.compare_digest(sig, harap)
