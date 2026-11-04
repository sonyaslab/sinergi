"""Uji unit: hash sandi Argon2id, kebijakan sandi, TOTP (jendela & anti pakai ulang), token, CSRF."""
from __future__ import annotations

import time

import jwt
import pyotp
import pytest
from cryptography.fernet import Fernet
from sinergi_api.auth import sandi as sd
from sinergi_api.auth import token as tok
from sinergi_api.auth import totp

RAHASIA_JWT = "r" * 40


def test_argon2id_hash_dan_verifikasi():
    h = sd.hash_sandi("Sandi-Panjang-Sekali-1")
    assert h.startswith("$argon2id$")
    assert sd.cocok(h, "Sandi-Panjang-Sekali-1")
    assert not sd.cocok(h, "salah")
    assert not sd.cocok(None, "apa saja")  # pengguna tidak ada -> tetap False (waktu konstan)
    assert not sd.cocok("!disabled", "x")  # akun sistem tanpa sandi


@pytest.mark.parametrize("s,ok", [("pendek", False), ("aaaaaaaaaaaaaaaa", False), ("budi.santoso-2026!", False),
                                  ("Kaltara-Neraca-2026", True)])
def test_kebijakan_sandi(s, ok):
    assert (sd.cek_kebijakan(s, 12, "budi.santoso") is None) is ok


def test_totp_jendela_dan_pakai_ulang():
    r = totp.rahasia_baru()
    t0 = 1_800_000_000.0
    kode = pyotp.TOTP(r).at(t0)
    langkah = totp.verifikasi(r, kode, None, sekarang=t0)
    assert langkah == int(t0 // 30)
    assert totp.verifikasi(r, kode, langkah, sekarang=t0) is None  # dipakai ulang ditolak
    assert totp.verifikasi(r, pyotp.TOTP(r).at(t0 - 30), None, sekarang=t0) is not None  # toleransi 1 langkah
    assert totp.verifikasi(r, pyotp.TOTP(r).at(t0 - 90), None, sekarang=t0) is None  # terlalu lama
    assert totp.verifikasi(r, "12ab56", None, sekarang=t0) is None
    assert totp.verifikasi(r, "", None, sekarang=t0) is None


def test_totp_enkripsi_fernet():
    k = Fernet.generate_key().decode()
    r = totp.rahasia_baru()
    enc = totp.enkripsi(r, k)
    assert r.encode() not in enc
    assert totp.dekripsi(enc, k) == r
    with pytest.raises(RuntimeError):
        totp.dekripsi(enc, Fernet.generate_key().decode())
    assert totp.qr_svg(totp.uri_pendaftaran(r, "op.a", "SINERGI")).startswith("data:image/svg+xml")


def test_token_akses_dan_pra_tidak_tertukar():
    a = tok.buat_akses(RAHASIA_JWT, 7, "sid-1", 15)
    k = tok.baca_akses(RAHASIA_JWT, a)
    assert k is not None and k.user_id == 7 and k.sesi_id == "sid-1"
    assert tok.baca_pra(RAHASIA_JWT, a) is None  # token akses bukan token pra-TOTP
    pra = tok.buat_pra(RAHASIA_JWT, 7, 5)
    assert tok.baca_pra(RAHASIA_JWT, pra) == 7
    assert tok.baca_akses(RAHASIA_JWT, pra) is None  # token pra tidak memberi akses
    assert tok.baca_akses("lain" * 10, a) is None


def test_token_kedaluwarsa_dan_alg_none_ditolak():
    lama = jwt.encode({"sub": "1", "sid": "s", "typ": "akses", "iat": int(time.time()) - 3600,
                       "exp": int(time.time()) - 10}, RAHASIA_JWT, algorithm="HS256")
    assert tok.baca_akses(RAHASIA_JWT, lama) is None
    tanpa_tanda = jwt.encode({"sub": "1", "sid": "s", "typ": "akses", "iat": int(time.time()),
                              "exp": int(time.time()) + 60}, None, algorithm="none")
    assert tok.baca_akses(RAHASIA_JWT, tanpa_tanda) is None


def test_refresh_token_hanya_hash_disimpan():
    token, h = tok.refresh_baru("6f1c2a5e-0000-4000-8000-000000000001")
    sid, rahasia = tok.pecah_refresh(token)
    assert sid == "6f1c2a5e-0000-4000-8000-000000000001"
    assert rahasia not in h and tok.hash_refresh(rahasia) == h
    assert tok.pecah_refresh("bukan-uuid.xyz") is None
    assert tok.pecah_refresh("") is None


def test_csrf_double_submit_bertanda_tangan():
    k = "kunci-csrf"
    t = tok.csrf_baru(k)
    assert tok.csrf_sah(k, t, t)
    assert not tok.csrf_sah(k, t, None)
    assert not tok.csrf_sah(k, t, t + "x")
    palsu = "abc.def"
    assert not tok.csrf_sah(k, palsu, palsu)  # cookie disuntik tanpa tanda tangan sah
