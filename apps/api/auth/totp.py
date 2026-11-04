"""TOTP (RFC 6238) wajib untuk semua peran. Rahasia disimpan terenkripsi (Fernet) di sec.pengguna.totp_secret_enc."""
from __future__ import annotations

import time

import pyotp
import segno
from cryptography.fernet import Fernet, InvalidToken

LANGKAH = 30  # detik
JENDELA = 1  # toleransi +-1 langkah (jam tidak sinkron)


def _fernet(kunci: str) -> Fernet:
    if not kunci:
        raise RuntimeError("SINERGI_FERNET_KEY belum diisi.")
    return Fernet(kunci.encode())


def rahasia_baru() -> str:
    return pyotp.random_base32()


def enkripsi(rahasia: str, kunci: str) -> bytes:
    return _fernet(kunci).encrypt(rahasia.encode())


def dekripsi(data: bytes, kunci: str) -> str:
    try:
        return _fernet(kunci).decrypt(bytes(data)).decode()
    except InvalidToken as e:  # kunci salah/berubah
        raise RuntimeError("Rahasia TOTP tidak dapat dibuka (kunci Fernet berbeda).") from e


def uri_pendaftaran(rahasia: str, username: str, issuer: str) -> str:
    return pyotp.TOTP(rahasia, interval=LANGKAH).provisioning_uri(name=username, issuer_name=issuer)


def qr_svg(uri: str) -> str:
    """Kode QR sebagai data URI SVG (dibuat di server; tidak memanggil layanan luar)."""
    return segno.make(uri, error="m").svg_data_uri(scale=5, border=2)


def verifikasi(rahasia: str, kode: str, langkah_terakhir: int | None, sekarang: float | None = None) -> int | None:
    """Kembalikan nomor langkah waktu yang cocok, atau None.

    Kode yang langkahnya <= langkah_terakhir ditolak (tidak boleh dipakai ulang; ASVS 2.8.4).
    """
    kode = (kode or "").strip().replace(" ", "")
    if not (kode.isdigit() and len(kode) == 6):
        return None
    t = sekarang if sekarang is not None else time.time()
    totp = pyotp.TOTP(rahasia, interval=LANGKAH)
    sekarang_langkah = int(t // LANGKAH)
    for d in range(-JENDELA, JENDELA + 1):
        langkah = sekarang_langkah + d
        if pyotp.utils.strings_equal(totp.generate_otp(langkah), kode):
            if langkah_terakhir is not None and langkah <= langkah_terakhir:
                return None
            return langkah
    return None
