"""Uji API: RBAC per izin, RLS lewat koneksi aplikasi (operator tanpa penugasan ditolak), peta galat 423/403.

Rute `/api/_uji/*` hanya dipasang di aplikasi uji (tidak ada di produksi) untuk menjalankan SQL tulis lewat jalur
dependensi yang sama dengan endpoint sungguhan (cookie -> sesi -> SET LOCAL app.user_id/app.ip/app.alasan).
"""
from __future__ import annotations

import pytest
from fastapi import APIRouter, Depends
from fastapi.testclient import TestClient
from sqlalchemy import Connection, text

from sinergi_api.app.deps import Pengguna, butuh_izin, koneksi
from sinergi_api.app.main import buat_app
from tests.conftest import masuk

pytestmark = pytest.mark.db


@pytest.fixture
def klien_uji(basis_data):
    app = buat_app()
    r = APIRouter(prefix="/api/_uji")

    @r.get("/master")
    def hanya_admin(p: Pengguna = Depends(butuh_izin("master.kelola"))) -> dict:
        return {"ok": p.username}

    @r.post("/item")
    def tambah_item(data: dict, conn: Connection = Depends(koneksi)) -> dict:
        iid = conn.execute(text(
            "INSERT INTO lk.item (tahun_dasar_id, wilayah_kode, lapus_id, metode_kode, nomor, nama, alasan)"
            " SELECT l.tahun_dasar_id, :w, l.id, 'REV', :n, :nama, 'uji api' FROM ref.lapus l"
            "  JOIN ref.tahun_dasar td ON td.id = l.tahun_dasar_id WHERE td.kode = 'TD2025' AND l.kode = :l"
            " RETURNING id"), data).scalar_one()
        return {"id": iid}

    @r.post("/nilai-terkunci")
    def ubah_nilai(data: dict, conn: Connection = Depends(koneksi)) -> dict:
        conn.execute(text("UPDATE lk.nilai_item SET nilai = nilai + 1 WHERE putaran_id = :p"), data)
        return {"ok": True}

    app.include_router(r)
    with TestClient(app, base_url="http://testserver") as c:
        yield c


@pytest.fixture
def penugasan(admin_conn):
    def _tugas(uid: int, lapus: str, wilayah: str = "6500", td: str = "TD2025") -> None:
        admin_conn.execute(
            "INSERT INTO lk.penugasan (pengguna_id, tahun_dasar_id, wilayah_kode, lapus_id, peran_tugas)"
            " SELECT %s, l.tahun_dasar_id, %s, l.id, 'operator' FROM ref.lapus l"
            " JOIN ref.tahun_dasar t ON t.id = l.tahun_dasar_id WHERE t.kode = %s AND l.kode = %s",
            (uid, wilayah, td, lapus))

    return _tugas


def test_rbac_izin_dari_basis_data(klien_uji, buat_akun, jam):
    op = buat_akun(["operator"])
    masuk(klien_uji, op, jam)
    r = klien_uji.get("/api/_uji/master")
    assert r.status_code == 403 and r.json()["kode"] == "TIDAK_BERHAK"
    klien_uji.cookies.clear()
    adm = buat_akun(["admin"])
    masuk(klien_uji, adm, jam)
    assert klien_uji.get("/api/_uji/master").json() == {"ok": adm.username}


def test_operator_tanpa_penugasan_ditolak_rls(klien_uji, buat_akun, jam, penugasan, admin_conn):
    op = buat_akun(["operator"])
    h = masuk(klien_uji, op, jam)
    r = klien_uji.post("/api/_uji/item", json={"w": "6500", "n": 11, "nama": "Padi uji", "l": "A.1.a"}, headers=h)
    assert r.status_code == 403 and r.json()["kode"] == "TIDAK_BERHAK"
    penugasan(op.id, "A.1.a")
    r = klien_uji.post("/api/_uji/item", json={"w": "6500", "n": 11, "nama": "Padi uji", "l": "A.1.a"},
                       headers={**h, "X-Alasan": "uji%20alasan%20perubahan"})
    assert r.status_code == 200, r.text
    iid = r.json()["id"]
    # Penugasan hanya untuk A.1.a wilayah 6500: lapus/wilayah lain tetap ditolak.
    r = klien_uji.post("/api/_uji/item", json={"w": "6501", "n": 11, "nama": "Padi uji", "l": "A.1.a"}, headers=h)
    assert r.status_code == 403
    r = klien_uji.post("/api/_uji/item", json={"w": "6500", "n": 11, "nama": "Jagung", "l": "A.1.b"}, headers=h)
    assert r.status_code == 403
    # Audit mencatat pengguna dan alasan dari header X-Alasan (SET LOCAL app.alasan).
    a = admin_conn.execute("SELECT pengguna_id, alasan FROM audit.log WHERE entitas = 'lk.item'"
                           " AND entitas_id = %s AND aksi = 'INSERT'", (str(iid),)).fetchone()
    assert a == (op.id, "uji alasan perubahan")


def test_putaran_terkunci_423(klien_uji, buat_akun, jam, admin_conn):
    pid = admin_conn.execute(
        "INSERT INTO lk.putaran (tahun_dasar_id, tahun, triwulan, nomor, nama, jenis, status, periode_awal_id,"
        " periode_akhir_id) SELECT td.id, 2026, 1, 77, 'Uji kunci', 'REGULER', 'terbuka',"
        " (SELECT id FROM ref.periode WHERE tahun = 2019 AND triwulan = 1),"
        " (SELECT id FROM ref.periode WHERE tahun = 2026 AND triwulan = 1)"
        " FROM ref.tahun_dasar td WHERE td.kode = 'TD2025' RETURNING id").fetchone()[0]
    iid = admin_conn.execute(
        "INSERT INTO lk.item (tahun_dasar_id, wilayah_kode, lapus_id, metode_kode, nomor, nama)"
        " SELECT l.tahun_dasar_id, '6571', l.id, 'REV', 1, 'Item kunci' FROM ref.lapus l JOIN ref.tahun_dasar t"
        " ON t.id = l.tahun_dasar_id WHERE t.kode = 'TD2025' AND l.kode = 'B.4' RETURNING id").fetchone()[0]
    admin_conn.execute("INSERT INTO lk.nilai_item (putaran_id, item_id, jenis_seri, periode_id, nilai)"
                       " SELECT %s, %s, 'KUANTUM', id, 1 FROM ref.periode WHERE tahun = 2025", (pid, iid))
    admin_conn.execute("UPDATE lk.putaran SET status = 'terkunci' WHERE id = %s", (pid,))
    adm = buat_akun(["admin"])
    h = masuk(klien_uji, adm, jam)
    r = klien_uji.post("/api/_uji/nilai-terkunci", json={"p": pid}, headers=h)
    assert r.status_code == 423 and r.json()["kode"] == "PUTARAN_TERKUNCI"
