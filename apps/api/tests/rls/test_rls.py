"""Uji RLS dan hak peran DB lewat `db.transaksi` (koneksi app_rw + SET LOCAL app.user_id), sama seperti aplikasi."""
from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, ProgrammingError

from sinergi_api.app import db

pytestmark = pytest.mark.db

SQL_ITEM = text(
    "INSERT INTO lk.item (tahun_dasar_id, wilayah_kode, lapus_id, metode_kode, nomor, nama, alasan)"
    " SELECT l.tahun_dasar_id, :w, l.id, 'DEF', :n, 'Item RLS', 'uji rls' FROM ref.lapus l"
    " JOIN ref.tahun_dasar t ON t.id = l.tahun_dasar_id WHERE t.kode = :td AND l.kode = :l RETURNING id")


def _sqlstate(e: DBAPIError) -> str:
    return getattr(e.orig, "sqlstate", "")


@pytest.fixture
def tugaskan(admin_conn):
    def _t(uid: int, lapus: str, td: str = "TD2025", wilayah: str = "6500", sampai: str | None = None) -> None:
        admin_conn.execute(
            "INSERT INTO lk.penugasan (pengguna_id, tahun_dasar_id, wilayah_kode, lapus_id, peran_tugas,"
            " berlaku_mulai, berlaku_sampai) SELECT %s, l.tahun_dasar_id, %s, l.id, 'operator',"
            " current_date - 30, %s::date FROM ref.lapus l JOIN ref.tahun_dasar t ON t.id = l.tahun_dasar_id"
            " WHERE t.kode = %s AND l.kode = %s", (uid, wilayah, sampai, td, lapus))

    return _t


def test_operator_tanpa_penugasan_ditolak(buat_akun):
    op = buat_akun(["operator"])
    with pytest.raises(DBAPIError) as e, db.transaksi(op.id, "10.0.0.1") as c:
        c.execute(SQL_ITEM, {"w": "6500", "n": 1, "td": "TD2025", "l": "C.2.1"})
    assert _sqlstate(e.value) == "42501"


def test_operator_dengan_penugasan_boleh_dan_terbatas_td(buat_akun, tugaskan, admin_conn):
    op = buat_akun(["operator"])
    tugaskan(op.id, "C.2.1", td="TD2025")
    with db.transaksi(op.id, "10.0.0.1", "tambah komoditas baru") as c:
        iid = c.execute(SQL_ITEM, {"w": "6500", "n": 1, "td": "TD2025", "l": "C.2.1"}).scalar_one()
    a = admin_conn.execute("SELECT pengguna_id, host(ip), alasan FROM audit.log WHERE entitas = 'lk.item'"
                           " AND entitas_id = %s AND aksi = 'INSERT'", (str(iid),)).fetchone()
    assert a == (op.id, "10.0.0.1", "tambah komoditas baru")
    # Penugasan TD2025 tidak berlaku untuk lapus TD2010 (id lapus berbeda per tahun dasar).
    with pytest.raises(DBAPIError) as e, db.transaksi(op.id) as c:
        c.execute(SQL_ITEM, {"w": "6500", "n": 1, "td": "TD2010", "l": "C.2"})
    assert _sqlstate(e.value) == "42501"


def test_penugasan_kedaluwarsa_ditolak(buat_akun, tugaskan):
    op = buat_akun(["operator"])
    tugaskan(op.id, "C.2.2", sampai="2020-01-01")
    with pytest.raises(DBAPIError) as e, db.transaksi(op.id) as c:
        c.execute(SQL_ITEM, {"w": "6500", "n": 1, "td": "TD2025", "l": "C.2.2"})
    assert _sqlstate(e.value) == "42501"


def test_operator_lain_tidak_bisa_ubah_nilai(buat_akun, tugaskan, admin_conn):
    pemilik, lain = buat_akun(["operator"]), buat_akun(["operator"])
    tugaskan(pemilik.id, "C.2.4")
    tugaskan(lain.id, "C.2.5")
    with db.transaksi(pemilik.id) as c:
        iid = c.execute(SQL_ITEM, {"w": "6500", "n": 3, "td": "TD2025", "l": "C.2.4"}).scalar_one()
    with db.transaksi(lain.id) as c:  # baca boleh, ubah tidak berdampak (USING menyaring baris)
        assert c.execute(text("SELECT count(*) FROM lk.item WHERE id = :i"), {"i": iid}).scalar_one() == 1
        n = c.execute(text("UPDATE lk.item SET nama = 'diubah' WHERE id = :i"), {"i": iid}).rowcount
        assert n == 0
    assert admin_conn.execute("SELECT nama FROM lk.item WHERE id = %s", (iid,)).fetchone()[0] == "Item RLS"


def test_tanpa_konteks_pengguna_tidak_bisa_baca(buat_akun):
    with db.transaksi(None) as c:
        assert c.execute(text("SELECT count(*) FROM lk.item")).scalar_one() == 0


def test_admin_tulis_semua_dan_simulasi_butuh_izin(buat_akun, tugaskan, admin_conn):
    adm, op = buat_akun(["admin"]), buat_akun(["operator"])
    tugaskan(op.id, "D.1")
    pid = admin_conn.execute(
        "INSERT INTO lk.putaran (tahun_dasar_id, tahun, triwulan, nomor, nama, jenis, status, periode_awal_id,"
        " periode_akhir_id) SELECT td.id, 2026, 2, 88, 'Uji RLS', 'REGULER', 'terbuka',"
        " (SELECT id FROM ref.periode WHERE tahun = 2019 AND triwulan = 1),"
        " (SELECT id FROM ref.periode WHERE tahun = 2026 AND triwulan = 2)"
        " FROM ref.tahun_dasar td WHERE td.kode = 'TD2025' RETURNING id").fetchone()[0]
    sim = text(
        "INSERT INTO lk.penyesuaian (putaran_id, wilayah_kode, lapus_id, tahap, jenis_kode, harga, periode_id,"
        " nilai, alasan) SELECT :p, '6500', l.id, 'SIMULASI', 'SIM_NTB', 'K',"
        " (SELECT id FROM ref.periode WHERE tahun = 2026 AND triwulan = 1), 1, 'rekonsiliasi laju uji'"
        " FROM ref.lapus l JOIN ref.tahun_dasar t ON t.id = l.tahun_dasar_id WHERE t.kode = 'TD2025'"
        " AND l.kode = 'D.1'")
    with pytest.raises(DBAPIError) as e, db.transaksi(op.id) as c:  # operator: tidak punya simulasi.edit
        c.execute(sim, {"p": pid})
    assert _sqlstate(e.value) == "42501"
    with db.transaksi(adm.id) as c:  # admin: data.tulis_semua + simulasi.edit
        c.execute(sim, {"p": pid})
        c.execute(SQL_ITEM, {"w": "6504", "n": 9, "td": "TD2025", "l": "H.4"})


def test_audit_append_only_untuk_app_rw(buat_akun):
    op = buat_akun(["operator"])
    with pytest.raises(DBAPIError) as e, db.transaksi(op.id) as c:
        c.execute(text("UPDATE audit.log SET aksi = 'X' WHERE id = (SELECT min(id) FROM audit.log)"))
    assert _sqlstate(e.value) == "42501"
    with pytest.raises(DBAPIError), db.transaksi(op.id) as c:
        c.execute(text("DELETE FROM audit.log"))


def test_app_rw_tanpa_ddl_dan_app_ro_baca_saja(buat_akun):
    with pytest.raises(ProgrammingError), db.transaksi(None) as c:
        c.execute(text("CREATE TABLE lk.coba (x int)"))
    with pytest.raises(ProgrammingError), db.transaksi(None) as c:
        c.execute(text("ALTER TABLE lk.item DISABLE ROW LEVEL SECURITY"))
    with pytest.raises(ProgrammingError), db.transaksi(None, engine=db.engine_ro()) as c:
        c.execute(text("UPDATE ref.lapus SET nama = nama"))


def test_rantai_hash_audit_utuh(admin_conn):
    n = admin_conn.execute(
        "SELECT count(*) FROM (SELECT hash_sebelum, lag(hash) OVER (ORDER BY id) AS prev FROM audit.log) x"
        " WHERE x.prev IS NOT NULL AND x.hash_sebelum IS DISTINCT FROM x.prev").fetchone()[0]
    assert n == 0


def test_catat_ekspor_bertanda_air(buat_akun, admin_conn):
    from sinergi_api.app import audit

    sup = buat_akun(["supervisor"])
    with db.transaksi(sup.id, "10.0.0.2") as c:
        ta = audit.catat_ekspor(c, sup.id, sup.username, "tabel_pokok", {"wilayah": "6500"}, "10.0.0.2")
    assert ta.startswith("SINERGI - RAHASIA - " + sup.username)
    r = admin_conn.execute("SELECT tanda_air FROM audit.ekspor WHERE pengguna_id = %s", (sup.id,)).fetchone()
    assert r[0] == ta
    assert admin_conn.execute("SELECT count(*) FROM audit.log WHERE aksi = 'EKSPOR' AND pengguna_id = %s",
                              (sup.id,)).fetchone()[0] == 1
