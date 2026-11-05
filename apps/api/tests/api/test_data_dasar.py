"""API Data Dasar (F3): + Komoditas, simpan sel (kosong != nol), jangkar, nonaktif, sambung + usulan jangkar, tautan,
seri referensi, grid (kontribusi, validasi), konfirmasi V05, hak tulis per penugasan, putaran terkunci (423),
impor operator (baris tak ditugaskan dilewati). Angka fiktif."""
from __future__ import annotations

import io

import openpyxl
import pytest

from sinergi_api.data_dasar.router import usulan_jangkar
from sinergi_api.worker.antrean import proses_semua
from tests.conftest import tanpa_uid

pytestmark = pytest.mark.db
W = "6500"


def U(y: int, q: int) -> int:
    return y * 4 + q - 1


@pytest.fixture
def siap(admin_conn, td_salin, putaran_uji):
    """Tahun dasar salinan TD2025 + putaran 2024Q1–2026Q1; kembalikan dict id lapus."""
    td = td_salin("TD2025")
    put = putaran_uji(td, awal=(2024, 1), akhir=(2026, 1))
    lid = dict(admin_conn.execute("SELECT kode, id FROM ref.lapus WHERE tahun_dasar_id = %s", (td,)).fetchall())
    return {"td": td, "put": put, "lid": lid}


@pytest.fixture
def tugaskan(admin_conn):
    def _t(uid: int, td: int, lapus_id: int, wilayah: str = W) -> None:
        admin_conn.execute("INSERT INTO lk.penugasan (pengguna_id, tahun_dasar_id, wilayah_kode, lapus_id, peran_tugas)"
                           " VALUES (%s, %s, %s, %s, 'operator')", (uid, td, wilayah, lapus_id))
    return _t


def _h(h):
    return tanpa_uid(h)


def _tambah(klien, h, siap, lapus="A.1.a", metode="REV", nama="Padi", **kw):
    r = klien.post("/api/data-dasar/item", headers=_h(h), json={
        "putaran_id": siap["put"], "wilayah": W, "lapus_id": siap["lid"][lapus], "metode": metode, "nama": nama,
        "alasan": "komoditas baru uji API", **kw})
    return r


def _nilai(klien, h, siap, perubahan):
    return klien.put("/api/data-dasar/nilai", headers=_h(h), json={"putaran_id": siap["put"], "perubahan": perubahan})


def test_operator_tambah_isi_grid_dan_hak_tulis(klien, sebagai, siap, tugaskan, admin_conn, uid_worker):
    h = sebagai("operator")
    tugaskan(int(h["_uid"]), siap["td"], siap["lid"]["A.1.a"])
    r = _tambah(klien, h, siap)
    assert r.status_code == 201, r.text
    iid, no = r.json()["id"], r.json()["nomor"]
    assert no == 1
    assert _tambah(klien, h, siap, lapus="B.2").status_code == 403  # tidak ditugaskan
    assert _tambah(klien, h, siap, metode="EKS", nama="Indeks X").status_code == 422  # EKS tanpa jenis indeks
    per = [U(2024, q) for q in (1, 2, 3, 4)] + [U(2025, q) for q in (1, 2, 3, 4)] + [U(2026, 1)]
    ubah = [{"item_id": iid, "seri": "KUANTUM", "periode": u, "nilai": 100.0 + i} for i, u in enumerate(per)]
    ubah += [{"item_id": iid, "seri": "HARGA", "periode": u, "nilai": 2.5} for u in per[:-1]]
    ubah += [{"item_id": iid, "seri": "HARGA", "periode": per[-1], "tidak_tersedia": True}]
    ubah += [{"item_id": iid, "seri": "RKA", "periode": u, "nilai": 0.3} for u in per]
    r = _nilai(klien, h, siap, ubah)
    assert r.status_code == 200, r.text
    assert r.json()["tidak_tersedia"] == 1
    assert _nilai(klien, h, siap, [{"item_id": iid, "seri": "NILAI", "periode": per[0], "nilai": 1}]).status_code \
        == 422  # seri bukan milik REV
    assert _nilai(klien, h, siap, [{"item_id": iid, "seri": "KUANTUM", "periode": U(2023, 4), "nilai": 1}]) \
        .status_code == 422  # di luar cakupan putaran
    # jangkar: RKA_TD tanpa alasan boleh; H_TD wajib beralasan
    r = klien.put("/api/data-dasar/parameter", headers=_h(h), json={"putaran_id": siap["put"], "item_id": iid,
                                                                     "kode": "RKA_TD", "nilai": 0.3})
    assert r.status_code == 200, r.text
    r = klien.put("/api/data-dasar/parameter", headers=_h(h), json={"putaran_id": siap["put"], "item_id": iid,
                                                                     "kode": "H_TD", "nilai": 2.0})
    assert r.status_code == 422
    proses_semua(uid_worker)
    g = klien.get(f"/api/data-dasar/grid?putaran_id={siap['put']}&wilayah={W}&lapus_id={siap['lid']['A']}")
    assert g.status_code == 200, g.text
    d = g.json()
    it = next(x for x in d["item"] if x["id"] == iid)
    assert it["boleh_tulis"] and [s["kode"] for s in it["seri"]][:3] == ["KUANTUM", "HARGA", "IH"]
    harga = next(s for s in it["seri"] if s["kode"] == "HARGA")
    assert harga["tidak_tersedia"] == [U(2026, 1)] and str(U(2026, 1)) not in harga["nilai"]
    assert it["kontribusi"][str(U(2025, 1))] == [100.0, 100.0]
    assert d["antrean"]["berjalan"] == 0 and d["antrean"]["terakhir"]["status"] == "selesai"
    # sel tidak_tersedia tidak ditandai V01; RKA_TD ada -> tidak ada V02 tahun dasar
    assert not [v for v in d["validasi"] if v["kode"] == "V01" and v["item_id"] == iid]
    assert not [v for v in d["validasi"] if v["kode"] == "V02" and v["item_id"] == iid]
    assert [v for v in d["validasi"] if v["kode"] == "V13"]  # lapus lain tanpa item
    hasil = admin_conn.execute("SELECT count(*) FROM lk.hasil_item WHERE putaran_id = %s AND item_id = %s",
                               (siap["put"], iid)).fetchone()[0]
    assert hasil == 9


def test_nonaktif_masa_berlaku_dan_terkunci(klien, sebagai, siap, admin_conn):
    h = sebagai("admin")
    iid = _tambah(klien, h, siap).json()["id"]
    r = klien.patch(f"/api/data-dasar/item/{iid}", headers=_h(h), json={"putaran_id": siap["put"], "status": "nonaktif",
                                                                        "alasan": "komoditas tidak ada lagi"})
    assert r.status_code == 200, r.text
    r = klien.patch(f"/api/data-dasar/item/{iid}", headers=_h(h), json={
        "putaran_id": siap["put"], "mulai": U(2025, 3), "selesai": U(2025, 1), "alasan": "masa berlaku salah urut"})
    assert r.status_code == 422
    r = klien.patch(f"/api/data-dasar/item/{iid}", headers=_h(h), json={"putaran_id": siap["put"], "status": "aktif",
                                                                        "alasan": "pendek"})
    assert r.status_code == 422  # alasan min. 10 karakter
    st = admin_conn.execute("SELECT status FROM lk.item WHERE id = %s", (iid,)).fetchone()[0]
    assert st == "nonaktif"
    admin_conn.execute("UPDATE lk.putaran SET status = 'terkunci' WHERE id = %s", (siap["put"],))
    r = _nilai(klien, h, siap, [{"item_id": iid, "seri": "KUANTUM", "periode": U(2025, 1), "nilai": 1.0}])
    assert r.status_code == 423


def test_sambung_dan_usulan_jangkar(klien, sebagai, siap, admin_conn):
    h = sebagai("admin")
    lama = _tambah(klien, h, siap, nama="Ikan spesies X").json()["id"]
    baru = _tambah(klien, h, siap, nama="Ikan agregat DKP").json()["id"]
    o = [U(2024, q) for q in (1, 2, 3, 4)]
    t0 = [U(2025, q) for q in (1, 2, 3, 4)]
    ubah = [{"item_id": lama, "seri": s, "periode": u, "nilai": x} for u in o for s, x in (("KUANTUM", 10.0),
                                                                                         ("HARGA", 3.0))]
    ubah += [{"item_id": baru, "seri": s, "periode": u, "nilai": x} for u in o + t0 for s, x in (("KUANTUM", 50.0),
                                                                                              ("HARGA", 2.0))]
    assert _nilai(klien, h, siap, ubah).status_code == 200
    r = klien.post(f"/api/data-dasar/item/{lama}/sambung", headers=_h(h), json={
        "putaran_id": siap["put"], "penerus_id": baru, "alasan": "rebasing spesies ke agregat"})
    assert r.status_code == 200, r.text
    d = r.json()
    assert "V03" in d["pesan"] and isinstance(d["catatan"], list)
    h_td = next(x for x in d["usulan"] if x["kode"] == "H_TD")
    assert h_td["nilai"] == pytest.approx(2.0 * 3.0 / 2.0) and len(h_td["overlap"]) == 4
    asal = admin_conn.execute("SELECT item_asal_id FROM lk.item WHERE id = %s", (baru,)).fetchone()[0]
    assert asal == lama


def test_usulan_jangkar_ih_dan_tanpa_overlap():
    t0 = [U(2025, q) for q in (1, 2, 3, 4)]
    lama = {"metode": "DEF", "seri": {"IH": {U(2024, 1): 90.0, U(2024, 2): 110.0}}, "param": {}}
    baru = {"metode": "EKS", "seri": {"IH": {U(2024, 1): 45.0, U(2024, 2): 55.0, **{u: 120.0 for u in t0}}},
            "param": {"RKA_TD": 0.2}}
    r = usulan_jangkar(lama, baru, t0, True)
    ih = next(x for x in r["usulan"] if x["kode"] == "IH_TD")
    assert ih["nilai"] == pytest.approx(120.0 * 100.0 / 50.0)
    assert next(x for x in r["usulan"] if x["kode"] == "RKA_TD")["nilai"] == 0.2
    assert any("kurang dari satu tahun" in p for p in r["catatan"])
    kosong = usulan_jangkar({"metode": "REV", "seri": {"KUANTUM": {1: 1.0}}, "param": {}},
                            {"metode": "REV", "seri": {"KUANTUM": {2: 1.0}}, "param": {}}, t0, True)
    assert kosong["usulan"] == [] and any("Tidak ada triwulan overlap" in p for p in kosong["catatan"])


def test_tautan_seri_referensi_dan_hak_seri_ref(klien, sebagai, siap, tugaskan, uid_worker):
    adm = sebagai("admin")
    r = klien.post("/api/seri-referensi", headers=_h(adm), json={"kode": f"REF_UJI_{siap['put']}",
                                                                 "nama": "Indeks uji", "jenis": "indeks_harga"})
    assert r.status_code == 201, r.text
    sid = r.json()["id"]
    r = klien.put("/api/seri-referensi/nilai", headers=_h(adm), json={
        "putaran_id": siap["put"], "wilayah": W, "perubahan": [{"seri_id": sid, "periode": U(2025, q), "nilai": 100.0}
                                                              for q in (1, 2, 3, 4)]})
    assert r.status_code == 200, r.text
    iid = _tambah(klien, adm, siap, metode="DEF", nama="Jasa X").json()["id"]
    r = klien.put(f"/api/data-dasar/item/{iid}/tautan", headers=_h(adm), json={
        "putaran_id": siap["put"], "jenis_seri": "IH", "sumber": "SERI_REFERENSI", "seri_id": sid})
    assert r.status_code == 200, r.text
    assert _nilai(klien, adm, siap, [{"item_id": iid, "seri": "IH", "periode": U(2025, 1), "nilai": 1}]).status_code \
        == 422  # seri tertaut tidak dapat diketik
    r = klien.put(f"/api/data-dasar/item/{iid}/tautan", headers=_h(adm), json={
        "putaran_id": siap["put"], "jenis_seri": "IH", "sumber": "RUMUS", "rumus": "TPK_X_KAMAR"})
    assert r.status_code == 422  # rumus hanya untuk sasarannya
    _nilai(klien, adm, siap, [{"item_id": iid, "seri": "OUT_ADHB", "periode": U(2025, q), "nilai": 10.0}
                              for q in (1, 2, 3, 4)])
    proses_semua(uid_worker)
    g = klien.get(f"/api/data-dasar/grid?putaran_id={siap['put']}&wilayah={W}&lapus_id={siap['lid']['A.1.a']}").json()
    ih = next(s for x in g["item"] if x["id"] == iid for s in x["seri"] if s["kode"] == "IH")
    assert ih["tautan"]["teks"] == f"REF: REF_UJI_{siap['put']}" and ih["nilai_turunan"][str(U(2025, 1))] == 100.0
    # operator tanpa izin data.tulis_semua tidak dapat membuat/mengisi seri referensi bersama (RLS)
    op = sebagai("operator")
    tugaskan(int(op["_uid"]), siap["td"], siap["lid"]["A.1.a"])
    r = klien.post("/api/seri-referensi", headers=_h(op), json={"kode": f"REF_OP_{siap['put']}", "nama": "x y",
                                                                "jenis": "harga"})
    assert r.status_code == 403
    r = klien.put("/api/seri-referensi/nilai", headers=_h(op), json={
        "putaran_id": siap["put"], "wilayah": W, "perubahan": [{"seri_id": sid, "periode": U(2025, 1), "nilai": 1.0}]})
    assert r.status_code == 403


def test_v05_konfirmasi_bertahan_setelah_hitung_ulang(klien, sebagai, siap, uid_worker):
    h = sebagai("admin")
    a = _tambah(klien, h, siap, nama="Ubi Kayu").json()["id"]
    b = _tambah(klien, h, siap, metode="DEF", nama="ubi  kayu").json()["id"]
    proses_semua(uid_worker)
    q = f"/api/validasi?putaran_id={siap['put']}&wilayah={W}&lapus_id={siap['lid']['A.1.a']}"
    v5 = [v for v in klien.get(q).json() if v["kode"] == "V05"]
    assert {v["item_id"] for v in v5} == {a, b} and all(v["boleh_konfirmasi"] for v in v5)
    r = klien.post("/api/validasi/konfirmasi", headers=_h(h), json={
        "putaran_id": siap["put"], "wilayah": W, "lapus_id": siap["lid"]["A.1.a"], "kode": "V05",
        "kunci": v5[0]["kunci"], "alasan": "Ubi kayu DEF adalah olahan, bukan produksi"})
    assert r.status_code == 200, r.text
    klien.post("/api/hitung", headers=_h(h), json={"putaran_id": siap["put"], "wilayah": W})
    proses_semua(uid_worker)
    assert all(v["dikonfirmasi"] for v in klien.get(q).json() if v["kode"] == "V05")
    r = klien.post("/api/validasi/konfirmasi", headers=_h(h), json={
        "putaran_id": siap["put"], "wilayah": W, "lapus_id": siap["lid"]["B"], "kode": "V13", "kunci": "-",
        "alasan": "tidak boleh dikonfirmasi"})
    assert r.status_code == 422


def _templat_mini(lapus: list[str]) -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "A"
    ws.append([])
    ws.append([])
    ws.append([])
    ws.append(["Kode Wilayah", "Kode Lapus", "Metode", "No Item", "Komoditas / Rincian", "Kode Seri", "Satuan",
               "Jangkar Tahun Dasar", "2025-T1", "2025-T2", "Seri", "Jenis Indeks (EKS)", "Sumber Data",
               "Tautan / Rumus", "Kode LK BPS", "Catatan", "Lokasi Sumber"])
    for lap in lapus:
        ws.append([W, lap, "REV", 1, f"Komoditas {lap}", "KUANTUM", "ton", None, 10, 11])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_impor_operator_baris_tidak_ditugaskan_dilewati(klien, sebagai, siap, tugaskan):
    h = sebagai("operator")
    tugaskan(int(h["_uid"]), siap["td"], siap["lid"]["A.1.a"])
    data = _templat_mini(["A.1.a", "A.1.b"])
    hd = {**_h(h), "Content-Type": "application/octet-stream"}
    r = klien.post(f"/api/impor/templat?putaran_id={siap['put']}&nama=mini.xlsx", content=data, headers=hd)
    assert r.status_code == 200, r.text
    p = r.json()
    assert p["ringkasan"]["item_baru"] == 1 and p["ringkasan"]["dilewati"] == 1
    assert klien.post(f"/api/impor/{p['impor_id']}/terapkan", content=_templat_mini(["A.1.a"]), headers=hd) \
        .status_code == 409  # berkas berbeda
    assert klien.post(f"/api/impor/{p['impor_id']}/terapkan", content=data, headers=hd).status_code == 200
    assert klien.post(f"/api/impor/{p['impor_id']}/terapkan", content=data, headers=hd).status_code == 409
    # opsi kosongkan hanya admin
    r = klien.post(f"/api/impor/templat?putaran_id={siap['put']}&nama=mini.xlsx&kosongkan=true", content=data,
                   headers=hd)
    assert r.status_code == 403


def test_impor_galat_format_dan_data_mikro(klien, sebagai, siap):
    h = sebagai("admin")
    wb = openpyxl.load_workbook(io.BytesIO(_templat_mini(["A.1.a"])))
    ws = wb["A"]
    ws.append([W, "A.1.a", "REV", 2, "PT Contoh Abadi", "KUANTUM", "ton", None, 5])
    ws.append([W, "A.1.a", "REV", 3, "Jagung", "KUANTUM", "ton", None, "dua belas"])
    ws.append([W, "B.2", "REV", 1, "Batu bara", "KUANTUM", "ton", None, 1])
    buf = io.BytesIO()
    wb.save(buf)
    hd = {**_h(h), "Content-Type": "application/octet-stream"}
    p = klien.post(f"/api/impor/templat?putaran_id={siap['put']}&nama=salah.xlsx", content=buf.getvalue(),
                   headers=hd).json()
    teks = [x["teks"] for x in p["pesan"] if x["tingkat"] == "galat"]
    assert not p["dapat_diterapkan"]
    assert any("data mikro" in t for t in teks)
    assert any("bukan angka" in t for t in teks)
    assert any("bukan bagian sheet A" in t for t in teks)
    assert all(not any(c.isdigit() for c in t.replace("A.1", "")) for t in teks if "mikro" in t)
    assert klien.post(f"/api/impor/{p['impor_id']}/terapkan", content=buf.getvalue(), headers=hd).status_code == 409


def test_v15_hasil_tersimpan_vs_hitung_ulang(klien, sebagai, siap, admin_conn, uid_worker):
    h = sebagai("admin")
    iid = _tambah(klien, h, siap).json()["id"]
    _nilai(klien, h, siap, [{"item_id": iid, "seri": "KUANTUM", "periode": U(2025, 1), "nilai": 5.0}])
    proses_semua(uid_worker)
    q = f"/api/validasi/kunci?putaran_id={siap['put']}&wilayah={W}"
    d = klien.get(q).json()
    assert not [b for b in d["blokir"] if b["kode"] == "V15"]
    assert any(b["kode"] == "V13" for b in d["blokir"]) and not d["boleh_kunci"]
    # ubah data tanpa hitung ulang (meniru hasil usang, temuan T3) -> V15
    admin_conn.execute("UPDATE lk.nilai_item SET nilai = 6 WHERE putaran_id = %s AND item_id = %s",
                       (siap["put"], iid))
    v15 = [b for b in klien.get(q).json()["blokir"] if b["kode"] == "V15"]
    assert v15 and "A.1.a" in v15[0]["kode_lapus"]
