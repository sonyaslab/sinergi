"""Uji API autentikasi: sandi + TOTP wajib, pendaftaran TOTP, kunci akun, CSRF, rotasi refresh, logout, ganti sandi."""
from __future__ import annotations

import pyotp
import pytest

from tests.conftest import SANDI_UJI, csrf, masuk

pytestmark = pytest.mark.db


def _audit(admin_conn, uid: int) -> list[str]:
    return [r[0] for r in admin_conn.execute(
        "SELECT aksi FROM audit.log WHERE pengguna_id = %s ORDER BY id", (uid,)).fetchall()]


def test_login_lengkap_dengan_pendaftaran_totp(klien, buat_akun, jam, admin_conn):
    akun = buat_akun(["operator"], totp_aktif=False)
    h = csrf(klien)
    r = klien.post("/api/auth/login", json={"username": akun.username, "sandi": akun.sandi}, headers=h)
    assert r.status_code == 200
    d = r.json()
    assert d["tahap"] == "daftar_totp" and d["qr_svg"].startswith("data:image/svg+xml") and d["rahasia"]
    # Sandi benar saja belum memberi akses.
    assert klien.get("/api/tahun-dasar").status_code == 401
    r = klien.post("/api/auth/totp", json={"kode": jam.kode(d["rahasia"])}, headers=h)
    assert r.status_code == 200, r.text
    profil = r.json()
    assert profil["username"] == akun.username and "data_dasar.isi" in profil["izin"]
    assert {"sinergi_akses", "sinergi_refresh"} <= set(klien.cookies.keys())
    assert klien.get("/api/auth/saya").json()["peran"] == ["operator"]
    aksi = _audit(admin_conn, akun.id)
    assert "TOTP_DAFTAR" in aksi and "LOGIN" in aksi
    # Login berikutnya langsung tahap TOTP (rahasia tidak dikirim lagi).
    r = klien.post("/api/auth/login", json={"username": akun.username, "sandi": akun.sandi}, headers=h)
    assert r.json() == {"tahap": "totp", "qr_svg": None, "rahasia": None}


def test_totp_salah_dan_dipakai_ulang_ditolak(klien, buat_akun, jam):
    akun = buat_akun()
    h = csrf(klien)
    klien.post("/api/auth/login", json={"username": akun.username, "sandi": akun.sandi}, headers=h)
    r = klien.post("/api/auth/totp", json={"kode": "000000"}, headers=h)
    assert r.status_code == 401 and r.json()["kode"] == "TOTP_SALAH"
    kode = jam.kode(akun.rahasia)
    assert klien.post("/api/auth/totp", json={"kode": kode}, headers=h).status_code == 200
    klien.post("/api/auth/login", json={"username": akun.username, "sandi": akun.sandi}, headers=h)
    r = klien.post("/api/auth/totp", json={"kode": kode}, headers=h)  # kode yang sama
    assert r.status_code == 401


def test_sandi_salah_pesan_umum(klien, buat_akun):
    akun = buat_akun()
    h = csrf(klien)
    r1 = klien.post("/api/auth/login", json={"username": akun.username, "sandi": "salah"}, headers=h)
    r2 = klien.post("/api/auth/login", json={"username": "tidak.ada", "sandi": "salah"}, headers=h)
    assert r1.status_code == r2.status_code == 401
    assert r1.json()["pesan"] == r2.json()["pesan"] == "Nama pengguna atau sandi salah."


def test_kunci_akun_setelah_5_gagal(klien, buat_akun, admin_conn):
    akun = buat_akun()
    h = csrf(klien)
    kode = []
    for _ in range(5):
        kode.append(klien.post("/api/auth/login", json={"username": akun.username, "sandi": "salah"},
                               headers=h).status_code)
    assert kode == [401, 401, 401, 401, 429]
    r = klien.post("/api/auth/login", json={"username": akun.username, "sandi": akun.sandi}, headers=h)
    assert r.status_code == 429 and "terkunci" in r.json()["pesan"].lower()
    assert "AKUN_TERKUNCI" in _audit(admin_conn, akun.id)
    # Setelah masa kunci lewat, sandi benar diterima.
    admin_conn.execute("UPDATE sec.pengguna SET terkunci_sampai = now() - interval '1 minute' WHERE id = %s",
                       (akun.id,))
    r = klien.post("/api/auth/login", json={"username": akun.username, "sandi": akun.sandi}, headers=h)
    assert r.status_code == 200


def test_csrf_wajib_untuk_post(klien, buat_akun):
    akun = buat_akun()
    r = klien.post("/api/auth/login", json={"username": akun.username, "sandi": akun.sandi})
    assert r.status_code == 403 and r.json()["kode"] == "CSRF"
    csrf(klien)
    r = klien.post("/api/auth/login", json={"username": akun.username, "sandi": akun.sandi},
                   headers={"X-CSRF-Token": "palsu.palsu"})
    assert r.status_code == 403


def _klien_lain(klien):
    """Klien terpisah (mis. penyerang yang memegang token curian) tanpa cookie jar bersama."""
    from fastapi.testclient import TestClient

    return TestClient(klien.app, base_url="http://testserver")


def test_refresh_berotasi_dan_pakai_ulang_mencabut_sesi(klien, buat_akun, jam, admin_conn):
    akun = buat_akun()
    h = masuk(klien, akun, jam)
    lama = klien.cookies.get("sinergi_refresh")
    r = klien.post("/api/auth/refresh", headers=h)
    assert r.status_code == 200
    baru = klien.cookies.get("sinergi_refresh")
    assert baru and baru != lama and baru.split(".")[0] == lama.split(".")[0]
    # Token lama dipakai ulang oleh pihak lain -> seluruh sesi dicabut.
    t = h["X-CSRF-Token"]
    with _klien_lain(klien) as lain:
        r = lain.post("/api/auth/refresh", headers={**h, "Cookie": f"sinergi_csrf={t}; sinergi_refresh={lama}"})
        assert r.status_code == 401
    assert klien.post("/api/auth/refresh", headers=h).status_code == 401  # pemilik sah juga harus login ulang
    assert "REFRESH_PAKAI_ULANG" in _audit(admin_conn, akun.id)


def test_logout_mencabut_sesi(klien, buat_akun, jam, admin_conn):
    akun = buat_akun()
    h = masuk(klien, akun, jam)
    akses = klien.cookies.get("sinergi_akses")
    assert klien.get("/api/auth/saya").status_code == 200
    assert klien.post("/api/auth/logout", headers=h).status_code == 200
    assert klien.get("/api/auth/saya").status_code == 401
    with _klien_lain(klien) as lain:  # token akses lama (belum kedaluwarsa) tidak berlaku lagi
        assert lain.get("/api/auth/saya", headers={"Cookie": f"sinergi_akses={akses}"}).status_code == 401
    assert "LOGOUT" in _audit(admin_conn, akun.id)


def test_sesi_idle_dicabut(klien, buat_akun, jam, admin_conn):
    akun = buat_akun()
    masuk(klien, akun, jam)
    admin_conn.execute("UPDATE sec.sesi SET aktif_terakhir = now() - interval '2 hours' WHERE pengguna_id = %s",
                       (akun.id,))
    r = klien.get("/api/auth/saya")
    assert r.status_code == 401 and r.json()["kode"] == "SESI_IDLE"


def test_wajib_ganti_sandi_awal(klien, buat_akun, jam):
    akun = buat_akun(["supervisor"], wajib_ganti=True)
    h = masuk(klien, akun, jam)
    r = klien.get("/api/tahun-dasar")
    assert r.status_code == 403 and r.json()["kode"] == "WAJIB_GANTI_SANDI"
    r = klien.post("/api/auth/ganti-sandi", json={"sandi_lama": SANDI_UJI, "sandi_baru": "pendek"}, headers=h)
    assert r.status_code == 422 and "minimal" in r.json()["pesan"]
    r = klien.post("/api/auth/ganti-sandi", json={"sandi_lama": "salah", "sandi_baru": "Neraca-Kaltara-2026"},
                   headers=h)
    assert r.status_code == 422
    r = klien.post("/api/auth/ganti-sandi", json={"sandi_lama": SANDI_UJI, "sandi_baru": "Neraca-Kaltara-2026"},
                   headers=h)
    assert r.status_code == 200
    td = klien.get("/api/tahun-dasar").json()
    assert [t["kode"] for t in td] == ["TD2010", "TD2025"]  # urut status: produksi lalu paralel (dari master)


def test_cookie_aman_di_produksi(monkeypatch):
    from fastapi import Response
    from sinergi_api.app import config, keamanan_http

    monkeypatch.setattr(config.pengaturan(), "cookie_secure", True)
    r = Response()
    keamanan_http.setel_cookie(r, keamanan_http.COOKIE_AKSES, "x", 900, "/api")
    sc = r.headers["set-cookie"].lower()
    assert sc.startswith("sinergi_akses=") and "httponly" in sc and "secure" in sc and "samesite=strict" in sc


def test_qr_tidak_bocor_setelah_aktif(klien, buat_akun, jam):
    akun = buat_akun()
    h = csrf(klien)
    r = klien.post("/api/auth/login", json={"username": akun.username, "sandi": akun.sandi}, headers=h)
    assert r.json()["rahasia"] is None
    assert pyotp.TOTP(akun.rahasia).now()  # sanity
