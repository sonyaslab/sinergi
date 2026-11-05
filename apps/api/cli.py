"""Perintah administrasi.

    python -m sinergi_api.cli buat-pengguna --username admin --nama "Admin SINERGI" --peran admin

Sandi sementara acak dicetak SEKALI ke layar; pengguna wajib menggantinya saat login pertama dan mendaftarkan TOTP.
Perintah ini untuk bootstrap (admin pertama) sehingga memakai koneksi pemilik (SINERGI_DB_URL_OWNER): RLS menolak
penulisan peran oleh app_rw tanpa izin pengguna.kelola. Di Docker jalankan lewat layanan `migrate`.
Pengguna berikutnya dibuat admin dari layar Pengguna & Hak Akses.
"""
from __future__ import annotations

import argparse
import secrets
import sys

from sqlalchemy import create_engine, text

from .app import audit, db
from .app.config import Pengaturan
from .auth import sandi


def buat_pengguna(username: str, nama: str, peran: list[str], email: str | None = None) -> tuple[int, str]:
    sementara = secrets.token_urlsafe(12)
    eng = create_engine(Pengaturan().db_url_owner)
    with db.transaksi(None, alasan="buat pengguna via CLI", engine=eng) as conn:
        uid = conn.execute(
            text("INSERT INTO sec.pengguna (username, nama, email, password_hash, wajib_ganti_sandi)"
                 " VALUES (lower(:u), :n, :e, :h, true) RETURNING id"),
            {"u": username, "n": nama, "e": email, "h": sandi.hash_sandi(sementara)},
        ).scalar_one()
        for kode in peran:
            n = conn.execute(
                text("INSERT INTO sec.pengguna_peran (pengguna_id, peran_id) SELECT :u, id FROM sec.peran"
                     " WHERE kode = :k"), {"u": uid, "k": kode}).rowcount
            if n != 1:
                raise SystemExit(f"Peran '{kode}' tidak ada di sec.peran.")
        audit.catat(conn, "BUAT_PENGGUNA", "sec.pengguna", str(uid), None, None,
                    {"username": username, "peran": peran}, "CLI")
    eng.dispose()
    return uid, sementara


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="sinergi_api.cli")
    sub = ap.add_subparsers(dest="perintah", required=True)
    b = sub.add_parser("buat-pengguna", help="Buat pengguna baru dengan sandi sementara")
    b.add_argument("--username", required=True)
    b.add_argument("--nama", required=True)
    b.add_argument("--peran", action="append", required=True, help="kode peran; boleh diulang")
    b.add_argument("--email")
    a = ap.parse_args(argv)
    if a.perintah == "buat-pengguna":
        uid, sementara = buat_pengguna(a.username, a.nama, a.peran, a.email)
        print(f"Pengguna #{uid} '{a.username}' dibuat. Sandi sementara (catat sekarang, tidak ditampilkan lagi):")
        print(sementara)
    return 0


if __name__ == "__main__":
    sys.exit(main())
