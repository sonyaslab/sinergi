"""Skenario ujung-ke-ujung F4 (kriteria selesai): buka Put -> isi -> adjustment -> ajukan -> setujui -> simulasi ->
kunci (423 untuk semua tulis) -> putaran baru tersalin. Lewat API (TestClient) + worker hitung, angka fiktif."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import psycopg
import pytest

from sinergi_api.worker.antrean import proses_semua
from tests.alur import U, W, buka, h_, hasil, isi_rev, lapus_id, nihil_lainnya, status, tugaskan
from tests.conftest import masuk

pytestmark = pytest.mark.db


@pytest.fixture
def pemain(klien, buat_akun, jam):
    akun: dict[str, object] = {}

    def _jadi(nama: str) -> dict[str, str]:
        if nama not in akun:
            akun[nama] = buat_akun([nama])
        klien.cookies.clear()
        h = masuk(klien, akun[nama], jam)
        h["_uid"] = str(akun[nama].id)  # type: ignore[attr-defined]
        return h

    return _jadi


def test_alur_putaran_ujung_ke_ujung(klien, pemain, td_salin, admin_conn, uid_worker):
    td = td_salin("TD2025")
    lid = lapus_id(admin_conn, td)
    a, b = lid["A.1.a"], lid["A.1.b"]
    T = U(2025, 4)

    # 1) Admin membuka Put 0 (cakupan 2024Q1–2026Q1, cut-off besok) + seri referensi bersama
    adm = pemain("admin")
    besok = (datetime.now(UTC) + timedelta(days=1)).isoformat()
    put = buka(klien, adm, td, nama="Put 0", tanggal_cutoff=besok)
    sid = klien.post("/api/seri-referensi", headers=h_(adm), json={
        "kode": f"REF_E2E_{put}", "nama": "Indeks uji e2e", "jenis": "indeks_harga"}).json()["id"]
    op = pemain("operator")
    for x in (a, b):
        tugaskan(admin_conn, int(op["_uid"]), td, x)

    # 2) Operator mengisi data dasar dua lapus + adjustment (ADJ3 lewat target NTB, ADJ1 pasangan ADHB/ADHK)
    op = pemain("operator")
    ia = isi_rev(klien, op, put, a, nama="Padi")
    isi_rev(klien, op, put, b, nama="Cabai", dasar=40.0)
    proses_semua(uid_worker)
    post_lama = hasil(admin_conn, put, a, U(2025, 2), "PRE")
    r = klien.post("/api/penyesuaian", headers=h_(op), json={
        "putaran_id": put, "wilayah": W, "lapus_id": a, "tahap": "REKON", "jenis": "ADJ3", "harga": "CP",
        "periode": U(2025, 2), "mode": "target_ntb", "target": post_lama[1] * 1.02,
        "alasan": "rekonsiliasi cakupan wilayah"})
    assert r.status_code == 201, r.text
    for harga, v in (("CP", 3.0), ("K", 2.5)):
        r = klien.post("/api/penyesuaian", headers=h_(op), json={
            "putaran_id": put, "wilayah": W, "lapus_id": b, "tahap": "METODE", "metode": "REV", "jenis": "ADJ1",
            "harga": harga, "periode": U(2025, 1), "mode": "nilai", "target": v, "alasan": "tambahan cakupan pasar"})
        assert r.status_code == 201, r.text

    # 3) Ajukan
    for x in (a, b):
        r = klien.post(f"/api/status/{x}/ajukan", headers=h_(op), json={"putaran_id": put, "wilayah": W})
        assert r.status_code == 200, r.text
    r = klien.post(f"/api/status/{lid['A.1.c']}/nihil", headers=h_(op), json={
        "putaran_id": put, "wilayah": W, "catatan": "tidak ada perkebunan semusim"})
    assert r.status_code == 403  # tidak ditugaskan; NIHIL lewat supervisor di bawah

    # 4) Supervisor memutus adjustment dan menyetujui lapus; NIHIL lapus kosong; admin mengecualikan TOP/SOP
    sup = pemain("supervisor")
    ids = [x["id"] for x in klien.get(f"/api/penyesuaian?putaran_id={put}&wilayah={W}&status=diajukan",
                                      headers=h_(sup)).json()]
    assert len(ids) == 3
    assert klien.post("/api/penyesuaian/putus", headers=h_(sup), json={
        "putaran_id": put, "id": ids, "keputusan": "setujui"}).status_code == 200
    for x in (a, b):
        r = klien.post(f"/api/status/{x}/setujui", headers=h_(sup), json={"putaran_id": put, "wilayah": W})
        assert r.status_code == 200, r.text
    r = klien.post(f"/api/status/{lid['A.1.c']}/nihil", headers=h_(sup), json={
        "putaran_id": put, "wilayah": W, "catatan": "tidak ada perkebunan semusim"})
    assert r.status_code == 200, r.text
    nihil_lainnya(admin_conn, put, td)
    adm = pemain("admin")
    for k in ("TOP", "SOP"):
        r = klien.post(f"/api/status/{lid[k]}/kecualikan", headers=h_(adm), json={
            "putaran_id": put, "wilayah": W, "catatan": "data pajak/subsidi belum tersedia"})
        assert r.status_code == 200, r.text
    proses_semua(uid_worker)
    pre = hasil(admin_conn, put, a, U(2025, 2), "POST")
    assert pre[1] == pytest.approx(post_lama[1] * 1.02, rel=1e-9)  # ADJ3 disetujui mencapai target NTB

    # 5) Simulasi (target implisit ADHB) -> setujui -> FINAL
    sup = pemain("supervisor")
    r = klien.get(f"/api/putaran/{put}/syarat-kunci", headers=h_(sup))
    assert r.json()["boleh_kunci"], r.json()
    r = klien.post("/api/penyesuaian", headers=h_(sup), json={
        "putaran_id": put, "wilayah": W, "lapus_id": a, "tahap": "SIMULASI", "jenis": "SIM_NTB", "harga": "CP",
        "periode": T, "mode": "target_implisit", "target": 101.5, "alasan": "rekonsiliasi implisit kompilasi"})
    assert r.status_code == 201, r.text
    s = klien.get(f"/api/putaran/{put}/syarat-kunci", headers=h_(sup)).json()
    assert [x["kode"] for x in s["blokir"]] == ["SIMULASI", "ANTREAN"]  # simpan memicu hitung ulang
    proses_semua(uid_worker)
    s = klien.get(f"/api/putaran/{put}/syarat-kunci", headers=h_(sup)).json()
    assert [x["kode"] for x in s["blokir"]] == ["SIMULASI"]
    r = klien.post(f"/api/putaran/{put}/kunci", headers=h_(sup), json={"alasan": "kunci sebelum simulasi"})
    assert r.status_code == 409 and r.json()["kode"] == "SYARAT_KUNCI"
    assert klien.post("/api/simulasi/setujui", headers=h_(sup), json={"putaran_id": put, "wilayah": W}).json()[
        "jumlah"] == 1
    proses_semua(uid_worker)
    fin = hasil(admin_conn, put, a, T)
    assert fin[1] / fin[3] * 100 == pytest.approx(101.5, rel=1e-9)
    kat = hasil(admin_conn, put, lid["A"], T)
    jml = [x + y for x, y in zip(hasil(admin_conn, put, a, T), hasil(admin_conn, put, b, T), strict=True)]
    assert kat == pytest.approx(jml, rel=1e-12)  # agregat FINAL = Σ lapus berdata

    # 6) Kunci (beralasan) -> semua tulis 423
    assert klien.post(f"/api/putaran/{put}/kunci", headers=h_(sup), json={"alasan": "pendek"}).status_code == 422
    r = klien.post(f"/api/putaran/{put}/kunci", headers=h_(sup), json={"alasan": "Put 0 final disetujui rapat"})
    assert r.status_code == 200, r.text
    al = admin_conn.execute("SELECT alasan FROM audit.log WHERE entitas = 'lk.putaran' AND entitas_id = %s"
                            " ORDER BY id DESC LIMIT 1", (str(put),)).fetchone()[0]
    assert al == "Put 0 final disetujui rapat"
    adm = pemain("admin")
    aid = ids[0]
    P = {"putaran_id": put}
    tulis = [
        ("put", "/api/data-dasar/nilai", P | {"perubahan": [{"item_id": ia, "seri": "KUANTUM", "periode": T,
                                                             "nilai": 1.0}]}),
        ("put", "/api/data-dasar/parameter", P | {"item_id": ia, "kode": "RKA_TD", "nilai": 0.2}),
        ("post", "/api/data-dasar/item", P | {"wilayah": W, "lapus_id": a, "metode": "REV", "nama": "Kedelai",
                                              "alasan": "komoditas baru sesudah kunci"}),
        ("patch", f"/api/data-dasar/item/{ia}", P | {"status": "nonaktif", "alasan": "uji tulis sesudah kunci"}),
        ("put", f"/api/data-dasar/item/{ia}/seri", P | {"seri": ["KUANTUM", "HARGA", "RKA"]}),
        ("patch", f"/api/data-dasar/item/{ia}/seri/HARGA", P | {"satuan": "Rp/kg"}),
        ("put", f"/api/data-dasar/item/{ia}/tautan", P | {"jenis_seri": "IH", "sumber": "SERI_REFERENSI",
                                                          "seri_id": sid}),
        ("post", f"/api/data-dasar/item/{ia}/sambung", P | {"penerus_id": ia + 1, "alasan": "uji tulis sesudah kunci"}),
        ("put", "/api/seri-referensi/nilai", P | {"wilayah": W, "perubahan": [{"seri_id": sid, "periode": T,
                                                                                "nilai": 100.0}]}),
        ("post", "/api/hitung", P | {"wilayah": W}),
        ("post", "/api/validasi/konfirmasi", P | {"wilayah": W, "lapus_id": a, "kode": "V05", "kunci": "-",
                                                  "alasan": "uji tulis sesudah kunci"}),
        ("post", "/api/penyesuaian", P | {"wilayah": W, "lapus_id": a, "tahap": "REKON", "jenis": "ADJ3",
                                          "harga": "CP", "periode": T, "target": 1.0,
                                          "alasan": "uji tulis sesudah kunci"}),
        ("delete", f"/api/penyesuaian/{aid}", None),
        ("post", "/api/penyesuaian/putus", P | {"id": [aid], "keputusan": "tolak", "catatan": "uji tulis kunci"}),
        ("post", "/api/simulasi/setujui", P | {"wilayah": W}),
        ("post", f"/api/status/{a}/kembalikan", P | {"wilayah": W, "catatan": "uji tulis sesudah kunci"}),
        ("post", f"/api/status/{a}/ajukan", P | {"wilayah": W}),
        ("post", f"/api/status/{a}/setujui", P | {"wilayah": W}),
        ("post", f"/api/status/{lid['A.1.d']}/batal", P | {"wilayah": W}),
        ("post", f"/api/status/{lid['TOP']}/batal", P | {"wilayah": W}),
        ("post", "/api/struktur-biaya/terapkan", P | {"wilayah": W, "lapus_id": lid["A"], "terapkan": True}),
        ("patch", f"/api/putaran/{put}", {"nama": "Put 0 ganti nama"}),
    ]
    for metode, jalur, isi in tulis:
        r = getattr(klien, metode)(jalur, headers=h_(adm), **({"json": isi} if isi is not None else {}))
        assert r.status_code == 423, (jalur, r.status_code, r.text)
    r = klien.post(f"/api/impor/templat?putaran_id={put}&nama=uji.xlsx", headers=h_(adm) | {
        "Content-Type": "application/octet-stream"}, content=b"PK\x03\x04 bukan berkas")
    assert r.status_code == 423
    # tingkat basis data: app_rw dengan izin penuh tetap ditolak trigger (P0423)
    uid_adm = int(adm["_uid"])
    with psycopg.connect(_dsn_rw()) as c:
        c.execute("SELECT set_config('app.user_id', %s, false)", (str(uid_adm),))
        for sql in ("UPDATE lk.hasil_lapus SET gva_cp = 0 WHERE putaran_id = %(p)s",
                    "INSERT INTO lk.hasil_validasi (putaran_id, wilayah_kode, lapus_id, kode_validasi, pesan, tingkat)"
                    " VALUES (%(p)s, '6500', %(l)s, 'V01', 'uji', 'info')",
                    "UPDATE lk.status_lapus SET catatan = 'catatan uji kunci' WHERE putaran_id = %(p)s",
                    "UPDATE lk.putaran SET nama = 'x' WHERE id = %(p)s"):
            with pytest.raises(psycopg.Error) as e:
                c.execute(sql, {"p": put, "l": a})
            assert e.value.sqlstate == "P0423", sql
            c.rollback()
            c.execute("SELECT set_config('app.user_id', %s, false)", (str(uid_adm),))
    assert hasil(admin_conn, put, a, T) == pytest.approx(fin, rel=0)

    # 7) Buka kunci hanya admin + alasan; kunci lagi
    sup = pemain("supervisor")
    assert klien.post(f"/api/putaran/{put}/buka-kunci", headers=h_(sup), json={
        "alasan": "koreksi sesudah rilis"}).status_code == 403
    adm = pemain("admin")
    r = klien.post(f"/api/putaran/{put}/buka-kunci", headers=h_(adm), json={"alasan": "koreksi sesudah rilis"})
    assert r.status_code == 200, r.text
    r = klien.post(f"/api/putaran/{put}/kunci", headers=h_(adm), json={"alasan": "kunci ulang tanpa perubahan"})
    assert r.status_code == 200, r.text

    # 8) Putaran baru tersalin dari putaran terkunci; adjustment menjadi draf (keputusan 21)
    put1 = buka(klien, adm, td, nama="Put 1", sumber=put, triwulan=2)
    n = lambda t, p: admin_conn.execute(  # noqa: E731
        f"SELECT count(*) FROM lk.{t} WHERE putaran_id = %s", (p,)).fetchone()[0]
    for t in ("nilai_item", "parameter_item", "nilai_seri_referensi", "penyesuaian"):
        assert n(t, put1) == n(t, put) > 0 or t == "nilai_seri_referensi", t
    st = admin_conn.execute("SELECT DISTINCT status FROM lk.penyesuaian WHERE putaran_id = %s", (put1,)).fetchall()
    assert st == [("draf",)]
    assert status(admin_conn, put1, a) == "belum"
    proses_semua(uid_worker)
    # angka resmi Put 1 = tanpa adjustment (semua draf); pratinjau = angka resmi Put 0
    resmi1 = hasil(admin_conn, put1, a, T)
    assert resmi1 == pytest.approx(hasil(admin_conn, put1, a, T, "PRE"), rel=1e-12)
    prat = klien.get(f"/api/hasil/lapus/{a}?putaran_id={put1}&wilayah={W}&pratinjau=true", headers=h_(adm)).json()
    assert prat["tahap"]["FINAL"][str(T)] == pytest.approx(list(fin), rel=1e-12)
    # Put 1 terbuka untuk ditulis, Put 0 tetap terkunci
    sel = {"perubahan": [{"item_id": ia, "seri": "KUANTUM", "periode": U(2026, 2), "nilai": 130.0}]}
    assert klien.put("/api/data-dasar/nilai", headers=h_(adm), json={"putaran_id": put1, **sel}).status_code == 200
    assert klien.put("/api/data-dasar/nilai", headers=h_(adm), json={"putaran_id": put, **sel}).status_code == 423
    assert status(admin_conn, put1, a) == "draf"


def _dsn_rw() -> str:
    import os

    from sqlalchemy.engine import make_url

    return make_url(os.environ["SINERGI_DB_URL"]).set(drivername="postgresql").render_as_string(hide_password=False)
