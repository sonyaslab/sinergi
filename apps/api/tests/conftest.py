"""Fixture uji. Basis data uji `sinergi_test` dibuat ulang sekali per sesi lewat migrasi Alembic.

Lingkungan:
  SINERGI_DB_ADMIN_URL  superuser (bawaan postgresql://postgres:postgres@localhost:5432/postgres)
  SINERGI_DB_URL, SINERGI_DB_URL_RO, SINERGI_DB_URL_OWNER  (nama DB diganti menjadi sinergi_test)
"""
from __future__ import annotations

import os
import secrets
import types
from collections.abc import Iterator
from dataclasses import dataclass

import pyotp
import pytest
from cryptography.fernet import Fernet
from sqlalchemy.engine import make_url

DB_UJI = "sinergi_test"


def _ke_db_uji(url: str) -> str:
    return make_url(url).set(database=DB_UJI).render_as_string(hide_password=False)


# Peran dan sandi sama dengan lingkungan pengembangan (.env / bawaan Pengaturan); hanya nama DB yang diganti.
os.environ.setdefault("SINERGI_DB_ADMIN_URL", "postgresql://postgres:postgres@localhost:5432/postgres")
os.environ["SINERGI_LINGKUNGAN"] = "uji"
from sinergi_api.app.config import Pengaturan as _P  # noqa: E402

_p = _P()
os.environ["SINERGI_DB_URL"] = _ke_db_uji(_p.db_url)
os.environ["SINERGI_DB_URL_RO"] = _ke_db_uji(_p.db_url_ro)
os.environ["SINERGI_DB_URL_OWNER"] = _ke_db_uji(_p.db_url_owner)
os.environ["SINERGI_JWT_SECRET"] = secrets.token_hex(32)
os.environ["SINERGI_FERNET_KEY"] = Fernet.generate_key().decode()
os.environ["SINERGI_COOKIE_SECURE"] = "false"  # TestClient memakai http://testserver

from sinergi_api import dbadmin  # noqa: E402
from sinergi_api.app import db  # noqa: E402
from sinergi_api.app.config import Pengaturan, pengaturan  # noqa: E402
from sinergi_api.auth import sandi as sd  # noqa: E402
from sinergi_api.auth import totp  # noqa: E402

SANDI_UJI = "Sandi-Uji-Kaltara-2026"


@pytest.fixture(scope="session")
def basis_data() -> Iterator[None]:
    """Buat ulang sinergi_test (peran + DB + alembic upgrade head)."""
    p = Pengaturan()
    try:
        dbadmin.reset(p, DB_UJI)
    except Exception as e:  # pragma: no cover - lingkungan tanpa PostgreSQL
        if os.environ.get("SINERGI_LEWATI_DB") == "1":
            pytest.skip(f"PostgreSQL tidak tersedia: {e}")
        raise
    pengaturan.cache_clear()
    db.engine_rw.cache_clear()
    db.engine_ro.cache_clear()
    yield
    db.engine_rw().dispose()
    db.engine_ro().dispose()


@pytest.fixture(scope="session")
def admin_conn(basis_data):
    """Koneksi pemilik (app_owner) untuk menyiapkan data uji tanpa RLS."""
    import psycopg

    dsn = make_url(os.environ["SINERGI_DB_URL_OWNER"]).set(drivername="postgresql").render_as_string(
        hide_password=False)
    with psycopg.connect(dsn, autocommit=True) as c:
        yield c


@dataclass
class Akun:
    id: int
    username: str
    sandi: str
    rahasia: str | None


@pytest.fixture
def buat_akun(admin_conn):
    """Pabrik akun uji: buat_akun(peran=['operator'], totp=True, wajib_ganti=False)."""

    def _buat(peran: list[str] | tuple[str, ...] = ("operator",), totp_aktif: bool = True,
              wajib_ganti: bool = False, sandi: str = SANDI_UJI) -> Akun:
        username = f"uji.{secrets.token_hex(4)}"
        rahasia = totp.rahasia_baru() if totp_aktif else None
        enc = totp.enkripsi(rahasia, pengaturan().fernet_key) if rahasia else None
        uid = admin_conn.execute(
            "INSERT INTO sec.pengguna (username, nama, password_hash, totp_secret_enc, totp_aktif, wajib_ganti_sandi)"
            " VALUES (%s, %s, %s, %s, %s, %s) RETURNING id",
            (username, f"Pengguna {username}", sd.hash_sandi(sandi), enc, totp_aktif, wajib_ganti),
        ).fetchone()[0]
        for k in peran:
            admin_conn.execute("INSERT INTO sec.pengguna_peran SELECT %s, id FROM sec.peran WHERE kode = %s", (uid, k))
        return Akun(uid, username, sandi, rahasia)

    return _buat


@pytest.fixture
def jam(monkeypatch):
    """Jam palsu untuk modul TOTP; tiap kode baru memakai langkah waktu berikutnya (kode tidak boleh dipakai ulang)."""
    import time as _time

    st = {"t": float(int(_time.time() // 30) * 30)}
    monkeypatch.setattr(totp, "time", types.SimpleNamespace(time=lambda: st["t"]))

    class Jam:
        def kode(self, rahasia: str, maju: bool = True) -> str:
            if maju:
                st["t"] += 30
            return pyotp.TOTP(rahasia).at(st["t"])

        def maju(self, detik: float) -> None:
            st["t"] += detik

    return Jam()


@pytest.fixture
def klien(basis_data):
    from fastapi.testclient import TestClient

    from sinergi_api.app.main import buat_app

    with TestClient(buat_app(), base_url="http://testserver") as c:
        yield c


def csrf(c) -> dict[str, str]:
    r = c.get("/api/auth/csrf")
    assert r.status_code == 200
    return {"X-CSRF-Token": r.json()["csrf"]}


def masuk(c, akun: Akun, jam) -> dict[str, str]:
    """Login lengkap (sandi + TOTP). Kembalikan header CSRF untuk permintaan berikutnya."""
    h = csrf(c)
    r = c.post("/api/auth/login", json={"username": akun.username, "sandi": akun.sandi}, headers=h)
    assert r.status_code == 200, r.text
    assert akun.rahasia
    r = c.post("/api/auth/totp", json={"kode": jam.kode(akun.rahasia)}, headers=h)
    assert r.status_code == 200, r.text
    return h


@pytest.fixture
def sebagai(klien, buat_akun, jam):
    """Login sebagai peran tertentu: h = sebagai('admin') -> header CSRF; klien sudah memegang cookie sesi."""

    def _masuk(*peran: str) -> dict[str, str]:
        klien.cookies.clear()
        akun = buat_akun(list(peran))
        h = masuk(klien, akun, jam)
        h["_uid"] = str(akun.id)
        return h

    return _masuk


def tanpa_uid(h: dict[str, str]) -> dict[str, str]:
    return {k: v for k, v in h.items() if not k.startswith("_")}


@pytest.fixture
def td_uji(klien, admin_conn):
    """Pabrik tahun dasar uji berisi salinan pohon TD2025 (memerlukan klien yang login sebagai admin)."""

    def _buat(h: dict[str, str]) -> dict:
        kode = f"TD{secrets.randbelow(9000) + 1000}"
        sumber = admin_conn.execute("SELECT id FROM ref.tahun_dasar WHERE kode = 'TD2025'").fetchone()[0]
        r = klien.post("/api/tahun-dasar", headers=tanpa_uid(h), json={
            "kode": kode, "tahun_dasar": 2025, "status": "rencana", "klasifikasi": "KBLI2025",
            "tahun_awal_seri": 2019, "tahun_baseline_eks": 2025, "salin_pohon_dari": sumber})
        assert r.status_code == 201, r.text
        return r.json()

    return _buat
