"""Uji F1 pengguna & hak akses: pengguna, peran-izin, penugasan (diperluas ke daun), jejak audit, penjaga pengelola."""
from __future__ import annotations

import pytest

from tests.conftest import csrf, tanpa_uid

pytestmark = pytest.mark.db


def test_buat_pengguna_sandi_sementara_wajib_ganti(klien, sebagai, jam, admin_conn):
    h = sebagai("admin")
    r = klien.post("/api/pengguna", headers=tanpa_uid(h),
                   json={"username": "op.nunukan", "nama": "Operator  Nunukan", "peran": ["operator"]})
    assert r.status_code == 201, r.text
    baru = r.json()
    assert len(baru["sandi_sementara"]) >= 12
    daftar = {u["username"]: u for u in klien.get("/api/pengguna").json()}
    assert daftar["op.nunukan"]["nama"] == "Operator Nunukan" and daftar["op.nunukan"]["peran"] == ["operator"]
    assert daftar["op.nunukan"]["wajib_ganti_sandi"] is True and daftar["sistem.worker"]["akun_sistem"] is True
    # Login dengan sandi sementara -> daftar TOTP -> wajib ganti sandi
    klien.cookies.clear()
    h2 = csrf(klien)
    r = klien.post("/api/auth/login", json={"username": "op.nunukan", "sandi": baru["sandi_sementara"]}, headers=h2)
    assert r.json()["tahap"] == "daftar_totp"
    assert klien.post("/api/auth/totp", json={"kode": jam.kode(r.json()["rahasia"])}, headers=h2).status_code == 200
    assert klien.get("/api/tahun-dasar").json()["kode"] == "WAJIB_GANTI_SANDI"
    # Audit pengguna tanpa hash sandi / rahasia TOTP
    rows = admin_conn.execute("SELECT nilai_baru::text FROM audit.log WHERE entitas = 'sec.pengguna'"
                              " AND entitas_id = %s AND aksi IN ('INSERT', 'UPDATE')", (str(baru["id"]),)).fetchall()
    assert rows and all("argon2" not in r[0] and "totp_secret_enc" not in r[0] for r in rows)
    assert any("rahasia_totp_diubah" in r[0] for r in rows)
    # Username tidak valid
    sebagai("admin")
    r = klien.post("/api/pengguna", headers=tanpa_uid(sebagai("admin")),
                   json={"username": "Op Besar", "nama": "x", "peran": ["operator"]})
    assert r.status_code == 422


def test_nonaktif_mencabut_sesi_dan_tidak_bisa_diri_sendiri(klien, sebagai, buat_akun, jam):
    from fastapi.testclient import TestClient

    from tests.conftest import masuk

    target = buat_akun(["operator"])
    with TestClient(klien.app, base_url="http://testserver") as lain:
        masuk(lain, target, jam)
        assert lain.get("/api/auth/saya").status_code == 200
        h = sebagai("admin")
        assert klien.delete(f"/api/pengguna/{target.id}", headers=tanpa_uid(h)).json()["hasil"] == "dinonaktifkan"
        assert lain.get("/api/auth/saya").status_code == 401  # sesi target langsung dicabut
    r = klien.patch(f"/api/pengguna/{h['_uid']}", headers=tanpa_uid(h), json={"aktif": False})
    assert r.status_code == 422 and "sendiri" in r.json()["pesan"]


def test_reset_sandi_totp_dan_buka_kunci(klien, sebagai, buat_akun, admin_conn):
    h = sebagai("admin")
    t = buat_akun(["operator"])
    admin_conn.execute("UPDATE sec.pengguna SET terkunci_sampai = now() + interval '10 minutes' WHERE id = %s",
                       (t.id,))
    assert next(u for u in klien.get("/api/pengguna").json() if u["id"] == t.id)["terkunci"] is True
    klien.post(f"/api/pengguna/{t.id}/buka-kunci", headers=tanpa_uid(h))
    assert next(u for u in klien.get("/api/pengguna").json() if u["id"] == t.id)["terkunci"] is False
    r = klien.post(f"/api/pengguna/{t.id}/reset-sandi", headers=tanpa_uid(h)).json()
    assert r["sandi_sementara"]
    klien.post(f"/api/pengguna/{t.id}/reset-totp", headers=tanpa_uid(h))
    u = admin_conn.execute("SELECT wajib_ganti_sandi, totp_aktif, totp_secret_enc FROM sec.pengguna WHERE id = %s",
                           (t.id,)).fetchone()
    assert u == (True, False, None)
    sistem = admin_conn.execute("SELECT id FROM sec.pengguna WHERE username = 'sistem.worker'").fetchone()[0]
    assert klien.post(f"/api/pengguna/{sistem}/reset-sandi", headers=tanpa_uid(h)).status_code == 422


def test_peran_baru_dan_izin_berlaku(klien, sebagai, buat_akun, jam):
    h = sebagai("admin")
    izin = {i["kode"]: i["nama"] for i in klien.get("/api/izin").json()}
    assert izin["master.kelola"].startswith("Kelola master data")
    r = klien.post("/api/peran", headers=tanpa_uid(h),
                   json={"kode": "analis_uji", "nama": "Analis", "izin": ["tabel_pokok.lihat", "master.kelola"]})
    assert r.status_code == 201
    pid = r.json()["id"]
    assert klien.post("/api/peran", headers=tanpa_uid(h),
                      json={"kode": "x_uji", "nama": "x", "izin": ["izin.palsu"]}).status_code == 422
    from tests.conftest import masuk
    analis = buat_akun(["analis_uji"])
    klien.cookies.clear()
    ha = masuk(klien, analis, jam)
    assert klien.post("/api/satuan", headers=ha, json={"kode": "uji_analis", "nama": "x"}).status_code == 201
    # Izin dicabut dari peran -> langsung tidak berlaku
    h = sebagai("admin")
    klien.patch(f"/api/peran/{pid}", headers=tanpa_uid(h), json={"izin": ["tabel_pokok.lihat"]})
    klien.cookies.clear()
    ha = masuk(klien, analis, jam)
    assert klien.post("/api/satuan", headers=ha, json={"kode": "uji_analis2", "nama": "x"}).status_code == 403
    # Peran dipakai pengguna -> hapus = nonaktif; izinnya tidak berlaku lagi
    h = sebagai("admin")
    klien.patch(f"/api/peran/{pid}", headers=tanpa_uid(h), json={"izin": ["master.kelola"]})
    assert klien.delete(f"/api/peran/{pid}", headers=tanpa_uid(h)).json()["hasil"] == "dinonaktifkan"
    klien.cookies.clear()
    ha = masuk(klien, analis, jam)
    assert klien.get("/api/auth/saya").json()["izin"] == []
    assert klien.post("/api/satuan", headers=ha, json={"kode": "uji_analis3", "nama": "x"}).status_code == 403


def test_minimal_satu_pengelola_tersisa(klien, sebagai, admin_conn):
    h = sebagai("admin")
    admin_id = admin_conn.execute("SELECT id FROM sec.peran WHERE kode = 'admin'").fetchone()[0]
    semua = [i["kode"] for i in klien.get("/api/izin").json()]
    # Simulasikan: hanya pengguna uji ini yang aktif dengan pengguna.kelola
    admin_conn.execute("CREATE TEMP TABLE _cadang AS SELECT id FROM sec.pengguna WHERE aktif AND id <> %s",
                       (int(h["_uid"]),))
    admin_conn.execute("UPDATE sec.pengguna SET aktif = false WHERE id IN (SELECT id FROM _cadang)")
    try:
        r = klien.patch(f"/api/peran/{admin_id}", headers=tanpa_uid(h),
                        json={"izin": [k for k in semua if k != "pengguna.kelola"]})
        assert r.status_code == 422 and "pengguna.kelola" in r.json()["pesan"]
        r = klien.patch(f"/api/pengguna/{h['_uid']}", headers=tanpa_uid(h), json={"peran": ["operator"]})
        assert r.status_code == 422
        assert "pengguna.kelola" in klien.get("/api/auth/saya").json()["izin"]  # transaksi dibatalkan utuh
    finally:
        admin_conn.execute("UPDATE sec.pengguna SET aktif = true WHERE id IN (SELECT id FROM _cadang)")
        admin_conn.execute("DROP TABLE _cadang")


def test_penugasan_kategori_diperluas_ke_daun_dan_rls(klien, sebagai, buat_akun, admin_conn):
    from sqlalchemy import text
    from sqlalchemy.exc import DBAPIError

    from sinergi_api.app import db

    h = sebagai("admin")
    op = buat_akun(["operator"])
    td = admin_conn.execute("SELECT id FROM ref.tahun_dasar WHERE kode = 'TD2025'").fetchone()[0]
    lid = dict(admin_conn.execute("SELECT kode, id FROM ref.lapus WHERE tahun_dasar_id = %s", (td,)).fetchall())
    r = klien.post("/api/penugasan", headers=tanpa_uid(h), json={
        "pengguna_id": op.id, "tahun_dasar_id": td, "wilayah_kode": ["6501", "6502"], "lapus_ids": [lid["H"]]})
    assert r.status_code == 201, r.text
    assert r.json() == {"jumlah": 14, "lapus_daun": 7, "wilayah": 2}  # H: H.1, H.2, H.3.a, H.3.b, H.4, H.5, H.6
    daftar = klien.get("/api/penugasan", params={"pengguna_id": op.id}).json()
    assert {d["kode_lapus"] for d in daftar} == {"H.1", "H.2", "H.3.a", "H.3.b", "H.4", "H.5", "H.6"}
    # TOP/SOP boleh ditugaskan (lapus berdata, keputusan metodologi)
    r = klien.post("/api/penugasan", headers=tanpa_uid(h), json={
        "pengguna_id": op.id, "tahun_dasar_id": td, "wilayah_kode": ["6500"], "lapus_ids": [lid["TOP"], lid["SOP"]]})
    assert r.json()["lapus_daun"] == 2
    sql = text("INSERT INTO lk.item (tahun_dasar_id, wilayah_kode, lapus_id, metode_kode, nomor, nama)"
               " VALUES (:td, '6501', :l, 'DEF', 49, 'Uji penugasan')")
    with db.transaksi(op.id) as c:
        c.execute(sql, {"td": td, "l": lid["H.4"]})
    # Akhiri penugasan -> hak tulis langsung hilang (RLS)
    pid = next(d["id"] for d in daftar if d["kode_lapus"] == "H.5" and d["wilayah_kode"] == "6501")
    assert klien.delete(f"/api/penugasan/{pid}", headers=tanpa_uid(h)).json()["hasil"] == "diakhiri"
    with pytest.raises(DBAPIError), db.transaksi(op.id) as c:
        c.execute(sql, {"td": td, "l": lid["H.5"]})
    # Lapus beda tahun dasar / wilayah tidak dikenal ditolak
    td10 = admin_conn.execute("SELECT id FROM ref.tahun_dasar WHERE kode = 'TD2010'").fetchone()[0]
    r = klien.post("/api/penugasan", headers=tanpa_uid(h), json={
        "pengguna_id": op.id, "tahun_dasar_id": td10, "wilayah_kode": ["6500"], "lapus_ids": [lid["H"]]})
    assert r.status_code == 422
    r = klien.post("/api/penugasan", headers=tanpa_uid(h), json={
        "pengguna_id": op.id, "tahun_dasar_id": td, "wilayah_kode": ["9999"], "lapus_ids": [lid["H"]]})
    assert r.status_code == 422


def test_hak_akses_ditolak_untuk_non_pengelola(klien, sebagai):
    h = sebagai("supervisor")
    assert klien.get("/api/pengguna").status_code == 403
    assert klien.post("/api/peran", headers=tanpa_uid(h), json={"kode": "naik_kelas", "nama": "x",
                                                               "izin": ["pengguna.kelola"]}).status_code == 403
    assert klien.get("/api/audit").status_code == 200  # supervisor punya audit.lihat
    sebagai("operator")
    assert klien.get("/api/audit").status_code == 403


def test_jejak_audit_dan_verifikasi_rantai(klien, sebagai):
    h = sebagai("admin")
    klien.post("/api/satuan", headers={**tanpa_uid(h), "X-Alasan": "uji%20jejak%20audit"},
               json={"kode": "uji_jejak", "nama": "x"})
    d = klien.get("/api/audit", params={"entitas": "ref.satuan", "pengguna_id": h["_uid"]}).json()
    assert d["total"] >= 1 and d["baris"][0]["alasan"] == "uji jejak audit"
    assert d["baris"][0]["nilai_baru"]["kode"] == "uji_jejak"
    v = klien.get("/api/audit/verifikasi").json()
    assert v["utuh"] is True and v["putus"] == 0 and v["baris"] > 0
