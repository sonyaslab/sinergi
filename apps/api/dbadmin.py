"""Administrasi basis data: peran, buat ulang DB, migrasi Alembic, uji skema.

    python -m sinergi_api.dbadmin reset            # buat ulang DB `sinergi` + alembic upgrade head
    python -m sinergi_api.dbadmin migrasi          # alembic upgrade head saja
    python -m sinergi_api.dbadmin reset --db sinergi_test
    python -m sinergi_api.dbadmin uji-skema        # DB sinergi_test_skema + db/test_schema.sql (16 OK)

Kata sandi peran diambil dari URL koneksi SINERGI_DB_URL (app_rw), SINERGI_DB_URL_RO (app_ro), dan
SINERGI_DB_URL_OWNER (app_owner). Superuser: SINERGI_DB_ADMIN_URL (hanya untuk membuat peran dan DB).
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import psycopg
from psycopg import sql
from sqlalchemy.engine import URL, make_url

from .app.config import Pengaturan

ALEMBIC_INI = Path(__file__).resolve().parent / "alembic.ini"


def _psycopg_dsn(url: str | URL, db: str | None = None) -> str:
    u = make_url(url) if isinstance(url, str) else url
    if db:
        u = u.set(database=db)
    return u.set(drivername="postgresql").render_as_string(hide_password=False)


def url_admin() -> str:
    url = os.environ.get("SINERGI_DB_ADMIN_URL")
    if not url:
        raise SystemExit("SINERGI_DB_ADMIN_URL (superuser) belum diisi.")
    return url


def pastikan_peran(p: Pengaturan) -> None:
    """Buat/selaraskan peran login app_owner, app_rw, app_ro (sandi dari URL koneksi)."""
    peran = [make_url(p.db_url_owner), make_url(p.db_url), make_url(p.db_url_ro)]
    with psycopg.connect(_psycopg_dsn(url_admin()), autocommit=True) as c:
        for u in peran:
            if not u.username or u.password is None:
                raise SystemExit("URL koneksi peran harus memuat nama pengguna dan sandi.")
            ada = c.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (u.username,)).fetchone()
            perintah = "ALTER" if ada else "CREATE"
            c.execute(sql.SQL("{} ROLE {} LOGIN PASSWORD {}").format(
                sql.SQL(perintah), sql.Identifier(u.username), sql.Literal(u.password)))


def buat_ulang_db(p: Pengaturan, nama: str) -> None:
    owner = make_url(p.db_url_owner).username or "app_owner"
    rw, ro = make_url(p.db_url).username or "app_rw", make_url(p.db_url_ro).username or "app_ro"
    with psycopg.connect(_psycopg_dsn(url_admin()), autocommit=True) as c:
        c.execute(sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(nama)))
        c.execute(sql.SQL("CREATE DATABASE {} OWNER {} ENCODING 'UTF8' TEMPLATE template0").format(
            sql.Identifier(nama), sql.Identifier(owner)))
        # Hanya peran aplikasi yang boleh terhubung (bukan PUBLIC).
        c.execute(sql.SQL("REVOKE ALL ON DATABASE {} FROM PUBLIC").format(sql.Identifier(nama)))
        c.execute(sql.SQL("GRANT CONNECT ON DATABASE {} TO {}, {}").format(
            sql.Identifier(nama), sql.Identifier(rw), sql.Identifier(ro)))


def uji_skema(p: Pengaturan, berkas: Path, nama: str = "sinergi_test_skema", harap_ok: int = 16) -> int:
    """Buat DB lewat migrasi Alembic lalu jalankan db/test_schema.sql (psql, superuser). Harus muncul N baris OK."""
    reset(p, nama)
    admin = make_url(url_admin()).set(drivername="postgresql", database=nama)
    env = {**os.environ, "PGPASSWORD": admin.password or ""}
    psql = shutil.which("psql")
    if psql is None:
        raise SystemExit("psql tidak ditemukan di PATH.")
    hasil = subprocess.run(  # noqa: S603 - argumen dari konfigurasi admin, bukan input pengguna web
        [psql, "-X", "-v", "ON_ERROR_STOP=1", "-h", admin.host or "localhost", "-p", str(admin.port or 5432),
         "-U", admin.username or "postgres", "-d", nama, "-f", str(berkas)],
        capture_output=True, text=True, env=env, check=False)
    baris_ok = [b for b in (hasil.stdout + hasil.stderr).splitlines() if re.search(r"\bOK \d", b)]
    for b in baris_ok:
        print(b.split("NOTICE:")[-1].strip())
    if hasil.returncode != 0 or len(baris_ok) != harap_ok:
        print(hasil.stderr[-2000:], file=sys.stderr)
        print(f"GAGAL: {len(baris_ok)}/{harap_ok} uji skema OK", file=sys.stderr)
        return 1
    print(f"Uji skema: {len(baris_ok)}/{harap_ok} OK")
    return 0


def migrasi(p: Pengaturan, nama: str | None = None) -> None:
    from alembic import command
    from alembic.config import Config

    url = make_url(p.db_url_owner)
    if nama:
        url = url.set(database=nama)
    cfg = Config(str(ALEMBIC_INI))
    cfg.cmd_opts = argparse.Namespace(x=[f"url={url.render_as_string(hide_password=False)}"])
    command.upgrade(cfg, "head")


def reset(p: Pengaturan, nama: str) -> None:
    pastikan_peran(p)
    buat_ulang_db(p, nama)
    migrasi(p, nama)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="sinergi_api.dbadmin")
    ap.add_argument("perintah", choices=["reset", "migrasi", "peran", "uji-skema"])
    ap.add_argument("--db", default=None, help="nama basis data (bawaan: dari SINERGI_DB_URL_OWNER)")
    ap.add_argument("--berkas", default=str(Path(__file__).resolve().parents[2] / "db" / "test_schema.sql"))
    a = ap.parse_args(argv)
    p = Pengaturan()
    nama = a.db or make_url(p.db_url_owner).database or "sinergi"
    if a.perintah == "reset":
        reset(p, nama)
        print(f"Basis data '{nama}' dibuat ulang dan dimigrasi ke head.")
    elif a.perintah == "uji-skema":
        return uji_skema(p, Path(a.berkas), a.db or "sinergi_test_skema")
    elif a.perintah == "migrasi":
        migrasi(p, nama)
    else:
        pastikan_peran(p)
    return 0


if __name__ == "__main__":
    sys.exit(main())
