"""db/schema.sql + db/seed_ref.sql (dokumen sumber) harus identik dengan hasil migrasi Alembic (head).

Bila gagal: migrasi baru ditambahkan tanpa menyinkronkan db/schema.sql (atau sebaliknya).
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

import psycopg
import pytest
from psycopg import sql
from sqlalchemy.engine import make_url

pytestmark = pytest.mark.db

ROOT = Path(__file__).resolve().parents[4]
DB_SINKRON = "sinergi_test_sinkron"
DB_ALEMBIC = "sinergi_test_alembic"  # DB bersih hasil migrasi (DB uji bersama diubah oleh uji lain)


def _dsn(url: str, db: str | None = None) -> str:
    u = make_url(url).set(drivername="postgresql")
    return (u.set(database=db) if db else u).render_as_string(hide_password=False)


def _dump(db: str, *opsi: str) -> str:
    admin = make_url(os.environ["SINERGI_DB_ADMIN_URL"])
    env = {**os.environ, "PGPASSWORD": admin.password or ""}
    out = subprocess.run(
        ["pg_dump", "-h", admin.host or "localhost", "-p", str(admin.port or 5432), "-U", admin.username or "postgres",
         "--no-owner", "--no-comments", "-d", db, *opsi],
        check=True, capture_output=True, text=True, env=env).stdout
    out = re.sub(r"(?m)^--.*$|^\\(un)?restrict .*$|^SET .*$|^SELECT pg_catalog.set_config.*$", "", out)
    out = re.sub(r"(?s)CREATE TABLE public\.alembic_version.*?;\n|ALTER TABLE ONLY public\.alembic_version.*?;\n",
                 "", out)
    return "\n".join(_urutkan_copy([x for x in out.splitlines() if x.strip()]))


def _urutkan_copy(baris: list[str]) -> list[str]:
    """Urutkan baris data di tiap blok COPY (urutan fisik heap berbeda antara jalur migrasi dan jalur psql -f)."""
    hasil: list[str] = []
    blok: list[str] | None = None
    for b in baris:
        if blok is not None:
            if b == "\\.":
                hasil += sorted(blok) + [b]
                blok = None
            else:
                blok.append(b)
        else:
            hasil.append(b)
            if b.startswith("COPY "):
                blok = []
    return hasil


@pytest.mark.skipif(shutil.which("pg_dump") is None, reason="pg_dump tidak tersedia")
def test_schema_sql_sinkron_dengan_alembic(basis_data):
    with psycopg.connect(_dsn(os.environ["SINERGI_DB_ADMIN_URL"]), autocommit=True) as c:
        c.execute(sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(DB_SINKRON)))
        c.execute(sql.SQL("CREATE DATABASE {} OWNER {} TEMPLATE template0").format(
            sql.Identifier(DB_SINKRON), sql.Identifier(make_url(os.environ["SINERGI_DB_URL_OWNER"]).username)))
    with psycopg.connect(_dsn(os.environ["SINERGI_DB_URL_OWNER"], DB_SINKRON), autocommit=True) as c:
        c.execute((ROOT / "db" / "schema.sql").read_text(encoding="utf-8"))
        c.execute((ROOT / "db" / "seed_ref.sql").read_text(encoding="utf-8"))
    from sinergi_api import dbadmin
    from sinergi_api.app.config import Pengaturan

    dbadmin.reset(Pengaturan(), DB_ALEMBIC)
    alembic_db = DB_ALEMBIC
    assert _dump(DB_SINKRON, "--schema-only") == _dump(alembic_db, "--schema-only"), \
        "db/schema.sql tidak sinkron dengan migrasi Alembic"
    data = ["--data-only", "-t", "ref.*", "-t", "sec.peran", "-t", "sec.izin", "-t", "sec.peran_izin"]
    assert _dump(DB_SINKRON, *data) == _dump(alembic_db, *data), "db/seed_ref.sql tidak sinkron dengan migrasi"
