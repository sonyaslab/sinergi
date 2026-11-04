"""Konfigurasi dari variabel lingkungan berprefiks SINERGI_ (lihat .env.example). Tidak ada rahasia di kode."""
from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Pengaturan(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SINERGI_", env_file=".env", extra="ignore")

    # Koneksi basis data. Aplikasi = app_rw (RLS berlaku), laporan = app_ro, migrasi = app_owner.
    db_url: str = "postgresql+psycopg://app_rw:ganti@localhost:5432/sinergi"
    db_url_ro: str = "postgresql+psycopg://app_ro:ganti@localhost:5432/sinergi"
    db_url_owner: str = "postgresql+psycopg://app_owner:ganti@localhost:5432/sinergi"

    # Rahasia (wajib diganti di produksi; lihat .env.example).
    jwt_secret: str = Field(default="", min_length=0)
    fernet_key: str = ""  # kunci enkripsi rahasia TOTP (cryptography.fernet)

    # Sesi
    akses_menit: int = 15  # masa berlaku token akses
    refresh_jam: int = 8  # masa berlaku sesi (refresh) maksimum
    idle_menit: int = 60  # sesi dicabut bila tidak aktif selama ini
    pra_totp_menit: int = 5  # jeda antara sandi benar dan kode TOTP

    # Kunci akun
    maks_gagal_login: int = 5
    kunci_menit: int = 15

    # Cookie
    cookie_secure: bool = True
    totp_issuer: str = "SINERGI"
    sandi_min_panjang: int = 12

    lingkungan: str = "produksi"  # produksi | pengembangan | uji


@lru_cache
def pengaturan() -> Pengaturan:
    p = Pengaturan()
    if p.lingkungan == "produksi" and (len(p.jwt_secret) < 32 or not p.fernet_key):
        raise RuntimeError("SINERGI_JWT_SECRET (>= 32 karakter) dan SINERGI_FERNET_KEY wajib diisi di produksi.")
    return p
