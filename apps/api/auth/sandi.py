"""Hash sandi Argon2id."""
from __future__ import annotations

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

# Argon2id, profil RFC 9106 "low memory" (t=3, m=64 MiB, p=4) — melebihi minimum OWASP.
_ph = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=4)
_DUMMY = _ph.hash("sinergi-dummy-untuk-waktu-konstan")


def hash_sandi(sandi: str) -> str:
    return _ph.hash(sandi)


def cocok(hash_tersimpan: str | None, sandi: str) -> bool:
    """Bandingkan sandi. Bila hash tidak ada/rusak tetap memverifikasi hash tiruan agar waktu respons sama."""
    try:
        if not hash_tersimpan or not hash_tersimpan.startswith("$argon2"):
            _ph.verify(_DUMMY, sandi)
            return False
        return _ph.verify(hash_tersimpan, sandi)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def perlu_hash_ulang(hash_tersimpan: str) -> bool:
    return _ph.check_needs_rehash(hash_tersimpan)


def cek_kebijakan(sandi: str, min_panjang: int, username: str) -> str | None:
    """Kembalikan pesan galat bila sandi tidak memenuhi kebijakan, None bila memenuhi."""
    if len(sandi) < min_panjang:
        return f"Sandi minimal {min_panjang} karakter."
    if len(sandi) > 128:
        return "Sandi maksimal 128 karakter."
    if username and username.lower() in sandi.lower():
        return "Sandi tidak boleh memuat nama pengguna."
    if len(set(sandi)) < 5:
        return "Sandi terlalu sederhana."
    return None
