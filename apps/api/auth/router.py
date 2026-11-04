"""Endpoint autentikasi.

Alur: GET /api/auth/csrf -> POST /api/auth/login (sandi) -> POST /api/auth/totp (kode 6 digit; pendaftaran QR
bila TOTP belum aktif) -> cookie akses (15 menit) + refresh (berotasi). Kunci akun setelah N gagal berturut-turut.
"""
from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import Connection, text

from ..app import audit, db
from ..app.config import pengaturan
from ..app.deps import Pengguna, ip_klien, izin_dan_peran, pengguna_login
from ..app.galat import GalatSinergi
from ..app.keamanan_http import (
    COOKIE_AKSES,
    COOKIE_CSRF,
    COOKIE_PRA,
    COOKIE_REFRESH,
    hapus_cookie,
    kunci_csrf,
    setel_cookie,
)
from . import sandi as sd
from . import token as tok
from . import totp

router = APIRouter(prefix="/api/auth", tags=["auth"])

PATH_API = "/api"
PATH_AUTH = "/api/auth"
GAGAL_LOGIN = GalatSinergi(401, "LOGIN_GAGAL", "Nama pengguna atau sandi salah.")


class MasukIn(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    sandi: str = Field(min_length=1, max_length=256)


class TotpIn(BaseModel):
    kode: str = Field(min_length=6, max_length=8)


class GantiSandiIn(BaseModel):
    sandi_lama: str = Field(min_length=1, max_length=256)
    sandi_baru: str = Field(min_length=1, max_length=256)


class MasukOut(BaseModel):
    tahap: Literal["totp", "daftar_totp"]
    qr_svg: str | None = None
    rahasia: str | None = None  # untuk input manual di aplikasi autentikator (hanya saat pendaftaran)


def _menit_tersisa(sampai: datetime, now: datetime) -> int:
    return max(1, int((sampai - now).total_seconds() // 60) + 1)


def _catat_gagal(conn: Connection, u, ip: str | None, aksi: str) -> GalatSinergi | None:
    """Tambah hitungan gagal; kunci akun bila mencapai batas. Kembalikan galat kunci bila akun baru saja dikunci."""
    p = pengaturan()
    gagal = (u.gagal_login or 0) + 1
    audit.catat(conn, aksi, "sec.pengguna", str(u.id), u.id, ip)
    if gagal >= p.maks_gagal_login:
        conn.execute(
            text("UPDATE sec.pengguna SET gagal_login = 0, terkunci_sampai = now() + make_interval(mins => :m),"
                 " diubah_pada = now() WHERE id = :id"),
            {"m": p.kunci_menit, "id": u.id},
        )
        audit.catat(conn, "AKUN_TERKUNCI", "sec.pengguna", str(u.id), u.id, ip, {"menit": p.kunci_menit})
        return GalatSinergi(429, "AKUN_TERKUNCI",
                            f"Terlalu banyak percobaan gagal. Akun dikunci {p.kunci_menit} menit.")
    conn.execute(text("UPDATE sec.pengguna SET gagal_login = :g, diubah_pada = now() WHERE id = :id"),
                 {"g": gagal, "id": u.id})
    return None


def _cek_terkunci(u, now: datetime) -> GalatSinergi | None:
    if u.terkunci_sampai and u.terkunci_sampai > now:
        return GalatSinergi(429, "AKUN_TERKUNCI",
                            f"Akun terkunci sementara. Coba lagi dalam {_menit_tersisa(u.terkunci_sampai, now)} menit.")
    return None


_KOLOM_U = ("id, username, nama, password_hash, aktif, gagal_login, terkunci_sampai, totp_aktif, totp_secret_enc,"
            " totp_langkah_terakhir, wajib_ganti_sandi")


@router.get("/csrf")
def csrf(response: Response) -> dict:
    t = tok.csrf_baru(kunci_csrf())
    setel_cookie(response, COOKIE_CSRF, t, 12 * 3600, "/", http_only=False)
    return {"csrf": t}


@router.post("/login", response_model=MasukOut)
def login(data: MasukIn, request: Request, response: Response) -> MasukOut:
    p = pengaturan()
    ip = ip_klien(request)
    now = datetime.now(UTC)
    galat: GalatSinergi | None = None
    hasil: MasukOut | None = None
    uid: int | None = None
    with db.engine_rw().begin() as conn:
        u = conn.execute(text(f"SELECT {_KOLOM_U} FROM sec.pengguna WHERE username = lower(:u) FOR UPDATE"),
                         {"u": data.username.strip()}).one_or_none()
        sah = sd.cocok(u.password_hash if u else None, data.sandi)  # selalu dijalankan (waktu konstan)
        if u is None:
            audit.catat(conn, "LOGIN_GAGAL", "sec.pengguna", data.username.strip().lower()[:64], None, ip)
            galat = GAGAL_LOGIN
        elif (galat := _cek_terkunci(u, now)) is not None:
            audit.catat(conn, "LOGIN_DITOLAK_TERKUNCI", "sec.pengguna", str(u.id), u.id, ip)
        elif not u.aktif or not sah:
            galat = _catat_gagal(conn, u, ip, "LOGIN_GAGAL") or GAGAL_LOGIN
        else:
            uid = u.id
            conn.execute(text("UPDATE sec.pengguna SET gagal_login = 0 WHERE id = :id"), {"id": u.id})
            if sd.perlu_hash_ulang(u.password_hash):
                conn.execute(text("UPDATE sec.pengguna SET password_hash = :h WHERE id = :id"),
                             {"h": sd.hash_sandi(data.sandi), "id": u.id})
            if u.totp_aktif and u.totp_secret_enc:
                hasil = MasukOut(tahap="totp")
            else:
                rahasia = totp.dekripsi(u.totp_secret_enc, p.fernet_key) if u.totp_secret_enc else None
                if rahasia is None:
                    rahasia = totp.rahasia_baru()
                    conn.execute(text("UPDATE sec.pengguna SET totp_secret_enc = :s, totp_aktif = false,"
                                      " totp_langkah_terakhir = NULL WHERE id = :id"),
                                 {"s": totp.enkripsi(rahasia, p.fernet_key), "id": u.id})
                uri = totp.uri_pendaftaran(rahasia, u.username, p.totp_issuer)
                hasil = MasukOut(tahap="daftar_totp", qr_svg=totp.qr_svg(uri), rahasia=rahasia)
    if galat is not None:
        raise galat
    assert hasil is not None and uid is not None
    setel_cookie(response, COOKIE_PRA, tok.buat_pra(p.jwt_secret, uid, p.pra_totp_menit),
                 p.pra_totp_menit * 60, PATH_AUTH)
    return hasil


def _profil(conn: Connection, user_id: int) -> dict:
    u = conn.execute(text("SELECT id, username, nama, wajib_ganti_sandi FROM sec.pengguna WHERE id = :id"),
                     {"id": user_id}).one()
    peran, izin = izin_dan_peran(conn, user_id)
    tugas = conn.execute(
        text(
            "SELECT td.kode AS tahun_dasar, p.wilayah_kode, l.kode AS lapus, p.peran_tugas"
            "  FROM lk.penugasan p JOIN ref.tahun_dasar td ON td.id = p.tahun_dasar_id"
            "  JOIN ref.lapus l ON l.id = p.lapus_id"
            " WHERE p.pengguna_id = :u AND current_date >= p.berlaku_mulai"
            "   AND (p.berlaku_sampai IS NULL OR current_date <= p.berlaku_sampai)"
            " ORDER BY td.kode, p.wilayah_kode, l.urutan"
        ),
        {"u": user_id},
    ).mappings().all()
    return {"id": u.id, "username": u.username, "nama": u.nama, "wajib_ganti_sandi": u.wajib_ganti_sandi,
            "peran": list(peran), "izin": sorted(izin), "penugasan": [dict(t) for t in tugas]}


def _ua_hash(request: Request) -> str:
    return hashlib.sha256((request.headers.get("user-agent") or "").encode()).hexdigest()[:32]


@router.post("/totp")
def verifikasi_totp(data: TotpIn, request: Request, response: Response) -> dict:
    p = pengaturan()
    ip = ip_klien(request)
    uid = tok.baca_pra(p.jwt_secret, request.cookies.get(COOKIE_PRA, ""))
    if uid is None:
        raise GalatSinergi(401, "PRA_KEDALUWARSA", "Waktu verifikasi habis. Silakan masuk ulang.")
    now = datetime.now(UTC)
    galat: GalatSinergi | None = None
    profil: dict | None = None
    sid = str(uuid.uuid4())
    refresh, refresh_hash = tok.refresh_baru(sid)
    with db.engine_rw().begin() as conn:
        u = conn.execute(text(f"SELECT {_KOLOM_U} FROM sec.pengguna WHERE id = :id FOR UPDATE"),
                         {"id": uid}).one_or_none()
        if u is None or not u.aktif or not u.totp_secret_enc:
            galat = GalatSinergi(401, "PRA_KEDALUWARSA", "Waktu verifikasi habis. Silakan masuk ulang.")
        elif (galat := _cek_terkunci(u, now)) is not None:
            pass
        else:
            langkah = totp.verifikasi(totp.dekripsi(u.totp_secret_enc, p.fernet_key), data.kode,
                                      u.totp_langkah_terakhir)
            if langkah is None:
                galat = _catat_gagal(conn, u, ip, "TOTP_GAGAL") or GalatSinergi(
                    401, "TOTP_SALAH", "Kode verifikasi salah atau sudah dipakai. Coba kode berikutnya.")
            else:
                if not u.totp_aktif:
                    audit.catat(conn, "TOTP_DAFTAR", "sec.pengguna", str(u.id), u.id, ip)
                conn.execute(
                    text("UPDATE sec.pengguna SET totp_aktif = true, totp_langkah_terakhir = :l, gagal_login = 0,"
                         " terakhir_login = now(), diubah_pada = now() WHERE id = :id"),
                    {"l": langkah, "id": u.id},
                )
                conn.execute(
                    text("INSERT INTO sec.sesi (id, pengguna_id, refresh_hash, kedaluwarsa, ip, ua_hash)"
                         " VALUES (CAST(:sid AS uuid), :u, :h, now() + make_interval(hours => :j),"
                         " CAST(NULLIF(:ip, '') AS inet), :ua)"),
                    {"sid": sid, "u": u.id, "h": refresh_hash, "j": p.refresh_jam, "ip": ip or "",
                     "ua": _ua_hash(request)},
                )
                audit.catat(conn, "LOGIN", "sec.pengguna", str(u.id), u.id, ip, {"sesi": sid})
                profil = _profil(conn, u.id)
    if galat is not None:
        raise galat
    assert profil is not None
    _setel_sesi(response, profil["id"], sid, refresh)
    hapus_cookie(response, COOKIE_PRA, PATH_AUTH)
    return profil


def _setel_sesi(response: Response, user_id: int, sid: str, refresh: str) -> None:
    p = pengaturan()
    setel_cookie(response, COOKIE_AKSES, tok.buat_akses(p.jwt_secret, user_id, sid, p.akses_menit),
                 p.akses_menit * 60, PATH_API)
    setel_cookie(response, COOKIE_REFRESH, refresh, p.refresh_jam * 3600, PATH_AUTH)


@router.post("/refresh")
def refresh(request: Request, response: Response) -> dict:
    """Rotasi token refresh. Token lama yang dipakai ulang mencabut seluruh sesi (deteksi pencurian token)."""
    p = pengaturan()
    ip = ip_klien(request)
    bagian = tok.pecah_refresh(request.cookies.get(COOKIE_REFRESH, ""))
    tolak = GalatSinergi(401, "BELUM_MASUK", "Sesi berakhir. Silakan masuk kembali.")
    if bagian is None:
        raise tolak
    sid, rahasia = bagian
    now = datetime.now(UTC)
    galat: GalatSinergi | None = None
    token_baru: str | None = None
    uid: int | None = None
    with db.engine_rw().begin() as conn:
        s = conn.execute(
            text("SELECT s.pengguna_id, s.refresh_hash, s.kedaluwarsa, s.aktif_terakhir, s.dicabut, u.aktif"
                 "  FROM sec.sesi s JOIN sec.pengguna u ON u.id = s.pengguna_id"
                 " WHERE s.id = CAST(:sid AS uuid) FOR UPDATE OF s"),
            {"sid": sid},
        ).one_or_none()
        if s is None or s.dicabut or not s.aktif or s.kedaluwarsa <= now:
            galat = tolak
        elif tok.hash_refresh(rahasia) != s.refresh_hash:
            conn.execute(text("UPDATE sec.sesi SET dicabut = true WHERE id = CAST(:sid AS uuid)"), {"sid": sid})
            audit.catat(conn, "REFRESH_PAKAI_ULANG", "sec.sesi", sid, s.pengguna_id, ip)
            galat = tolak
        elif now - s.aktif_terakhir > timedelta(minutes=p.idle_menit):
            conn.execute(text("UPDATE sec.sesi SET dicabut = true WHERE id = CAST(:sid AS uuid)"), {"sid": sid})
            galat = GalatSinergi(401, "SESI_IDLE", "Sesi berakhir karena tidak aktif. Silakan masuk kembali.")
        else:
            token_baru, h = tok.refresh_baru(sid)
            uid = s.pengguna_id
            conn.execute(text("UPDATE sec.sesi SET refresh_hash = :h, aktif_terakhir = now()"
                              " WHERE id = CAST(:sid AS uuid)"), {"h": h, "sid": sid})
    if galat is not None:
        hapus_cookie(response, COOKIE_AKSES, PATH_API)
        raise galat
    assert token_baru is not None and uid is not None
    _setel_sesi(response, uid, sid, token_baru)
    return {"ok": True}


@router.post("/logout")
def logout(request: Request, response: Response) -> dict:
    p = pengaturan()
    ip = ip_klien(request)
    sid: str | None = None
    klaim = tok.baca_akses(p.jwt_secret, request.cookies.get(COOKIE_AKSES, ""))
    if klaim:
        sid = klaim.sesi_id
    elif (bagian := tok.pecah_refresh(request.cookies.get(COOKIE_REFRESH, ""))) is not None:
        sid = bagian[0]
    if sid:
        with db.engine_rw().begin() as conn:
            r = conn.execute(text("UPDATE sec.sesi SET dicabut = true WHERE id = CAST(:sid AS uuid) AND NOT dicabut"
                                  " RETURNING pengguna_id"), {"sid": sid}).one_or_none()
            if r is not None:
                audit.catat(conn, "LOGOUT", "sec.sesi", sid, r.pengguna_id, ip)
    hapus_cookie(response, COOKIE_AKSES, PATH_API)
    hapus_cookie(response, COOKIE_REFRESH, PATH_AUTH)
    hapus_cookie(response, COOKIE_PRA, PATH_AUTH)
    return {"ok": True}


@router.get("/saya")
def saya(pengguna: Pengguna = Depends(pengguna_login)) -> dict:
    with db.engine_rw().begin() as conn:
        return _profil(conn, pengguna.id)


@router.post("/ganti-sandi")
def ganti_sandi(data: GantiSandiIn, request: Request, pengguna: Pengguna = Depends(pengguna_login)) -> dict:
    p = pengaturan()
    ip = ip_klien(request)
    if (msg := sd.cek_kebijakan(data.sandi_baru, p.sandi_min_panjang, pengguna.username)) is not None:
        raise GalatSinergi(422, "SANDI_LEMAH", msg)
    if data.sandi_baru == data.sandi_lama:
        raise GalatSinergi(422, "SANDI_SAMA", "Sandi baru harus berbeda dari sandi lama.")
    galat: GalatSinergi | None = None
    with db.engine_rw().begin() as conn:
        u = conn.execute(text(f"SELECT {_KOLOM_U} FROM sec.pengguna WHERE id = :id FOR UPDATE"),
                         {"id": pengguna.id}).one()
        if not sd.cocok(u.password_hash, data.sandi_lama):
            galat = _catat_gagal(conn, u, ip, "GANTI_SANDI_GAGAL") or GalatSinergi(
                422, "SANDI_LAMA_SALAH", "Sandi lama salah.")
        else:
            conn.execute(text("UPDATE sec.pengguna SET password_hash = :h, wajib_ganti_sandi = false,"
                              " gagal_login = 0, diubah_pada = now() WHERE id = :id"),
                         {"h": sd.hash_sandi(data.sandi_baru), "id": u.id})
            # Cabut sesi lain milik pengguna ini.
            conn.execute(text("UPDATE sec.sesi SET dicabut = true WHERE pengguna_id = :u"
                              " AND id <> CAST(:sid AS uuid) AND NOT dicabut"),
                         {"u": u.id, "sid": pengguna.sesi_id})
            audit.catat(conn, "GANTI_SANDI", "sec.pengguna", str(u.id), u.id, ip)
    if galat is not None:
        raise galat
    return {"ok": True}
