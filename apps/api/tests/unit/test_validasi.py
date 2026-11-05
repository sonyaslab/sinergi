"""Uji unit validasi V01–V17 (data_dasar/validasi.py) pada masukan kecil dengan angka fiktif."""
from __future__ import annotations

import pytest

from sinergi_api.data_dasar.validasi import (
    AdjInfo,
    AturanValidasi,
    InfoItem,
    KonteksValidasi,
    _p95,
    ambang_v08,
    validasi,
)
from sinergi_api.engine import (
    DataLapus,
    Item,
    KonfigTD,
    Lapus,
    MasukanWilayah,
    Penyesuaian,
    Sumbu,
    Tautan,
    hitung_wilayah,
    urut,
)

AWAL, AKHIR = urut(2024, 1), urut(2026, 1)
PER = list(range(AWAL, AKHIR + 1))
T0 = [urut(2025, q) for q in (1, 2, 3, 4)]
TINGKAT = {"V01": "blokir_ajukan", "V02": "blokir_ajukan", "V03": "blokir_ajukan", "V04": "peringatan",
           "V05": "blokir_ajukan", "V06": "peringatan", "V07": "peringatan", "V08": "peringatan", "V09": "peringatan",
           "V10": "blokir_ajukan", "V11": "info", "V12": "info", "V13": "blokir_kunci", "V14": "blokir_kunci",
           "V16": "peringatan", "V17": "peringatan"}
PARAM = {"V06": {"toleransi": 0.5}, "V11": {"ambang_persen": 1}, "V05": {"boleh_konfirmasi": True},
         "V08": {"ambang_persen": {"qtq_volume": 30, "yoy_volume": 30, "qtq_implisit": 30, "yoy_implisit": 30},
                 "kalibrasi": "tetap", "p95": {"tahun_awal": 2019, "tahun_akhir": 2025, "min_titik": 8,
                                               "batas_bawah_persen": None}, "per_lapus": {}}}
WAJIB = {"REV": {"KUANTUM", "HARGA", "RKA"}, "EKS": {"INDEKS", "IH", "RKA"}, "DEF": {"OUT_ADHB", "IH"}}
POHON = [Lapus(1, "A.1", "daun", None, 1), Lapus(2, "TOP", "top", None, 2), Lapus(3, "SOP", "sop", None, 3),
         Lapus(4, "B", "daun", None, 4)]
KODE = {1: ("A.1", "daun"), 2: ("TOP", "top"), 3: ("SOP", "sop"), 4: ("B", "daun")}


def s(f) -> dict[int, float]:
    return {u: float(f(i)) for i, u in enumerate(PER)}


def rev(iid: int, **kw) -> Item:
    seri = {"KUANTUM": s(lambda i: 100 + i), "HARGA": s(lambda i: 2.0), "RKA": s(lambda i: 0.3)}
    seri.update(kw.pop("seri", {}))
    return Item(iid, "REV", seri=seri, parameter=kw.pop("parameter", {"RKA_TD": 0.3}), **kw)


def jalankan(data: dict[int, list[Item]], adj: dict[int, list[Penyesuaian]] | None = None, jdd: bool = True,
             info: dict[int, InfoItem] | None = None, adj_info: list[AdjInfo] | None = None,
             aturan: dict | None = None, status: dict | None = None, konfirmasi: dict | None = None,
             tahun_dasar: int = 2025):
    adj = adj or {}
    m = MasukanWilayah(KonfigTD(2025, jdd), Sumbu(AWAL, AKHIR), POHON,
                       {lid: DataLapus(its, adj.get(lid, [])) for lid, its in data.items()})
    h = hitung_wilayah(m)
    semua = {it.id: (lid, it) for lid, its in data.items() for it in its}
    inf = {iid: InfoItem(iid, lid, it.metode, f"Komoditas {iid}", iid) for iid, (lid, it) in semua.items()}
    inf.update(info or {})
    k = KonteksValidasi("TD2025", tahun_dasar, AWAL, AKHIR, inf, KODE,
                        {kd: AturanValidasi(t, dict(PARAM.get(kd, {}))) for kd, t in TINGKAT.items()} | (aturan or {}),
                        WAJIB, adj_info or [], {2: "nihil", 3: "nihil", 4: "nihil"} if status is None else status,
                        konfirmasi or {})
    return validasi(m, h, k)


def kode(ts, k: str, item: int | None = None):
    return [t for t in ts if t.kode == k and (item is None or t.item_id == item)]


def test_bersih_tanpa_temuan_blokir():
    ts = jalankan({1: [rev(1)]})
    assert not [t for t in ts if t.tingkat.startswith("blokir")], [(t.kode, t.pesan) for t in ts]


def test_v01_v17_sel_wajib_periode_berjalan_kosong_ne_nol():
    a = rev(1, seri={"HARGA": {u: 2.0 for u in PER if u != AKHIR}})
    b = rev(2, seri={"KUANTUM": {}, "HARGA": {}})
    c = rev(3, seri={"HARGA": {u: 2.0 for u in PER if u != AKHIR}})
    info = {3: InfoItem(3, 1, "REV", "Komoditas 3", 3, tidak_tersedia={("HARGA", AKHIR)})}
    ts = jalankan({1: [a, b, c]}, info=info)
    assert [(t.jenis_seri, t.periode) for t in kode(ts, "V01", 1)] == [("HARGA", AKHIR)]
    assert {t.jenis_seri for t in kode(ts, "V01", 2)} == {"HARGA", "KUANTUM"}
    assert kode(ts, "V17", 2) and not kode(ts, "V17", 1)
    assert not kode(ts, "V01", 3)  # tidak_tersedia: kosong bukan "belum diisi"


def test_v01_seri_tertaut_diganti_komponen():
    it = Item(1, "REV", seri={"TPK": s(lambda i: 50), "HARGA": s(lambda i: 1), "RKA": s(lambda i: 0.2)},
              parameter={"RKA_TD": 0.2}, tautan=(Tautan("KUANTUM", "RUMUS", "TPK_X_KAMAR"),))
    ts = jalankan({1: [it]})
    assert {t.jenis_seri for t in kode(ts, "V01", 1)} == {"KAMAR"}


def test_v02_rka_td_dan_rka_triwulanan():
    a = rev(1, parameter={})
    b = rev(2, seri={"RKA": {u: 0.3 for u in PER if u not in (AWAL, AWAL + 1)}})
    ts = jalankan({1: [a, b]})
    assert any("tahun dasar" in t.pesan for t in kode(ts, "V02", 1))
    v = [t for t in kode(ts, "V02", 2) if "triwulanan" in t.pesan]
    assert len(v) == 1 and v[0].periode == AWAL and "2 triwulan" in v[0].pesan
    # TOP/SOP tanpa konsumsi antara: tidak ada V02
    assert not kode(jalankan({2: [rev(3, parameter={}, seri={"RKA": {}})]}), "V02")


def test_v02_def_td2025_rka_tanpa_ntb_tahun_dasar_keputusan17():
    it = Item(1, "DEF", seri={"OUT_ADHB": s(lambda i: 500), "IH": s(lambda i: 100), "RKA": s(lambda i: 0.4)})
    ts = jalankan({1: [it]})
    assert any("keputusan 17" in t.pesan for t in kode(ts, "V02", 1))
    ok = Item(2, "DEF", seri={"OUT_ADHB": s(lambda i: 500), "IH": s(lambda i: 100), "NTB_ADHB": s(lambda i: 300)})
    assert not kode(jalankan({1: [ok]}), "V02")


def test_v03_jangkar_menurut_tahun_dasar():
    # TD2025: data T0 ada -> jangkar boleh kosong; tanpa data T0 -> wajib
    tanpa_t0 = rev(2, seri={"KUANTUM": {u: 10.0 for u in PER if u < T0[0]}})
    ts = jalankan({1: [rev(1), tanpa_t0]})
    assert not kode(ts, "V03", 1)
    assert [t.jenis_seri for t in kode(ts, "V03", 2)] == ["HARGA"]
    # TD2010 (jangkar_dari_data = tidak): semua jangkar wajib
    eks = Item(3, "EKS", "IP", seri={"INDEKS": s(lambda i: 100 + i), "IH": s(lambda i: 100),
                                     "BASE_ADHK": {u: 50.0 for u in T0}, "RKA": s(lambda i: 0.2)},
               parameter={"RKA_TD": 0.2})
    deff = Item(4, "DEF", seri={"OUT_ADHB": s(lambda i: 10), "IH": s(lambda i: 100)}, parameter={"IH_TD": 100})
    margin = Item(5, "DEF", seri={"R_MARGIN": s(lambda i: 0.1)}, parameter={"RKA_TD": 0.1},
                  tautan=(Tautan("OUT_ADHB", "RUMUS", "MARGIN_X_OUTPUT", lapus_sumber=(4,)),))
    ts = jalankan({1: [rev(1), eks, deff, margin]}, jdd=False)
    assert {(t.item_id, t.jenis_seri) for t in kode(ts, "V03")} == {
        (1, "HARGA"), (3, "IH"), (4, "RKA"), (5, "R_MARGIN")}  # margin barang: IH tidak dipakai


def test_v04_v12_eks_rantai_dan_baseline():
    ind = s(lambda i: 100 + i)
    del ind[urut(2024, 2)]
    putus = Item(1, "EKS", "IP", seri={"INDEKS": ind, "IH": s(lambda i: 100), "BASE_ADHK": {u: 50.0 for u in T0},
                                       "RKA": s(lambda i: 0.2)}, parameter={"RKA_TD": 0.2})
    tanpa = Item(2, "EKS", "IB", seri={"INDEKS": s(lambda i: 100), "IH": s(lambda i: 100), "RKA": s(lambda i: 0.2),
                                       "BASE_ADHK": {u: 5.0 for u in T0}}, parameter={"RKA_TD": 0.2})
    ts = jalankan({1: [putus, tanpa]})
    v4 = kode(ts, "V04", 1)
    assert len(v4) == 1 and "mundur" in v4[0].pesan and v4[0].periode == urut(2024, 2)
    assert kode(ts, "V12", 2) and not kode(ts, "V12", 1)
    assert not kode(ts, "V04", 2)  # salah satu baseline ada


def test_v05_komoditas_ganda_dan_konfirmasi():
    a = rev(1)
    b = Item(2, "DEF", seri={"OUT_ADHB": s(lambda i: 10), "NTB_ADHB": s(lambda i: 5), "IH": s(lambda i: 100)})
    info = {1: InfoItem(1, 1, "REV", "Ubi  Kayu", 1), 2: InfoItem(2, 1, "DEF", "ubi kayu", 1)}
    ts = jalankan({1: [a, b]}, info=info)
    v5 = kode(ts, "V05")
    assert {t.item_id for t in v5} == {1, 2} and len({t.kunci for t in v5}) == 1
    ts = jalankan({1: [a, b]}, info=info, konfirmasi={("V05", 1, "1-2"): (7, "Komoditas berbeda kualitas")})
    assert all(t.dikonfirmasi_oleh == 7 for t in kode(ts, "V05"))


def test_v06_implisit_tahun_dasar():
    it = Item(1, "DEF", seri={"OUT_ADHB": s(lambda i: 100), "NTB_ADHB": s(lambda i: 60), "IH": s(lambda i: 90)},
              parameter={"IH_TD": 100.0})
    assert kode(jalankan({1: [it]}), "V06")
    assert not kode(jalankan({1: [rev(1)]}), "V06")


def test_v07_v11_penyesuaian():
    adj = [AdjInfo(1, "METODE", "REV", "ADJ1", "CP", urut(2025, 2), 15.0, "draf"),
           AdjInfo(1, "METODE", "REV", "ADJ2", "CP", urut(2025, 2), 5.0, "disetujui"),
           AdjInfo(1, "METODE", "REV", "ADJ2", "K", urut(2025, 2), 4.0, "disetujui"),
           AdjInfo(1, "REKON", None, "CT_OUTPUT", "CP", urut(2025, 3), 99999.0, "draf")]
    ts = jalankan({1: [rev(1)]}, adj_info=adj)
    assert [t.pesan.split(":")[0] for t in kode(ts, "V07")] == ["ADJ1 REV Q2-2025"]
    assert len(kode(ts, "V11")) == 1 and kode(ts, "V11")[0].tingkat == "info"


def test_v08_ambang_tetap_override_dan_p95():
    lonjak = rev(1, seri={"KUANTUM": s(lambda i: 100 * (1.5 if PER[i] == urut(2025, 3) else 1))})
    ts = jalankan({1: [lonjak]})
    v8 = kode(ts, "V08")
    assert {(t.jenis_seri, t.periode) for t in v8} >= {("qtq_volume", urut(2025, 3)), ("yoy_volume", urut(2025, 3))}
    assert all("30.0%" in t.pesan for t in v8) and all(not any(c.isdigit() for c in t.pesan.split("ambang")[0])
                                                       or "q-to-q" in t.pesan or "y-on-y" in t.pesan for t in v8)
    longgar = {"V08": AturanValidasi("peringatan", PARAM["V08"] | {"per_lapus": {"TD2025:A.1": {
        "ambang_persen": {"qtq_volume": 80, "yoy_volume": 80, "qtq_implisit": 80, "yoy_implisit": 80}}}})}
    assert not kode(jalankan({1: [lonjak]}, aturan=longgar), "V08")


def test_ambang_v08_p95_tidak_di_bawah_tetap():
    assert _p95([1, 2, 3, 4, 5, 6, 7, 8, 9, 10]) == pytest.approx(9.55)
    par = PARAM["V08"] | {"kalibrasi": "p95"}
    tinggi = {"qtq_volume": [10.0 * i for i in range(1, 11)]}
    a = ambang_v08(par, "TD2025", "A.1", tinggi)
    assert a["qtq_volume"] == pytest.approx(95.5) and a["yoy_volume"] == 30  # titik kurang -> ambang tetap
    rendah = {"qtq_volume": [1.0] * 10}
    assert ambang_v08(par, "TD2025", "A.1", rendah)["qtq_volume"] == 30  # tidak di bawah ambang tetap


def test_v09_v10_ntb_dan_adhk_nol():
    lebih = Item(1, "DEF", seri={"OUT_ADHB": s(lambda i: 100), "NTB_ADHB": s(lambda i: 120), "IH": s(lambda i: 100)},
                 parameter={"IH_TD": 100})
    nol = rev(2, parameter={"RKA_TD": 0.3, "H_TD": 0.0})
    ts = jalankan({1: [lebih, nol]})
    assert kode(ts, "V09") and "Q1-2024" in kode(ts, "V09")[0].pesan
    v10 = kode(ts, "V10", 2)
    assert v10 and v10[0].tingkat == "blokir_ajukan" and f"{len(PER)} triwulan" in v10[0].pesan


def test_v13_v14_lapus_tanpa_item():
    ts = jalankan({1: [rev(1)]}, status={})
    assert [t.lapus_id for t in kode(ts, "V13")] == [4]
    assert {t.lapus_id for t in kode(ts, "V14")} == {2, 3}
    ts = jalankan({1: [rev(1)]}, status={4: "nihil", 2: "nihil", 3: "nihil"})
    assert not kode(ts, "V13") and not kode(ts, "V14")


def test_v16_satuan_dan_aturan_nonaktif():
    info = {1: InfoItem(1, 1, "REV", "Padi", 1, satuan_kode="ton", satuan_seri={"KUANTUM": "kg"})}
    assert kode(jalankan({1: [rev(1)]}, info=info), "V16")
    mati = {"V16": AturanValidasi("peringatan", {}, aktif=False)}
    assert not kode(jalankan({1: [rev(1)]}, info=info, aturan=mati), "V16")


def test_item_nonaktif_tidak_memblokir():
    info = {1: InfoItem(1, 1, "REV", "Padi", 1, status="nonaktif")}
    ts = jalankan({1: [rev(1, parameter={})]}, info=info)
    assert not kode(ts, "V02") and not kode(ts, "V01")
