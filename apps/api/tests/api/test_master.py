"""Uji F1 master: tahun dasar, pohon lapus (urutan DFS), kelompok, konkordansi, katalog, satuan, sumber, wilayah.

Kriteria F1: admin dapat menambah subkategori atau kelompok tanpa mengubah kode, dan tabel pokok (lk.v_tabel_pokok)
langsung mengikuti urutan baru.
"""
from __future__ import annotations

import pytest

from tests.conftest import tanpa_uid

pytestmark = pytest.mark.db


def _pohon(klien, td_id: int) -> list[dict]:
    r = klien.get(f"/api/tahun-dasar/{td_id}/lapus")
    assert r.status_code == 200
    return r.json()


def _id(pohon: list[dict], kode: str) -> int:
    return next(x["id"] for x in pohon if x["kode"] == kode)


def _baris_tabel_pokok(admin_conn, td_id: int) -> list[str]:
    """Urutan baris lk.v_tabel_pokok untuk satu putaran uji (format tabel pokok)."""
    pid = admin_conn.execute(
        "INSERT INTO lk.putaran (tahun_dasar_id, tahun, triwulan, nomor, nama, jenis, status, periode_awal_id,"
        " periode_akhir_id) VALUES (%s, 2026, 1, (SELECT coalesce(max(nomor), 0) + 1 FROM lk.putaran), 'Uji F1',"
        " 'REGULER', 'terbuka', (SELECT id FROM ref.periode WHERE tahun = 2026 AND triwulan = 1),"
        " (SELECT id FROM ref.periode WHERE tahun = 2026 AND triwulan = 1)) RETURNING id", (td_id,)).fetchone()[0]
    return [r[0] for r in admin_conn.execute(
        "SELECT kode_lapus FROM lk.v_tabel_pokok WHERE putaran_id = %s AND wilayah_kode = '6500' ORDER BY urutan",
        (pid,)).fetchall()]


def _cek_dfs(pohon: list[dict]) -> None:
    """Invarian: urutan 1..N, anak tepat di bawah induk (DFS), level = kedalaman."""
    assert [x["urutan"] for x in pohon] == list(range(1, len(pohon) + 1))
    pos = {x["id"]: i for i, x in enumerate(pohon)}
    lv = {x["id"]: x["level"] for x in pohon}
    for x in pohon:
        if x["induk_id"] is not None:
            assert pos[x["induk_id"]] < pos[x["id"]]
            assert x["level"] == lv[x["induk_id"]] + 1
            antara = pohon[pos[x["induk_id"]] + 1: pos[x["id"]]]
            assert all(a["level"] > lv[x["induk_id"]] for a in antara), f"{x['kode']} terpisah dari induknya"


# ------------------------------------------------------------------ tahun dasar
def test_tahun_dasar_crud_dan_salin_pohon(klien, sebagai, td_uji):
    h = sebagai("admin")
    td = td_uji(h)
    assert td["lapus_disalin"] == 102 and td["jangkar_dari_data"] is True
    pohon = _pohon(klien, td["id"])
    _cek_dfs(pohon)
    tuv = next(x for x in pohon if x["kode"] == "TUV")
    assert [next(p["kode"] for p in pohon if p["id"] == a) for a in tuv["anggota"]] == ["T", "U", "V"]
    r = klien.patch(f"/api/tahun-dasar/{td['id']}", headers=tanpa_uid(h),
                    json={"status": "paralel", "jangkar_dari_data": False})
    assert r.json()["status"] == "paralel" and r.json()["jangkar_dari_data"] is False
    r = klien.patch(f"/api/tahun-dasar/{td['id']}", headers=tanpa_uid(h), json={"tahun_awal_seri": 2030})
    assert r.status_code == 422 and "baseline" in r.json()["pesan"]
    # Tidak dipakai data -> terhapus beserta pohonnya
    r = klien.delete(f"/api/tahun-dasar/{td['id']}", headers=tanpa_uid(h))
    assert r.json()["hasil"] == "dihapus"


def test_seed_jangkar_dari_data_dan_pdrb_nm(klien, sebagai):
    sebagai("operator")
    td = {t["kode"]: t for t in klien.get("/api/tahun-dasar").json()}
    assert td["TD2025"]["jangkar_dari_data"] is True and td["TD2010"]["jangkar_dari_data"] is False
    for kode in ("TD2010", "TD2025"):
        pohon = _pohon(klien, td[kode]["id"])
        _cek_dfs(pohon)  # seed asli sudah berurutan DFS
        assert pohon[-1]["kode"] == "PDRB.NM" and pohon[-1]["jenis"] == "pdrb_nonmigas"


# ------------------------------------------------------------------ pohon lapus
def test_tambah_subkategori_langsung_di_tabel_pokok(klien, sebagai, td_uji, admin_conn):
    h = sebagai("admin")
    td = td_uji(h)
    pohon = _pohon(klien, td["id"])
    # Subkategori baru di bawah C.2, tepat sesudah C.2.14 (mis. pemisahan industri aluminium)
    r = klien.post(f"/api/tahun-dasar/{td['id']}/lapus", headers=tanpa_uid(h), json={
        "kode": "C.2.14a", "nama": "Industri Aluminium", "jenis": "daun", "induk_id": _id(pohon, "C.2"),
        "sesudah_id": _id(pohon, "C.2.14")})
    assert r.status_code == 201, r.text
    assert r.json()["level"] == 3
    pohon = _pohon(klien, td["id"])
    _cek_dfs(pohon)
    kode = [x["kode"] for x in pohon]
    assert kode[kode.index("C.2.14") + 1] == "C.2.14a"
    baris = _baris_tabel_pokok(admin_conn, td["id"])
    assert baris == kode  # tabel pokok = pohon, urut sama, termasuk baris baru
    assert baris.index("C.2.14a") == baris.index("C.2.14") + 1


def test_tambah_kelompok_dan_anggota(klien, sebagai, td_uji, admin_conn):
    h = sebagai("admin")
    td = td_uji(h)
    pohon = _pohon(klien, td["id"])
    r = klien.post(f"/api/tahun-dasar/{td['id']}/lapus", headers=tanpa_uid(h), json={
        "kode": "Q,R", "nama": "Jasa Pendidikan dan Kesehatan (kelompok publikasi)", "jenis": "kelompok",
        "sesudah_id": _id(pohon, "R")})
    assert r.status_code == 201, r.text
    kid = r.json()["id"]
    r = klien.put(f"/api/lapus/{kid}/anggota", headers=tanpa_uid(h),
                  json={"anggota_ids": [_id(pohon, "Q"), _id(pohon, "R")]})
    assert r.json()["anggota"] == ["Q", "R"]
    baris = _baris_tabel_pokok(admin_conn, td["id"])
    assert baris.index("Q,R") == baris.index("R.3") + 1  # sesudah seluruh subtree R, sebelum S
    assert baris[baris.index("Q,R") + 1] == "S"
    # Anggota tidak boleh induk + turunannya (hitung ganda) atau baris total
    r = klien.put(f"/api/lapus/{kid}/anggota", headers=tanpa_uid(h),
                  json={"anggota_ids": [_id(pohon, "R"), _id(pohon, "R.1")]})
    assert r.status_code == 422 and "hitung ganda" in r.json()["pesan"]
    r = klien.put(f"/api/lapus/{kid}/anggota", headers=tanpa_uid(h), json={"anggota_ids": [_id(pohon, "PDRB")]})
    assert r.status_code == 422


def test_atur_urutan_saudara_memindahkan_seluruh_cabang(klien, sebagai, td_uji, admin_conn):
    h = sebagai("admin")
    td = td_uji(h)
    pohon = _pohon(klien, td["id"])
    akar = [x["id"] for x in pohon if x["induk_id"] is None]
    # Pindahkan kategori B ke depan A
    a, b = _id(pohon, "A"), _id(pohon, "B")
    baru = [b, a] + [i for i in akar if i not in (a, b)]
    r = klien.put(f"/api/tahun-dasar/{td['id']}/lapus/urutan", headers=tanpa_uid(h),
                  json={"induk_id": None, "anak": baru})
    assert r.status_code == 200 and r.json()["baris_berubah"] > 0
    pohon2 = _pohon(klien, td["id"])
    _cek_dfs(pohon2)
    kode = [x["kode"] for x in pohon2]
    assert kode[:6] == ["B", "B.1", "B.2", "B.3", "B.4", "A"]
    assert _baris_tabel_pokok(admin_conn, td["id"])[:6] == kode[:6]
    # Daftar tidak lengkap ditolak
    r = klien.put(f"/api/tahun-dasar/{td['id']}/lapus/urutan", headers=tanpa_uid(h),
                  json={"induk_id": None, "anak": baru[:-1]})
    assert r.status_code == 422


def test_pindah_induk_dan_validasi_struktur(klien, sebagai, td_uji):
    h = sebagai("admin")
    td = td_uji(h)
    pohon = _pohon(klien, td["id"])
    # Pindahkan E.1 ke bawah E.2 -> level 3
    r = klien.patch(f"/api/lapus/{_id(pohon, 'E.1')}", headers=tanpa_uid(h), json={"induk_id": _id(pohon, "E.2")})
    assert r.status_code == 200 and r.json()["level"] == 3
    _cek_dfs(_pohon(klien, td["id"]))
    # Siklus: E.2 ke bawah E.2.a
    r = klien.patch(f"/api/lapus/{_id(pohon, 'E.2')}", headers=tanpa_uid(h), json={"induk_id": _id(pohon, "E.2.a")})
    assert r.status_code == 422
    # Induk harus kategori/subkategori
    r = klien.post(f"/api/tahun-dasar/{td['id']}/lapus", headers=tanpa_uid(h), json={
        "kode": "F.1", "nama": "x", "jenis": "daun", "induk_id": _id(pohon, "F")})
    assert r.status_code == 422 and "kategori atau subkategori" in r.json()["pesan"]
    # Kelompok tidak boleh berinduk; kode duplikat ditolak
    r = klien.post(f"/api/tahun-dasar/{td['id']}/lapus", headers=tanpa_uid(h), json={
        "kode": "KX", "nama": "x", "jenis": "kelompok", "induk_id": _id(pohon, "C")})
    assert r.status_code == 422
    r = klien.post(f"/api/tahun-dasar/{td['id']}/lapus", headers=tanpa_uid(h), json={
        "kode": "A.1.a", "nama": "duplikat", "jenis": "daun", "induk_id": _id(pohon, "A.1")})
    assert r.status_code == 409
    # F (daun tanpa item) boleh dijadikan kategori lalu diberi sub-lapus
    r = klien.patch(f"/api/lapus/{_id(pohon, 'F')}", headers=tanpa_uid(h), json={"jenis": "kategori"})
    assert r.status_code == 200
    r = klien.post(f"/api/tahun-dasar/{td['id']}/lapus", headers=tanpa_uid(h), json={
        "kode": "F.1", "nama": "Konstruksi Gedung", "jenis": "daun", "induk_id": _id(pohon, "F")})
    assert r.status_code == 201 and r.json()["level"] == 2


def test_hapus_lapus_atau_nonaktifkan_bila_ada_item(klien, sebagai, td_uji, admin_conn):
    h = sebagai("admin")
    td = td_uji(h)
    pohon = _pohon(klien, td["id"])
    # Punya sub-lapus -> ditolak
    assert klien.delete(f"/api/lapus/{_id(pohon, 'A.1')}", headers=tanpa_uid(h)).status_code == 422
    # Tanpa data -> dihapus, urutan dirapikan
    r = klien.delete(f"/api/lapus/{_id(pohon, 'H.1')}", headers=tanpa_uid(h))
    assert r.json()["hasil"] == "dihapus"
    _cek_dfs(_pohon(klien, td["id"]))
    # Sudah punya item -> dinonaktifkan, hilang dari tabel pokok, riwayat tetap
    lid = _id(pohon, "H.2")
    admin_conn.execute("INSERT INTO lk.item (tahun_dasar_id, wilayah_kode, lapus_id, metode_kode, nomor, nama)"
                       " VALUES (%s, '6500', %s, 'REV', 1, 'Penumpang bus')", (td["id"], lid))
    r = klien.delete(f"/api/lapus/{lid}", headers=tanpa_uid(h))
    assert r.json()["hasil"] == "dinonaktifkan"
    assert "H.2" not in _baris_tabel_pokok(admin_conn, td["id"])
    # Jenis daun berisi item tidak boleh diubah menjadi induk
    r = klien.patch(f"/api/lapus/{lid}", headers=tanpa_uid(h), json={"jenis": "sub"})
    assert r.status_code == 422 and "item" in r.json()["pesan"]


def test_nonaktif_induk_butuh_anak_nonaktif(klien, sebagai, td_uji):
    h = sebagai("admin")
    td = td_uji(h)
    pohon = _pohon(klien, td["id"])
    r = klien.patch(f"/api/lapus/{_id(pohon, 'H.3')}", headers=tanpa_uid(h), json={"aktif": False})
    assert r.status_code == 422
    for k in ("H.3.a", "H.3.b", "H.3"):
        assert klien.patch(f"/api/lapus/{_id(pohon, k)}", headers=tanpa_uid(h),
                           json={"aktif": False}).status_code == 200
    r = klien.patch(f"/api/lapus/{_id(pohon, 'H.3.a')}", headers=tanpa_uid(h), json={"aktif": True})
    assert r.status_code == 422 and "induk" in r.json()["pesan"]


def test_operator_tidak_boleh_ubah_master(klien, sebagai, admin_conn):
    h = sebagai("operator")
    td = admin_conn.execute("SELECT id FROM ref.tahun_dasar WHERE kode = 'TD2025'").fetchone()[0]
    assert klien.get(f"/api/tahun-dasar/{td}/lapus").status_code == 200  # baca boleh
    r = klien.post(f"/api/tahun-dasar/{td}/lapus", headers=tanpa_uid(h),
                   json={"kode": "Z", "nama": "x", "jenis": "daun"})
    assert r.status_code == 403
    assert klien.post("/api/satuan", headers=tanpa_uid(h), json={"kode": "x", "nama": "x"}).status_code == 403


# ------------------------------------------------------------------ konkordansi
def test_konkordansi_bobot(klien, sebagai, admin_conn):
    h = sebagai("admin")
    lp = dict(admin_conn.execute(
        "SELECT td.kode || ':' || l.kode, l.id FROM ref.lapus l JOIN ref.tahun_dasar td ON td.id = l.tahun_dasar_id"
        " WHERE (td.kode, l.kode) IN (('TD2010','G.1'),('TD2025','G.1'),('TD2025','G.2'),('TD2025','T.1'))"))
    d = klien.get("/api/konkordansi").json()
    g1 = d["ringkasan_asal"]["G.1"]
    assert g1["jumlah_tujuan"] == 3 and g1["bobot_kosong"] == 3 and g1["lengkap"] is False
    ids = {(b["kode_asal"], b["kode_tujuan"]): b["id"] for b in d["baris"] if b["td_asal"] == "TD2010"}
    for tujuan, w in (("G.1", 0.5), ("G.2", 0.3)):
        assert klien.patch(f"/api/konkordansi/{ids[('G.1', tujuan)]}", headers=tanpa_uid(h),
                           json={"bobot": w}).status_code == 200
    r = klien.patch(f"/api/konkordansi/{ids[('G.1', 'T.1')]}", headers=tanpa_uid(h), json={"bobot": 0.3})
    assert r.status_code == 422 and "lebih dari 1" in r.json()["pesan"]
    assert klien.patch(f"/api/konkordansi/{ids[('G.1', 'T.1')]}", headers=tanpa_uid(h),
                       json={"bobot": 0.2}).status_code == 200
    assert klien.get("/api/konkordansi").json()["ringkasan_asal"]["G.1"]["lengkap"] is True
    r = klien.post("/api/konkordansi", headers=tanpa_uid(h),
                   json={"lapus_asal_id": lp["TD2025:G.1"], "lapus_tujuan_id": lp["TD2025:G.2"]})
    assert r.status_code == 422  # tahun dasar sama


# ------------------------------------------------------------------ referensi sederhana
def test_katalog_normalisasi_sinonim_dan_hapus(klien, sebagai, admin_conn):
    h = sebagai("admin")
    r = klien.post("/api/katalog", headers=tanpa_uid(h), json={
        "nama_baku": "  Ikan   Gurami ", "sinonim": ["Gurame", "gurame", "Ikan Gurami", " Kalui "],
        "satuan_kode": "ton"})
    assert r.status_code == 201, r.text
    k = r.json()
    assert k["nama_baku"] == "Ikan Gurami" and k["sinonim"] == ["Gurame", "Kalui"]
    assert [x["nama_baku"] for x in klien.get("/api/katalog", params={"q": "kalui"}).json()] == ["Ikan Gurami"]
    r = klien.post("/api/katalog", headers=tanpa_uid(h), json={"nama_baku": "gurame"})
    assert r.status_code == 422 and "Ikan Gurami" in r.json()["pesan"]
    assert klien.delete(f"/api/katalog/{k['id']}", headers=tanpa_uid(h)).json()["hasil"] == "dihapus"
    r = klien.post("/api/katalog", headers=tanpa_uid(h), json={"nama_baku": "Ikan Patin"})
    td = admin_conn.execute("SELECT id FROM ref.tahun_dasar WHERE kode = 'TD2025'").fetchone()[0]
    admin_conn.execute(
        "INSERT INTO lk.item (tahun_dasar_id, wilayah_kode, lapus_id, metode_kode, nomor, nama, katalog_id)"
        " SELECT %s, '6503', id, 'REV', 7, 'Ikan Patin', %s FROM ref.lapus WHERE tahun_dasar_id = %s AND kode = 'A.3'",
        (td, r.json()["id"], td))
    assert klien.delete(f"/api/katalog/{r.json()['id']}", headers=tanpa_uid(h)).json()["hasil"] == "dinonaktifkan"


def test_satuan_sumber_wilayah(klien, sebagai, admin_conn):
    h = sebagai("admin")
    assert klien.post("/api/satuan", headers=tanpa_uid(h), json={"kode": "tandan", "nama": "tandan buah segar"}
                      ).status_code == 201
    assert klien.patch("/api/satuan/tandan", headers=tanpa_uid(h), json={"nama": "tandan"}).json()["nama"] == "tandan"
    assert klien.delete("/api/satuan/tandan", headers=tanpa_uid(h)).json()["hasil"] == "dihapus"
    # Satuan 'ton' dipakai katalog/item -> nonaktif
    admin_conn.execute("INSERT INTO ref.katalog_komoditas (nama_baku, satuan_kode) VALUES ('Uji Satuan Ton', 'ton')"
                       " ON CONFLICT DO NOTHING")
    assert klien.delete("/api/satuan/ton", headers=tanpa_uid(h)).json()["hasil"] == "dinonaktifkan"
    admin_conn.execute("UPDATE ref.satuan SET aktif = true WHERE kode = 'ton'")
    s = klien.post("/api/sumber-data", headers=tanpa_uid(h), json={"nama": "DKP Provinsi", "instansi": "DKP"}).json()
    assert klien.patch(f"/api/sumber-data/{s['id']}", headers=tanpa_uid(h),
                       json={"keterangan": "produksi perikanan"}).json()["keterangan"] == "produksi perikanan"
    assert klien.delete(f"/api/sumber-data/{s['id']}", headers=tanpa_uid(h)).json()["hasil"] == "dihapus"
    assert klien.post("/api/wilayah", headers=tanpa_uid(h), json={
        "kode": "6599", "nama": "Wilayah Uji", "level": "kabupaten", "induk": "6500", "urutan": 9}).status_code == 201
    assert klien.delete("/api/wilayah/6599", headers=tanpa_uid(h)).json()["hasil"] == "dihapus"
    # 6500 dipakai (penugasan/item/turunan) -> nonaktif
    assert klien.delete("/api/wilayah/6500", headers=tanpa_uid(h)).json()["hasil"] == "dinonaktifkan"
    admin_conn.execute("UPDATE ref.wilayah SET aktif = true WHERE kode = '6500'")
    assert klien.post("/api/wilayah", headers=tanpa_uid(h), json={
        "kode": "65A1", "nama": "x", "level": "kota"}).status_code == 422


def test_semua_perubahan_master_diaudit(klien, sebagai, admin_conn):
    h = sebagai("admin")
    uid = int(h["_uid"])
    klien.post("/api/satuan", headers={**tanpa_uid(h), "X-Alasan": "satuan%20baru%20sawit"},
               json={"kode": "janjang", "nama": "janjang"})
    klien.patch("/api/wilayah/6571", headers=tanpa_uid(h), json={"urutan": 5})
    rows = admin_conn.execute("SELECT entitas, aksi, alasan FROM audit.log WHERE pengguna_id = %s ORDER BY id",
                              (uid,)).fetchall()
    assert ("ref.satuan", "INSERT", "satuan baru sawit") in rows
    assert any(r[0] == "ref.wilayah" and r[1] == "UPDATE" for r in rows)
