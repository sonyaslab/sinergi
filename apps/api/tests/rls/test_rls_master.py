"""RLS master (migrasi 0003): tulis ref.* butuh master.kelola; tulis peran/izin/penugasan butuh pengguna.kelola.

Diuji langsung di basis data (koneksi app_rw + SET LOCAL app.user_id) sehingga tetap berlaku walau API dilewati.
"""
from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from sinergi_api.app import db

pytestmark = pytest.mark.db


def _sqlstate(e: DBAPIError) -> str:
    return getattr(e.orig, "sqlstate", "")


def test_operator_tidak_bisa_tulis_master(buat_akun):
    op = buat_akun(["operator"])
    with pytest.raises(DBAPIError) as e, db.transaksi(op.id) as c:
        c.execute(text("INSERT INTO ref.satuan (kode, nama) VALUES ('rls_uji', 'x')"))
    assert _sqlstate(e.value) == "42501"
    with db.transaksi(op.id) as c:  # UPDATE/DELETE tersaring USING -> 0 baris, tidak berubah
        assert c.execute(text("UPDATE ref.lapus SET nama = 'diretas' WHERE kode = 'A'")).rowcount == 0
        assert c.execute(text("DELETE FROM ref.wilayah WHERE kode = '6571'")).rowcount == 0
        assert c.execute(text("SELECT count(*) FROM ref.lapus")).scalar_one() > 0  # baca tetap boleh


def test_operator_tidak_bisa_menaikkan_hak_sendiri(buat_akun):
    op = buat_akun(["operator"])
    with pytest.raises(DBAPIError) as e, db.transaksi(op.id) as c:
        c.execute(text("INSERT INTO sec.pengguna_peran (pengguna_id, peran_id)"
                       " SELECT :u, id FROM sec.peran WHERE kode = 'admin'"), {"u": op.id})
    assert _sqlstate(e.value) == "42501"
    with pytest.raises(DBAPIError), db.transaksi(op.id) as c:
        c.execute(text("INSERT INTO sec.peran_izin (peran_id, izin_kode)"
                       " SELECT id, 'data.tulis_semua' FROM sec.peran WHERE kode = 'operator'"))
    with pytest.raises(DBAPIError), db.transaksi(op.id) as c:
        c.execute(text("INSERT INTO lk.penugasan (pengguna_id, tahun_dasar_id, wilayah_kode, lapus_id, peran_tugas)"
                       " SELECT :u, tahun_dasar_id, '6500', id, 'operator' FROM ref.lapus WHERE kode = 'B.2'"
                       " LIMIT 1"), {"u": op.id})


def test_peran_master_dan_pengelola_terpisah(buat_akun):
    sup = buat_akun(["supervisor"])  # tanpa master.kelola dan pengguna.kelola
    with pytest.raises(DBAPIError), db.transaksi(sup.id) as c:
        c.execute(text("INSERT INTO ref.sumber_data (nama) VALUES ('rls uji supervisor')"))
    adm = buat_akun(["admin"])
    with db.transaksi(adm.id) as c:
        c.execute(text("INSERT INTO ref.sumber_data (nama) VALUES ('rls uji admin')"))
        c.execute(text("DELETE FROM ref.sumber_data WHERE nama = 'rls uji admin'"))


def test_peran_nonaktif_tidak_memberi_izin(buat_akun, admin_conn):
    pid = admin_conn.execute("INSERT INTO sec.peran (kode, nama, aktif) VALUES ('rls_nonaktif', 'x', false)"
                             " RETURNING id").fetchone()[0]
    admin_conn.execute("INSERT INTO sec.peran_izin VALUES (%s, 'master.kelola')", (pid,))
    u = buat_akun(["rls_nonaktif"])
    with db.transaksi(u.id) as c:
        assert c.execute(text("SELECT sec.punya_izin('master.kelola')")).scalar_one() is False
