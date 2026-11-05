"""API F4: buka/salin putaran, cut-off, status lapus (ajukan/setujui/kembalikan/NIHIL/DIKECUALIKAN, kembali ke draf),
penyesuaian (target, putus, izin), simulasi, Biaya Antara, LK Hitung pratinjau, bandingkan putaran. Angka fiktif."""
from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta

import pytest

from sinergi_api.worker.antrean import proses_semua
from tests.alur import PER, U, W, buka, h_, hasil, isi_rev, lapus_id, status, tugaskan
from tests.conftest import masuk

pytestmark = pytest.mark.db


@pytest.fixture
def pemain(klien, buat_akun, jam):
    """pemain('operator') -> header CSRF; akun per nama tetap sama (login ulang saat berganti)."""
    akun: dict[str, object] = {}

    def _jadi(nama: str, peran: str | None = None) -> dict[str, str]:
        if nama not in akun:
            akun[nama] = buat_akun([peran or nama])
        klien.cookies.clear()
        h = masuk(klien, akun[nama], jam)
        h["_uid"] = str(akun[nama].id)  # type: ignore[attr-defined]
        return h

    return _jadi


@pytest.fixture
def siap(admin_conn, td_salin, pemain, klien):
    td = td_salin("TD2025")
    lid = lapus_id(admin_conn, td)
    put = buka(klien, pemain("admin"), td)
    op = pemain("operator")
    tugaskan(admin_conn, int(op["_uid"]), td, lid["A.1.a"])
    return {"td": td, "lid": lid, "put": put}


def _adj(klien, h, put, lid, jenis="ADJ4_NTB", tahap="REKON", harga="CP", u=U(2025, 3), mode="nilai", target=5.0,
         metode=None, alasan="penyesuaian uji alur F4", jalur="/api/penyesuaian"):
    return klien.post(jalur, headers=h_(h), json={
        "putaran_id": put, "wilayah": W, "lapus_id": lid, "tahap": tahap, "metode": metode, "jenis": jenis,
        "harga": harga, "periode": u, "mode": mode, "target": target, "alasan": alasan})


def _st(klien, h, put, lid, aksi, **kw):
    return klien.post(f"/api/status/{lid}/{aksi}", headers=h_(h), json={"putaran_id": put, "wilayah": W, **kw})


def test_buka_putaran_izin_cakupan_dan_salin(klien, pemain, siap, admin_conn, uid_worker):
    op = pemain("operator")
    a11a = siap["lid"]["A.1.a"]
    iid = isi_rev(klien, op, siap["put"], a11a)
    r = _adj(klien, op, siap["put"], a11a)
    assert r.status_code == 201, r.text
    r = _adj(klien, op, siap["put"], a11a, u=U(2025, 4), target=7.0)
    tolak = r.json()["id"]
    admin_conn.execute("UPDATE lk.penyesuaian SET status = 'ditolak' WHERE id = %s", (tolak,))
    r = klien.post("/api/putaran", headers=h_(op), json={"tahun_dasar_id": siap["td"], "tahun": 2026, "triwulan": 2,
                                                         "nama": "Putaran operator", "jenis": "REGULER",
                                                         "periode_awal": U(2024, 1)})
    assert r.status_code == 403
    adm = pemain("admin")
    r = klien.post("/api/putaran", headers=h_(adm), json={"tahun_dasar_id": siap["td"], "tahun": 2026, "triwulan": 2,
                                                          "nama": "Salah cakupan", "jenis": "REGULER",
                                                          "periode_awal": U(2026, 3)})
    assert r.status_code == 422
    baru = buka(klien, adm, siap["td"], nama="Putaran 1", sumber=siap["put"], triwulan=2)
    n = lambda t, p: admin_conn.execute(f"SELECT count(*) FROM lk.{t} WHERE putaran_id = %s", (p,)).fetchone()[0]  # noqa: E731
    assert n("nilai_item", baru) == n("nilai_item", siap["put"]) == 27
    assert n("parameter_item", baru) == 1
    adj = admin_conn.execute("SELECT status, nilai::float8 FROM lk.penyesuaian WHERE putaran_id = %s",
                             (baru,)).fetchall()
    assert adj == [("draf", 5.0)]  # ditolak tidak disalin; semua menjadi draf (keputusan 21)
    p = admin_conn.execute("SELECT status, sumber_putaran_id, pa.urut, pz.urut FROM lk.putaran x JOIN ref.periode pa"
                           " ON pa.id = x.periode_awal_id JOIN ref.periode pz ON pz.id = x.periode_akhir_id"
                           " WHERE x.id = %s", (baru,)).fetchone()
    assert p == ("terbuka", siap["put"], U(2024, 1), U(2026, 2))
    assert status(admin_conn, baru, a11a) == "belum"  # status lapus tidak disalin
    al = admin_conn.execute("SELECT alasan FROM audit.log WHERE entitas = 'lk.putaran' AND entitas_id = %s",
                            (str(baru),)).fetchone()[0]
    assert "salin dari" in al
    proses_semua(uid_worker)
    assert hasil(admin_conn, baru, a11a, U(2025, 1)) == pytest.approx(hasil(admin_conn, siap["put"], a11a,
                                                                             U(2025, 1)), rel=1e-12)
    daftar = klien.get(f"/api/putaran?tahun_dasar_id={siap['td']}", headers=h_(adm)).json()
    assert {x["id"] for x in daftar} >= {siap["put"], baru} and daftar[0]["sumber"]
    assert iid


def test_cutoff_wajib_alasan(klien, pemain, siap, admin_conn):
    op = pemain("operator")
    iid = isi_rev(klien, op, siap["put"], siap["lid"]["A.1.a"])
    adm = pemain("admin")
    lalu = (datetime.now(UTC) - timedelta(days=1)).isoformat()
    r = klien.patch(f"/api/putaran/{siap['put']}", headers=h_(adm), json={"tanggal_cutoff": lalu})
    assert r.status_code == 200, r.text
    op = pemain("operator")
    sel = {"putaran_id": siap["put"], "perubahan": [{"item_id": iid, "seri": "KUANTUM", "periode": U(2025, 1),
                                                     "nilai": 123.0}]}
    r = klien.put("/api/data-dasar/nilai", headers=h_(op), json=sel)
    assert r.status_code == 422 and r.json()["kode"] == "ALASAN_CUTOFF"
    r = klien.put("/api/data-dasar/nilai", headers=h_(op, "koreksi data BPS sesudah cut-off"), json=sel)
    assert r.status_code == 200, r.text
    al = admin_conn.execute("SELECT alasan FROM audit.log WHERE entitas = 'lk.nilai_item' ORDER BY id DESC"
                            " LIMIT 1").fetchone()[0]
    assert al == "koreksi data BPS sesudah cut-off"
    putaran = next(x for x in klien.get("/api/putaran", headers=h_(op)).json() if x["id"] == siap["put"])
    assert putaran["lewat_cutoff"] is True


def test_alur_status_ajukan_setujui_kembali_ke_draf(klien, pemain, siap, admin_conn, uid_worker):
    put, a11a = siap["put"], siap["lid"]["A.1.a"]
    op = pemain("operator")
    iid = isi_rev(klien, op, put, a11a, rka_td=None)
    assert status(admin_conn, put, a11a) == "draf"  # belum -> draf saat diisi
    r = _st(klien, op, put, a11a, "ajukan")
    assert r.status_code == 409 and r.json()["kode"] == "VALIDASI_BLOKIR"
    assert any(x["kode"] == "V02" for x in r.json()["rincian"])
    klien.put("/api/data-dasar/parameter", headers=h_(op), json={"putaran_id": put, "item_id": iid, "kode": "RKA_TD",
                                                                 "nilai": 0.3})
    assert _adj(klien, op, put, a11a).status_code == 201
    assert _st(klien, op, put, siap["lid"]["B.1"], "ajukan").status_code == 403  # tidak ditugaskan
    r = _st(klien, op, put, a11a, "ajukan")
    assert r.status_code == 200 and r.json()["penyesuaian_diajukan"] == 1
    assert _st(klien, op, put, a11a, "setujui").status_code == 403  # operator tidak berhak menyetujui
    # ubah data saat diajukan -> kembali ke draf; penyesuaian diajukan ikut draf
    klien.put("/api/data-dasar/nilai", headers=h_(op), json={"putaran_id": put, "perubahan": [
        {"item_id": iid, "seri": "KUANTUM", "periode": U(2025, 2), "nilai": 150.0}]})
    assert status(admin_conn, put, a11a) == "draf"
    assert admin_conn.execute("SELECT status FROM lk.penyesuaian WHERE putaran_id = %s", (put,)).fetchone()[0] == "draf"
    assert _st(klien, op, put, a11a, "ajukan").status_code == 200
    sup = pemain("supervisor")
    r = _st(klien, sup, put, a11a, "setujui")
    assert r.status_code == 409 and r.json()["kode"] == "PENYESUAIAN_BELUM_DIPUTUS"
    r = _st(klien, sup, put, a11a, "setujui", putus_penyesuaian="setujui")
    assert r.status_code == 200 and r.json()["penyesuaian_diputus"] == 1, r.text
    assert status(admin_conn, put, a11a) == "disetujui"
    proses_semua(uid_worker)
    benc = hasil(admin_conn, put, a11a, U(2025, 3), "BENC")
    post = hasil(admin_conn, put, a11a, U(2025, 3), "POST")
    assert benc[1] == pytest.approx(post[1] + 5.0)  # ADJ4_NTB disetujui masuk angka resmi
    # operator mengubah data lapus yang sudah disetujui -> persetujuan gugur (keputusan 19)
    op = pemain("operator")
    klien.put("/api/data-dasar/nilai", headers=h_(op), json={"putaran_id": put, "perubahan": [
        {"item_id": iid, "seri": "KUANTUM", "periode": U(2025, 2), "nilai": 151.0}]})
    assert status(admin_conn, put, a11a) == "draf"
    riw = klien.get(f"/api/status/{a11a}/riwayat?putaran_id={put}&wilayah={W}", headers=h_(op)).json()
    assert riw[0]["dari"] == "disetujui" and riw[0]["ke"] == "draf" and "simpan data dasar" in riw[0]["catatan"]
    assert _st(klien, op, put, a11a, "ajukan").status_code == 200
    sup = pemain("supervisor")
    assert _st(klien, sup, put, a11a, "kembalikan", catatan="pendek").status_code == 422
    r = _st(klien, sup, put, a11a, "kembalikan", catatan="harga Q2 perlu dicek ulang")
    assert r.status_code == 200 and status(admin_conn, put, a11a) == "dikembalikan"
    d = klien.get(f"/api/status?putaran_id={put}&wilayah={W}", headers=h_(sup)).json()
    baris = next(x for x in d["lapus"] if x["id"] == a11a)
    assert baris["status"] == "dikembalikan" and baris["jumlah_item"] == 1


def test_nihil_dan_dikecualikan(klien, pemain, siap, admin_conn):
    put, lid = siap["put"], siap["lid"]
    op = pemain("operator")
    assert _st(klien, op, put, lid["A.1.a"], "nihil", catatan="tidak ada kegiatan di wilayah").status_code == 200
    assert status(admin_conn, put, lid["A.1.a"]) == "nihil"
    assert _st(klien, op, put, lid["A.1.b"], "nihil", catatan="tidak ada kegiatan di wilayah").status_code == 403
    # isi item pada lapus NIHIL -> kembali draf
    isi_rev(klien, op, put, lid["A.1.a"])
    assert status(admin_conn, put, lid["A.1.a"]) == "draf"
    r = _st(klien, op, put, lid["A.1.a"], "nihil", catatan="tidak ada kegiatan di wilayah")
    assert r.status_code == 422  # sudah punya item
    sup = pemain("supervisor")
    r = _st(klien, sup, put, lid["TOP"], "nihil", catatan="tidak ada pajak atas produk")
    assert r.status_code == 422  # TOP/SOP memakai DIKECUALIKAN
    assert _st(klien, sup, put, lid["TOP"], "kecualikan", catatan="belum ada arahan BPS RI").status_code == 403
    adm = pemain("admin")
    assert _st(klien, adm, put, lid["TOP"], "kecualikan", catatan="pendek").status_code == 422
    assert _st(klien, adm, put, lid["TOP"], "kecualikan", catatan="belum ada arahan BPS RI").status_code == 200
    assert _st(klien, adm, put, lid["SOP"], "kecualikan", catatan="belum ada arahan BPS RI").status_code == 200
    ring = klien.get(f"/api/validasi/kunci?putaran_id={put}&wilayah={W}", headers=h_(adm)).json()
    assert not [b for b in ring["blokir"] if b["kode"] == "V14"]
    assert any(b["kode"] == "V13" for b in ring["blokir"])  # daun lain masih kosong
    r = _st(klien, sup, put, lid["TOP"], "batal")
    assert r.status_code == 403
    assert _st(klien, adm, put, lid["TOP"], "batal").status_code == 200
    assert status(admin_conn, put, lid["TOP"]) == "belum"
    peta = klien.get(f"/api/status/ringkasan?putaran_id={put}", headers=h_(adm)).json()
    assert peta["sel"][W][str(lid["SOP"])]["status"] == "dikecualikan"
    assert peta["sel"][W][str(lid["A.1.a"])] == {"status": "draf", "item": 1}


def test_penyesuaian_target_izin_putus_dan_simulasi(klien, pemain, siap, admin_conn, uid_worker):
    put, a11a = siap["put"], siap["lid"]["A.1.a"]
    op = pemain("operator")
    isi_rev(klien, op, put, a11a)
    proses_semua(uid_worker)
    # pratinjau target NTB ADJ4 (ADHK): nilai = target - NTB POST
    post = hasil(admin_conn, put, a11a, U(2025, 3), "POST")
    r = _adj(klien, op, put, a11a, harga="K", mode="target_ntb", target=500.0, jalur="/api/penyesuaian/hitung")
    assert r.status_code == 200, r.text
    assert r.json()["nilai"] == pytest.approx(500.0 - post[3])
    r = _adj(klien, op, put, a11a, harga="K", mode="target_ntb", target=500.0)
    assert r.status_code == 201 and r.json()["status"] == "draf"
    assert _adj(klien, op, put, a11a, alasan="pendek").status_code == 422  # alasan wajib (trigger)
    assert _adj(klien, op, put, siap["lid"]["B.1"]).status_code == 403  # lapus tidak ditugaskan
    assert _adj(klien, op, put, a11a, jenis="ADJ4_OUTPUT", mode="target_ntb").status_code == 422
    assert _adj(klien, op, put, a11a, jenis="SIM_NTB", tahap="SIMULASI").status_code == 403
    aid = klien.get(f"/api/penyesuaian?putaran_id={put}&wilayah={W}", headers=h_(op)).json()[0]["id"]
    r = klien.post("/api/penyesuaian/putus", headers=h_(op), json={"putaran_id": put, "id": [aid],
                                                                   "keputusan": "setujui"})
    assert r.status_code == 403
    sup = pemain("supervisor")
    r = klien.post("/api/penyesuaian/putus", headers=h_(sup), json={"putaran_id": put, "id": [aid],
                                                                    "keputusan": "setujui"})
    assert r.status_code == 409  # masih draf (belum diajukan)
    # LK Hitung: pratinjau memuat draf, angka resmi tidak
    resmi = klien.get(f"/api/hasil/lapus/{a11a}?putaran_id={put}&wilayah={W}", headers=h_(sup)).json()
    prat = klien.get(f"/api/hasil/lapus/{a11a}?putaran_id={put}&wilayah={W}&pratinjau=true", headers=h_(sup)).json()
    k = str(U(2025, 3))
    assert prat["pratinjau"] and prat["tahap"]["BENC"][k][3] == pytest.approx(500.0)
    assert resmi["tahap"]["BENC"][k][3] == pytest.approx(post[3])
    assert set(resmi["metode"]) == {"REV"} and resmi["item"][0]["nilai"][k]
    # simulasi: target laju y-on-y NTB ADHK (docs/02 §6), dihitung pada pratinjau (keputusan 18)
    r = _adj(klien, sup, put, a11a, jenis="SIM_NTB", tahap="SIMULASI", harga="K", mode="target_laju", target=4.0,
             alasan="rekonsiliasi laju dengan rilis")
    assert r.status_code == 201, r.text
    prat = klien.get(f"/api/hasil/lapus/{a11a}?putaran_id={put}&wilayah={W}&pratinjau=true", headers=h_(sup)).json()
    lalu_k = prat["tahap"]["FINAL"][str(U(2024, 3))][3]
    assert prat["tahap"]["FINAL"][k][3] / lalu_k * 100 - 100 == pytest.approx(4.0, rel=1e-9)
    # draf ADJ4 operator dihapus -> pratinjau = resmi; simulasi diisi ulang lalu disetujui
    op = pemain("operator")
    assert klien.delete(f"/api/penyesuaian/{aid}", headers=h_(op)).status_code == 200
    sup = pemain("supervisor")
    r = _adj(klien, sup, put, a11a, jenis="SIM_NTB", tahap="SIMULASI", harga="K", mode="target_laju", target=4.0,
             alasan="rekonsiliasi laju dengan rilis")
    assert r.status_code == 201, r.text
    r = klien.post("/api/simulasi/setujui", headers=h_(sup), json={"putaran_id": put, "wilayah": W})
    assert r.status_code == 200 and r.json()["jumlah"] == 1
    proses_semua(uid_worker)
    fin, lalu = hasil(admin_conn, put, a11a, U(2025, 3)), hasil(admin_conn, put, a11a, U(2024, 3))
    assert fin[3] / lalu[3] * 100 - 100 == pytest.approx(4.0, rel=1e-9)
    kom = klien.get(f"/api/kompilasi?putaran_id={put}&wilayah={W}", headers=h_(sup)).json()
    baris = next(b for b in kom["baris"] if b["id"] == a11a)
    assert baris["berdata"] and baris["final"][k][1] == pytest.approx(fin[3])
    assert kom["simulasi"][0]["status"] == "disetujui"
    kat = next(b for b in kom["baris"] if b["kode"] == "A")
    assert not kat["berdata"] and kat["final"][k][1] == pytest.approx(fin[3])  # agregat = jumlah lapus berdata
    # mengubah simulasi mengembalikannya ke draf (angka FINAL kembali BENC)
    r = _adj(klien, sup, put, a11a, jenis="SIM_NTB", tahap="SIMULASI", harga="K", mode="nilai", target=1.0,
             alasan="ubah simulasi setelah rapat")
    assert r.json()["status"] == "draf"
    assert _adj(klien, sup, put, a11a, jenis="SIM_NTB", tahap="SIMULASI", harga="K", mode="target_implisit",
                target=100.0).status_code == 422  # implisit hanya ADHB


def test_biaya_antara_terapkan_rka_td(klien, pemain, siap, admin_conn, uid_worker):
    put, td, lid = siap["put"], siap["td"], siap["lid"]
    op = pemain("operator")
    i1 = isi_rev(klien, op, put, lid["A.1.a"], nama="Padi", rka_td=None)
    i2 = isi_rev(klien, op, put, lid["A.1.a"], nama="Jagung", rka_td=0.9)
    baris = {"tahun_dasar_id": td, "wilayah": W, "lapus_id": lid["A.1.a"], "output": 1000.0, "ba_bahan": 200.0,
             "ba_energi": 50.0, "ba_jasa": 30.0, "ba_sewa": 10.0, "ba_lainnya": 10.0}
    r = klien.put("/api/struktur-biaya", headers=h_(op), json=baris)
    assert r.status_code == 200 and r.json()["rasio_ka"] == pytest.approx(0.3)
    r = klien.put("/api/struktur-biaya", headers=h_(op), json=baris | {"item_id": i2, "ba_total_langsung": 450.0,
                                                                      "ba_bahan": None, "ba_energi": None,
                                                                      "ba_jasa": None, "ba_sewa": None,
                                                                      "ba_lainnya": None})
    assert r.status_code == 200 and r.json()["rasio_ka"] == pytest.approx(0.45)
    assert klien.put("/api/struktur-biaya", headers=h_(op), json=baris | {"lapus_id": lid["B.1"]}).status_code == 403
    tr = {"putaran_id": put, "wilayah": W, "lapus_id": lid["A"]}
    r = klien.post("/api/struktur-biaya/terapkan", headers=h_(op), json=tr)
    assert r.status_code == 200 and r.json()["ringkasan"] == {"tanpa_sumber": 2}  # belum disetujui
    d = klien.get(f"/api/struktur-biaya?tahun_dasar_id={td}&wilayah={W}&lapus_id={lid['A']}", headers=h_(op)).json()
    ids = [b["id"] for b in d["baris"]]
    assert len(ids) == 2 and {i["id"] for i in d["item"]} == {i1, i2}
    assert klien.post("/api/struktur-biaya/setujui", headers=h_(op), json={"id": ids}).status_code == 403
    sup = pemain("supervisor")
    assert klien.post("/api/struktur-biaya/setujui", headers=h_(sup), json={"id": ids}).json()["jumlah"] == 2
    op = pemain("operator")
    r = klien.post("/api/struktur-biaya/terapkan", headers=h_(op), json=tr | {"hanya_kosong": True})
    rinci = {b["id"]: b for b in r.json()["baris"]}
    assert rinci[i1]["sumber"] == "lapus A.1.a" and rinci[i1]["aksi"] == "ubah"
    assert rinci[i2]["sumber"] == "item" and rinci[i2]["aksi"] == "sudah_terisi"
    assert _st(klien, op, put, lid["A.1.a"], "ajukan").status_code == 409  # V02: Padi tanpa RKA_TD
    r = klien.post("/api/struktur-biaya/terapkan", headers=h_(op), json=tr | {"terapkan": True})
    assert r.json()["diterapkan"] == 2
    rka = dict(admin_conn.execute("SELECT item_id, nilai::float8 FROM lk.parameter_item WHERE putaran_id = %s"
                                  " AND kode = 'RKA_TD'", (put,)).fetchall())
    assert rka == {i1: pytest.approx(0.3), i2: pytest.approx(0.45)}
    assert _st(klien, op, put, lid["A.1.a"], "ajukan").status_code == 200
    # terapkan lagi mengubah jangkar -> lapus kembali draf hanya bila ada yang berubah
    r = klien.post("/api/struktur-biaya/terapkan", headers=h_(op), json=tr | {"terapkan": True})
    assert r.json()["diterapkan"] == 0 and status(admin_conn, put, lid["A.1.a"]) == "diajukan"
    proses_semua(uid_worker)
    h = hasil(admin_conn, put, lid["A.1.a"], U(2025, 1), "BENC")
    assert h[3] == pytest.approx((1 - 0.3) * (100 + 2 * 4) * _harga_t0(admin_conn, put, i1) +
                                 (1 - 0.45) * (100 + 2 * 4) * _harga_t0(admin_conn, put, i2))


def _harga_t0(admin_conn, put, iid) -> float:
    """Harga tahun dasar REV (TD2025) = Σ output 2025 ÷ Σ kuantum 2025 (docs/02 §2)."""
    q = {u: 100 + 2 * i for i, u in enumerate(PER)}
    hrg = {u: 2.0 + 0.01 * i for i, u in enumerate(PER)}
    t0 = [U(2025, x) for x in (1, 2, 3, 4)]
    return sum(q[u] * hrg[u] for u in t0) / sum(q[u] for u in t0)


def test_bandingkan_putaran(klien, pemain, siap, admin_conn, uid_worker):
    op = pemain("operator")
    a11a = siap["lid"]["A.1.a"]
    iid = isi_rev(klien, op, siap["put"], a11a)
    adm = pemain("admin")
    baru = buka(klien, adm, siap["td"], nama="Putaran revisi", sumber=siap["put"], triwulan=2)
    klien.put("/api/data-dasar/nilai", headers=h_(adm), json={"putaran_id": baru, "perubahan": [
        {"item_id": iid, "seri": "KUANTUM", "periode": U(2025, 2), "nilai": 999.0},
        {"item_id": iid, "seri": "HARGA", "periode": U(2026, 2), "nilai": 2.2}]})
    proses_semua(uid_worker)
    r = klien.get(f"/api/putaran/{siap['put']}/banding/{baru}?wilayah={W}", headers=h_(adm))
    assert r.status_code == 200, r.text
    d = r.json()
    b = next(x for x in d["baris"] if x["id"] == a11a)
    assert b["data"] == {"baru": 1, "hilang": 0, "berubah": 1}
    k = str(U(2025, 2))
    q1 = str(U(2025, 1))
    assert b["a"][k][0] != b["b"][k][0] and b["a"][q1][0] == b["b"][q1][0]  # ADHB Q1 tetap
    assert b["a"][q1][1] != b["b"][q1][1]  # ADHK ikut berubah: harga tahun dasar 2025 dari data (TD2025)
    assert d["periode"][-1]["urut"] == U(2026, 2)
    sel = klien.get(f"/api/putaran/{siap['put']}/banding/{baru}/data?wilayah={W}&lapus_id={a11a}",
                    headers=h_(adm)).json()
    assert {(s["seri"], s["lama"], s["baru"]) for s in sel} == {("KUANTUM", 110.0, 999.0), ("HARGA", None, 2.2)}
    lain = buka(klien, adm, siap["td"] + 0, nama="Lain", triwulan=3)
    assert klien.get(f"/api/putaran/{siap['put']}/banding/{lain}?wilayah={W}", headers=h_(adm)).status_code == 200
    assert math.isfinite(b["b"][k][1])
