"""Dependensi FastAPI: pengguna saat ini (token akses + sesi aktif), RBAC per izin, koneksi berkonteks."""
from __future__ import annotations

import ipaddress
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from urllib.parse import unquote

from fastapi import Depends, Request
from sqlalchemy import Connection, text

from ..auth import token as tok
from . import db
from .config import pengaturan
from .galat import GalatSinergi
from .keamanan_http import COOKIE_AKSES

HEADER_ALASAN = "X-Alasan"


@dataclass(frozen=True)
class Pengguna:
    id: int
    username: str
    nama: str
    sesi_id: str
    wajib_ganti_sandi: bool
    peran: tuple[str, ...] = ()
    izin: frozenset[str] = field(default_factory=frozenset)

    def punya(self, *kode: str) -> bool:
        return any(k in self.izin for k in kode)


def ip_klien(request: Request) -> str | None:
    """Alamat IP klien (di belakang Nginx: uvicorn --proxy-headers). Nilai bukan IP diabaikan (kolom inet)."""
    host = request.client.host if request.client else None
    try:
        return str(ipaddress.ip_address(host)) if host else None
    except ValueError:
        return None


def alasan_dari(request: Request) -> str | None:
    """Alasan perubahan dari header X-Alasan (UTF-8, percent-encoded). Disimpan ke app.alasan untuk audit."""
    raw = request.headers.get(HEADER_ALASAN)
    if not raw:
        return None
    return unquote(raw)[:500].strip() or None


def izin_dan_peran(conn: Connection, user_id: int) -> tuple[tuple[str, ...], frozenset[str]]:
    r = conn.execute(
        text(
            "SELECT coalesce(array_agg(DISTINCT p.kode) FILTER (WHERE p.kode IS NOT NULL), '{}') AS peran,"
            "       coalesce(array_agg(DISTINCT pi.izin_kode) FILTER (WHERE pi.izin_kode IS NOT NULL), '{}') AS izin"
            "  FROM sec.pengguna_peran pp JOIN sec.peran p ON p.id = pp.peran_id AND p.aktif"
            "  LEFT JOIN sec.peran_izin pi ON pi.peran_id = pp.peran_id"
            " WHERE pp.pengguna_id = :u"
        ),
        {"u": user_id},
    ).one()
    return tuple(sorted(r.peran)), frozenset(r.izin)


_TIDAK_LOGIN = GalatSinergi(401, "BELUM_MASUK", "Silakan masuk terlebih dahulu.")


def _pengguna_dari_token(request: Request) -> Pengguna:
    p = pengaturan()
    klaim = tok.baca_akses(p.jwt_secret, request.cookies.get(COOKIE_AKSES, ""))
    if klaim is None:
        raise GalatSinergi(401, "TOKEN_KEDALUWARSA", "Sesi berakhir. Silakan masuk kembali.")
    now = datetime.now(UTC)
    with db.engine_rw().begin() as conn:
        s = conn.execute(
            text(
                "SELECT s.dicabut, s.kedaluwarsa, s.aktif_terakhir, u.id, u.username, u.nama, u.aktif,"
                "       u.totp_aktif, u.wajib_ganti_sandi"
                "  FROM sec.sesi s JOIN sec.pengguna u ON u.id = s.pengguna_id"
                " WHERE s.id = CAST(:sid AS uuid) AND s.pengguna_id = :u"
            ),
            {"sid": klaim.sesi_id, "u": klaim.user_id},
        ).one_or_none()
        if s is None or s.dicabut or not s.aktif or not s.totp_aktif or s.kedaluwarsa <= now:
            raise _TIDAK_LOGIN
        if now - s.aktif_terakhir > timedelta(minutes=p.idle_menit):
            conn.execute(text("UPDATE sec.sesi SET dicabut = true WHERE id = CAST(:sid AS uuid)"),
                         {"sid": klaim.sesi_id})
            raise GalatSinergi(401, "SESI_IDLE", "Sesi berakhir karena tidak aktif. Silakan masuk kembali.")
        if now - s.aktif_terakhir > timedelta(seconds=60):
            conn.execute(text("UPDATE sec.sesi SET aktif_terakhir = now() WHERE id = CAST(:sid AS uuid)"),
                         {"sid": klaim.sesi_id})
        peran, izin = izin_dan_peran(conn, s.id)
    return Pengguna(s.id, s.username, s.nama, klaim.sesi_id, s.wajib_ganti_sandi, peran, izin)


def pengguna_login(request: Request) -> Pengguna:
    """Pengguna terautentikasi (boleh masih wajib ganti sandi). Hanya untuk endpoint profil/ganti sandi/logout."""
    return _pengguna_dari_token(request)


def pengguna_aktif(pengguna: Pengguna = Depends(pengguna_login)) -> Pengguna:
    """Pengguna terautentikasi yang sudah mengganti sandi awal."""
    if pengguna.wajib_ganti_sandi:
        raise GalatSinergi(403, "WAJIB_GANTI_SANDI", "Ganti sandi awal Anda terlebih dahulu.")
    return pengguna


def butuh_izin(*kode: str) -> Callable[..., Pengguna]:
    """Dependensi RBAC: pengguna wajib memiliki salah satu izin `kode` (dari sec.peran_izin)."""

    def _cek(pengguna: Pengguna = Depends(pengguna_aktif)) -> Pengguna:
        if not pengguna.punya(*kode):
            raise GalatSinergi(403, "TIDAK_BERHAK", "Anda tidak memiliki izin untuk tindakan ini.")
        return pengguna

    return _cek


def koneksi(request: Request, pengguna: Pengguna = Depends(pengguna_aktif)) -> Iterator[Connection]:
    """Satu transaksi per permintaan dengan SET LOCAL app.user_id / app.ip / app.alasan."""
    with db.transaksi(pengguna.id, ip_klien(request), alasan_dari(request)) as conn:
        yield conn
