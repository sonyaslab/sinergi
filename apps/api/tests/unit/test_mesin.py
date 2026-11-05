"""Uji unit mesin hitung produksi (sinergi_api.engine): satu kasus kecil per aturan docs/02, angka dihitung manual.

Port engine_ref/test_engine.py + aturan jangkar (TD2010/TD2025), TOP/SOP, rumus turunan, tautan, masa berlaku,
penyesuaian tiga tahap, agregasi, graf dependensi, tabel turunan, dan sidik masukan.
"""
from __future__ import annotations

import pytest

from sinergi_api.engine import (
    DataLapus,
    GalatMesin,
    Item,
    KonfigTD,
    Lapus,
    MasukanWilayah,
    Penyesuaian,
    SiklusTautan,
    Sumbu,
    Tautan,
    hitung_wilayah,
    urut,
)
from sinergi_api.engine import turunan_tabel as tt
from sinergi_api.engine.penyesuaian import adj_target_implisit, adj_target_laju

T1, T2, T3, T4 = (urut(2025, q) for q in (1, 2, 3, 4))
N1, N2 = urut(2026, 1), urut(2026, 2)
B1, B2, B3, B4 = (urut(2024, q) for q in (1, 2, 3, 4))
Q4_24 = urut(2024, 4)

POHON = [
    Lapus(1, "A", "kategori", None, 1), Lapus(2, "A.1", "daun", 1, 2), Lapus(3, "A.2", "daun", 1, 3),
    Lapus(4, "B", "kategori", None, 4, is_migas=True), Lapus(5, "B.1", "daun", 4, 5, is_migas=True),
    Lapus(6, "G", "daun", None, 6), Lapus(7, "AB", "kelompok", None, 7, anggota=(1, 4)),
    Lapus(8, "NTB", "ntb", None, 8), Lapus(9, "TOP", "top", None, 9), Lapus(10, "SOP", "sop", None, 10),
    Lapus(11, "TOP.SOP", "topsop", None, 11), Lapus(12, "PDRB", "pdrb", None, 12),
    Lapus(13, "PDRB.NM", "pdrb_nonmigas", None, 13),
]
ID = {r.kode: r.id for r in POHON}


def hitung(data: dict[str, DataLapus | list[Item]], baseline: int = 2025, jdd: bool = True, pohon=None,
           awal: int = urut(2024, 1), akhir: int = urut(2026, 4), referensi=None):
    d = {ID[k]: (v if isinstance(v, DataLapus) else DataLapus(v)) for k, v in data.items()}
    m = MasukanWilayah(KonfigTD(baseline, jdd), Sumbu(awal, akhir), pohon or POHON, d, referensi or {})
    h = hitung_wilayah(m)

    def nilai(kode: str, u: int, tahap: str = "BENC") -> tuple[float, float, float, float]:
        e = h.lapus[ID[kode]].tahap[tahap]
        t = h.sumbu.i(u)
        return e.out_cp[t], e.gva_cp[t], e.out_k[t], e.gva_k[t]

    return h, nilai


def dekat(a, b, tol=1e-9):
    return all(abs(x - y) <= tol * max(1.0, abs(y)) for x, y in zip(a, b, strict=True))


def rev(iid=1, **kw) -> Item:
    seri = {k: kw.pop(k) for k in ("KUANTUM", "HARGA", "RKA", "IH", "TPK", "KAMAR") if k in kw}
    return Item(iid, "REV", seri=seri, **kw)


def eks(iid=1, jenis="IP", **kw) -> Item:
    seri = {k: kw.pop(k) for k in ("INDEKS", "IH", "RKA", "BASE_ADHB", "BASE_ADHK") if k in kw}
    return Item(iid, "EKS", jenis_indeks=jenis, seri=seri, **kw)


def dfl(iid=1, **kw) -> Item:
    seri = {k: kw.pop(k) for k in ("OUT_ADHB", "NTB_ADHB", "IH", "RKA", "NILAI_KAPITA", "PENDUDUK", "R_MARGIN",
                                   "V_IMPOR", "KURS") if k in kw}
    return Item(iid, "DEF", seri=seri, **kw)


# ------------------------------------------------------------------ REV (port engine_ref)
def test_rev_td2025_harga_tertimbang():
    _, n = hitung({"A.1": [rev(KUANTUM={T1: 10, T2: 30, T3: 0, T4: 0, N1: 20}, HARGA={T1: 2, T2: 4, N1: 5},
                               RKA={N1: 0.25}, parameter={"RKA_TD": 0.2})]})
    hbar = (10 * 2 + 30 * 4) / 40
    assert dekat(n("A.1", N1), (100, 75, 20 * hbar, 0.8 * 20 * hbar))


def test_rev_td2010_jangkar_harga():
    it = rev(KUANTUM={N1: 20}, HARGA={N1: 5}, RKA={N1: 0.1}, parameter={"RKA_TD": 0.1, "H_TD": 1.5})
    _, n = hitung({"A.1": [it]},
                  baseline=2024, jdd=False)
    assert dekat(n("A.1", N1), (100, 90, 30, 27))


def test_rev_td2010_tanpa_h_td_adhk_nol():
    _, n = hitung({"A.1": [rev(KUANTUM={B1: 10, N1: 20}, HARGA={B1: 2, N1: 5}, parameter={"RKA_TD": 0.2})]},
                  baseline=2024, jdd=False)
    assert n("A.1", N1)[2] == 0 and n("A.1", N1)[0] == 100


def test_rev_rka_td_kosong_ntb_adhk_sama_output():
    _, n = hitung({"A.1": [rev(KUANTUM={T1: 10, N1: 10}, HARGA={T1: 3, N1: 4}, RKA={N1: 0.5})]})
    o_cp, g_cp, o_k, g_k = n("A.1", N1)
    assert (o_cp, g_cp) == (40, 20) and o_k == g_k == 30  # temuan K2: V02 memblokir


def test_rev_sel_kosong_dihitung_nol():
    _, n = hitung({"A.1": [rev(KUANTUM={T1: 10}, HARGA={T1: 3}, parameter={"RKA_TD": 0})]})
    assert n("A.1", N1) == (0, 0, 0, 0)


# ------------------------------------------------------------------ EKS
def test_eks_ip_rantai_maju_mundur():
    ind = {Q4_24: 90, T1: 100, T2: 100, T3: 100, T4: 100, N1: 110}
    _, n = hitung({"A.1": [eks(INDEKS=ind, IH={u: 100 for u in ind}, BASE_ADHK={u: 50 for u in (T1, T2, T3, T4)},
                               parameter={"RKA_TD": 0.0})]})
    assert dekat((n("A.1", N1)[2], n("A.1", Q4_24)[2]), (55, 45))


def test_eks_ib_baseline_adhb_dan_deflasi():
    t0 = (T1, T2, T3, T4)
    _, n = hitung({"A.1": [eks(jenis="IB", INDEKS={**{u: 100 for u in t0}, N1: 120},
                               IH={T1: 100, T2: 100, T3: 100, T4: 100, N1: 125}, BASE_ADHB={u: 80 for u in t0},
                               RKA={N1: 0.25}, parameter={"RKA_TD": 0.2})]})
    assert dekat(n("A.1", N1), (96, 72, 76.8, 61.44))


def test_eks_rantai_putus_dan_jenis_kosong():
    t0 = (T1, T2, T3, T4)
    ind = {**{u: 100 for u in t0}, N2: 110}  # N1 kosong -> N1 dan sesudahnya 0
    _, n = hitung({"A.1": [eks(INDEKS=ind, IH={u: 100 for u in (*t0, N1, N2)}, BASE_ADHK={u: 50 for u in t0})],
                   "A.2": [eks(2, jenis=None, INDEKS=ind, BASE_ADHK={u: 50 for u in t0})]})
    assert n("A.1", T4)[2] == 50 and n("A.1", N1)[2] == 0 and n("A.1", N2)[2] == 0
    assert n("A.2", T4) == (0, 0, 0, 0)


def test_eks_td2010_ih_td_parameter_baseline_2024():
    t0 = (B1, B2, B3, B4)
    it = eks(jenis="IB", INDEKS={**{u: 100 for u in t0}, N1: 120}, IH={u: 90 for u in t0},
             BASE_ADHB={u: 90 for u in t0}, parameter={"RKA_TD": 0.0, "IH_TD": 100})
    _, n = hitung({"A.1": [it]}, baseline=2024, jdd=False)
    assert dekat(n("A.1", B4)[::2], (90, 100))
    it.parameter = {"RKA_TD": 0.0}
    _, n = hitung({"A.1": [it]}, baseline=2024, jdd=False)
    assert n("A.1", B4)[2] == 0  # TD2010: IH dasar kosong = 0, bukan rata-rata 2024


def test_eks_ih_dasar_rata_rata_abaikan_kosong():
    t0 = (T1, T2, T3, T4)
    _, n = hitung({"A.1": [eks(INDEKS={u: 100 for u in t0}, IH={T1: 90, T2: 110, N1: 120},
                               BASE_ADHK={u: 50 for u in t0})]})
    assert dekat((n("A.1", T1)[0],), (50 * 90 / 100,))  # ĪH = (90 + 110) / 2


# ------------------------------------------------------------------ DEF
def test_def_td2025_dan_td2010():
    t0 = (T1, T2, T3, T4)
    a = dfl(OUT_ADHB={**{u: 100 for u in t0}, N1: 120}, NTB_ADHB={**{u: 60 for u in t0}, N1: 70},
            IH={**{u: 100 for u in t0}, N1: 120})
    _, n = hitung({"A.1": [a]})
    assert dekat(n("A.1", N1), (120, 70, 100, 60))
    b = dfl(2, OUT_ADHB={N1: 120}, IH={N1: 120}, parameter={"RKA_TD": 0.0, "IH_TD": 100})
    _, n = hitung({"A.1": [b]})
    assert dekat(n("A.1", N1), (120, 120, 100, 100))


def test_def_ntb_dari_rka_atau_nol():
    _, n = hitung({"A.1": [dfl(OUT_ADHB={N1: 100}, IH={N1: 100}, RKA={N1: 0.3}, parameter={"IH_TD": 100})],
                   "A.2": [dfl(2, OUT_ADHB={N1: 100}, IH={N1: 100}, parameter={"IH_TD": 100})]})
    assert n("A.1", N1)[1] == 70
    assert n("A.2", N1)[1] == 0  # NTB_ADHB dan RKA kosong: NTB ADHB = 0 (perilaku LK)


def test_def_rka_td_dari_data_t0_atau_parameter():
    t0 = (T1, T2, T3, T4)
    a = dfl(OUT_ADHB={**{u: 100 for u in t0}, N1: 100}, NTB_ADHB={u: 75 for u in t0}, IH={u: 100 for u in (*t0, N1)},
            parameter={"RKA_TD": 0.5})
    _, n = hitung({"A.1": [a]})
    assert dekat((n("A.1", N1)[3],), (75,))  # TD2025: rasio data T₀ menang atas parameter
    _, n = hitung({"A.1": [a]}, baseline=2024, jdd=False)
    assert n("A.1", N1)[3] == 0  # TD2010: IH_TD kosong -> ADHK 0
    a.parameter["IH_TD"] = 100
    _, n = hitung({"A.1": [a]}, baseline=2024, jdd=False)
    assert dekat((n("A.1", N1)[3],), (50,))  # TD2010: RKA_TD parameter (keputusan 3)


def test_def_tanpa_data_t0_pakai_parameter():
    _, n = hitung({"A.1": [dfl(OUT_ADHB={N1: 200}, NTB_ADHB={N1: 150}, IH={N1: 100, T1: 100},
                               parameter={"RKA_TD": 0.4})]})
    assert dekat(n("A.1", N1), (200, 150, 200, 120))


# ------------------------------------------------------------------ TOP / SOP (keputusan 1)
def test_top_sop_tanpa_konsumsi_antara_dan_pdrb():
    _, n = hitung({
        "A.1": [dfl(OUT_ADHB={N1: 100}, NTB_ADHB={N1: 60}, IH={N1: 100}, parameter={"IH_TD": 100, "RKA_TD": 0.4})],
        "TOP": [dfl(2, OUT_ADHB={N1: 30}, NTB_ADHB={N1: 5}, IH={N1: 120}, RKA={N1: 0.9},
                    parameter={"IH_TD": 100, "RKA_TD": 0.5})],
        "SOP": [rev(3, KUANTUM={N1: 10}, HARGA={N1: 1.2}, RKA={N1: 0.5}, parameter={"H_TD": 1.0, "RKA_TD": 0.5})]})
    assert dekat(n("TOP", N1), (30, 30, 25, 25)) and dekat(n("SOP", N1), (12, 12, 10, 10))
    assert dekat(n("TOP.SOP", N1), (18, 18, 15, 15))
    assert dekat(n("PDRB", N1), (118, 78, 115, 75)) and dekat(n("NTB", N1), (100, 60, 100, 60))


# ------------------------------------------------------------------ rumus turunan dan tautan
def test_tpk_x_kamar_sama_dengan_lk():
    it = rev(TPK={N1: 35.99}, KAMAR={N1: 375}, HARGA={N1: 1}, parameter={"H_TD": 1, "RKA_TD": 0},
             tautan=(Tautan("KUANTUM", "RUMUS", "TPK_X_KAMAR"),))
    _, n = hitung({"A.1": [it]})
    assert dekat((n("A.1", N1)[0],), (13496.25,))


def test_jangkar_x_ih_100():
    it = rev(KUANTUM={N1: 10}, IH={N1: 110}, parameter={"H_TD": 1500, "RKA_TD": 0},
             tautan=(Tautan("HARGA", "RUMUS", "JANGKAR_X_IH_100"),))
    _, n = hitung({"A.1": [it]}, baseline=2024, jdd=False)
    assert dekat(n("A.1", N1)[::2], (16500, 15000))


def test_kapita_x_penduduk_x_3_faktor():
    it = dfl(NILAI_KAPITA={N1: 200000}, PENDUDUK={N1: 700000}, IH={N1: 100}, RKA={N1: 0.1},
             parameter={"IH_TD": 100, "RKA_TD": 0.1}, tautan=(Tautan("OUT_ADHB", "RUMUS", "KAPITA_X_PENDUDUK_X_3",
                                                                    faktor=0.8865),))
    _, n = hitung({"A.1": [it]})
    assert dekat((n("A.1", N1)[0],), (200000 * 700000 * 3 / 1e6 * 0.8865,))


def test_seri_referensi_faktor_dan_kosong():
    it = dfl(OUT_ADHB={N1: 120, N2: 120}, NTB_ADHB={N1: 60, N2: 60}, parameter={"IH_TD": 100, "RKA_TD": 0.5},
             tautan=(Tautan("IH", "SERI_REFERENSI", seri_ref="REF_UPAH", faktor=2.0),))
    _, n = hitung({"A.1": [it]}, referensi={"REF_UPAH": {N1: 60.0}})
    assert dekat((n("A.1", N1)[2],), (100,)) and n("A.1", N2)[2] == 0
    _, n = hitung({"A.1": [it]})  # seri referensi belum diisi = kosong
    assert n("A.1", N1)[2] == 0


def test_hasil_lapus_dari_benc_dan_urutan_dependensi():
    # A.1 (urutan lebih awal) bergantung pada G (urutan lebih akhir): graf harus menghitung G dulu
    g = dfl(1, OUT_ADHB={N1: 200}, NTB_ADHB={N1: 100}, IH={N1: 125}, parameter={"IH_TD": 100, "RKA_TD": 0.5})
    a = eks(2, INDEKS={}, IH={u: 100 for u in (T1, T2, T3, T4, N1)}, BASE_ADHK={u: 1 for u in (T1, T2, T3, T4)},
            tautan=(Tautan("INDEKS", "HASIL_LAPUS", lapus_sumber=(6,), besaran="OUT_K", faktor=0.5),))
    b = dfl(3, OUT_ADHB={N1: 10}, NTB_ADHB={N1: 10}, IH={}, parameter={"IH_TD": 100},
            tautan=(Tautan("IH", "HASIL_LAPUS", lapus_sumber=(6,), besaran="IMPLISIT_OUT"),))
    sim = Penyesuaian("SIMULASI", "SIM_NTB", "K", N1, 50.0)  # simulasi G tidak memengaruhi tautan (BENC)
    h, n = hitung({"G": DataLapus([g], [sim]), "A.1": [a], "A.2": [b]})
    assert h.urutan_hitung.index(ID["G"]) < h.urutan_hitung.index(ID["A.1"])
    assert dekat((n("A.2", N1)[2],), (10 / 125 * 100,))
    assert n("A.1", N1)[2] == 0  # indeks = 0,5 x 160 pada N1, tetapi T4 (0,5 x 0) -> rantai 0 (V04)


def test_margin_x_output_arus_barang_dari_benc():
    t0 = (B1, B2, B3, B4)
    barang = dfl(1, OUT_ADHB={**{u: 100 for u in t0}, N1: 150}, NTB_ADHB={N1: 90}, IH={**{u: 100 for u in t0}, N1: 125},
                 parameter={"IH_TD": 100, "RKA_TD": 0.4})
    margin = dfl(2, R_MARGIN={N1: 0.2}, RKA={N1: 0.25}, parameter={"R_MARGIN_TD": 0.1, "RKA_TD": 0.5},
                 tautan=(Tautan("OUT_ADHB", "RUMUS", "MARGIN_X_OUTPUT", lapus_sumber=(1,), faktor=1.0),))
    sim = Penyesuaian("SIMULASI", "SIM_NTB", "CP", N1, 30.0)
    _, n = hitung({"A.1": DataLapus([barang], [sim]), "G": [margin]}, baseline=2024, jdd=False)
    assert dekat(n("G", N1), (30, 22.5, 12, 6))  # ADHB 0,2 x 150; ADHK 0,1 x 120 (ADHK BENC A)
    assert n("G", T4) == (0, 0, 0, 0)  # rasio margin kosong -> tidak ada margin


def test_margin_x_output_rasio_dasar_dari_data_td2025():
    t0 = (T1, T2, T3, T4)
    barang = dfl(1, OUT_ADHB={u: 100 for u in (*t0, N1)}, IH={u: 100 for u in (*t0, N1)}, parameter={"RKA_TD": 0})
    margin = dfl(2, R_MARGIN={T1: 0.1, T2: 0.1, T3: 0.3, T4: 0.3, N1: 0.5},
                 tautan=(Tautan("OUT_ADHB", "RUMUS", "MARGIN_X_OUTPUT", lapus_sumber=(2,)),))
    _, n = hitung({"A.1": [barang], "G": [margin]})
    assert dekat(n("G", N1)[::2], (50, 20))  # R_TD = (10+10+30+30)/400


def test_margin_x_impor_kurs_dan_tanpa_kurs():
    m = dfl(R_MARGIN={N1: 0.2}, V_IMPOR={N1: 10.0}, IH={N1: 150.0},
            parameter={"R_MARGIN_TD": 0.1, "IH_TD": 100, "RKA_TD": 0},
            tautan=(Tautan("OUT_ADHB", "RUMUS", "MARGIN_X_IMPOR", faktor=0.001),
                    Tautan("KURS", "SERI_REFERENSI", seri_ref="REF_KURS")))
    _, n = hitung({"G": [m]}, baseline=2024, jdd=False, referensi={"REF_KURS": {N1: 15000.0}})
    assert dekat(n("G", N1)[::2], (30, 10))
    m.tautan = m.tautan[:1]
    _, n = hitung({"G": [m]}, baseline=2024, jdd=False)
    assert dekat(n("G", N1)[::2], (0.002, 0.1 * 10 / 150 * 100 * 0.001))


def test_rumus_salah_sasaran_atau_tidak_baku_ditolak():
    with pytest.raises(GalatMesin, match="hanya untuk seri KUANTUM"):
        hitung({"A.1": [rev(tautan=(Tautan("HARGA", "RUMUS", "TPK_X_KAMAR"),))]})
    with pytest.raises(GalatMesin, match="daftar baku"):
        hitung({"A.1": [rev(tautan=(Tautan("HARGA", "RUMUS", "EKSPRESI_BEBAS"),))]})
    with pytest.raises(GalatMesin, match="baris total"):
        hitung({"A.1": [dfl(tautan=(Tautan("OUT_ADHB", "RUMUS", "MARGIN_X_OUTPUT", lapus_sumber=(12,)),))]})


# ------------------------------------------------------------------ masa berlaku item (keputusan F2)
def test_masa_berlaku_data_di_luar_dianggap_tidak_ada():
    it = rev(KUANTUM={T1: 10, N1: 10, N2: 10}, HARGA={T1: 2, N1: 3, N2: 3}, parameter={"RKA_TD": 0},
             mulai=N1, selesai=N1)
    _, n = hitung({"A.1": [it]})
    assert n("A.1", N1) == (30, 30, 0, 0)  # T₀ di luar masa -> harga dasar 0 (wajib jangkar, V03)
    assert n("A.1", N2) == (0, 0, 0, 0)
    it.parameter["H_TD"] = 2.5
    _, n = hitung({"A.1": [it]})
    assert n("A.1", N1) == (30, 30, 25, 25)


# ------------------------------------------------------------------ penyesuaian tiga tahap
def _dasar():
    return dfl(OUT_ADHB={N1: 100}, NTB_ADHB={N1: 60}, IH={N1: 125}, parameter={"IH_TD": 100, "RKA_TD": 0.5})


def test_penyesuaian_metode_proporsional():
    adj = [Penyesuaian("METODE", "ADJ1", "CP", N1, 10, "DEF"), Penyesuaian("METODE", "ADJ2", "CP", N1, 5, "DEF"),
           Penyesuaian("METODE", "SC", "CP", N1, 5, "DEF"), Penyesuaian("METODE", "ADJ1", "K", N1, -20, "DEF"),
           Penyesuaian("METODE", "ADJ1", "CP", N1, 99, "REV")]  # REV tanpa item: r = 0
    h, n = hitung({"A.1": DataLapus([_dasar()], adj)})
    pr, pre = h.lapus[ID["A.1"]].metode["DEF"]
    t = h.sumbu.i(N1)
    assert (pre.out_cp[t], pre.gva_cp[t]) == (120, 72) and dekat((pre.out_k[t], pre.gva_k[t]), (60, 30))
    assert dekat(n("A.1", N1, "PRE"), (219, 72, 60, 30))


def test_rekon_adj3_proporsional_adj4_terpisah():
    adj = [Penyesuaian("REKON", "ADJ3", "CP", N1, 20), Penyesuaian("REKON", "ADJ4_OUTPUT", "CP", N1, 5),
           Penyesuaian("REKON", "ADJ4_NTB", "CP", N1, -2), Penyesuaian("REKON", "ADJ3", "K", N1, -8)]
    _, n = hitung({"A.1": DataLapus([_dasar()], adj)})
    assert dekat(n("A.1", N1, "PRE"), (100, 60, 80, 40))
    assert dekat(n("A.1", N1, "POST"), (120, 72, 72, 36))
    assert dekat(n("A.1", N1, "BENC"), (125, 70, 72, 36))


def test_simulasi_output_ikut_ntb_dan_tanpa_sim_sama_benc():
    adj = [Penyesuaian("SIMULASI", "SIM_NTB", "CP", N1, 15), Penyesuaian("SIMULASI", "SIM_NTB", "K", N1, -10)]
    _, n = hitung({"A.1": DataLapus([_dasar()], adj),
                   "A.2": [dfl(2, OUT_ADHB={N1: 50}, IH={N1: 100}, parameter={"IH_TD": 100})]})
    assert dekat(n("A.1", N1, "FINAL"), (125, 75, 60, 30))
    assert n("A.2", N1, "FINAL") == n("A.2", N1, "BENC") and n("A.2", N1)[1] == 0
    assert dekat(n("A", N1, "FINAL"), (175, 75, 110, 80))  # A.2 tanpa RKA_TD: NTB ADHK = output ADHK (V02)


def test_bantuan_input_simulasi():
    assert adj_target_laju(100, 5, 103) == pytest.approx(2)
    assert adj_target_implisit(110, 200, 215) == pytest.approx(5)


def test_jenis_pembanding_tidak_mengubah_angka():
    adj = [Penyesuaian("REKON", "CT_OUTPUT", "CP", N1, 999)]
    _, n = hitung({"A.1": DataLapus([_dasar()], adj)})
    assert n("A.1", N1) == (100, 60, 80, 40)


# ------------------------------------------------------------------ agregasi pohon dan total
def test_agregasi_kategori_kelompok_ntb_migas():
    d = {"A.1": [dfl(1, OUT_ADHB={N1: 100}, NTB_ADHB={N1: 60}, IH={N1: 100}, parameter={"IH_TD": 100})],
         "A.2": [dfl(2, OUT_ADHB={N1: 50}, NTB_ADHB={N1: 20}, IH={N1: 100}, parameter={"IH_TD": 100})],
         "B.1": [dfl(3, OUT_ADHB={N1: 40}, NTB_ADHB={N1: 30}, IH={N1: 100}, parameter={"IH_TD": 100})],
         "G": [dfl(4, OUT_ADHB={N1: 10}, NTB_ADHB={N1: 5}, IH={N1: 100}, parameter={"IH_TD": 100})]}
    _, n = hitung(d)
    assert n("A", N1)[1] == 80 and n("B", N1)[1] == 30 and n("AB", N1)[1] == 110
    assert n("NTB", N1)[1] == 115 and n("PDRB", N1)[1] == 115
    assert n("PDRB.NM", N1)[1] == 85  # B dan B.1 sama-sama migas: dikurangkan sekali


def test_td2010_tanpa_baris_ntb_top_pdrb_jumlah_kategori():
    pohon = [Lapus(1, "A", "kategori", None, 1), Lapus(2, "A.1", "daun", 1, 2), Lapus(6, "G", "daun", None, 3),
             Lapus(12, "PDRB", "pdrb", None, 4)]
    d = {"A.1": [dfl(1, OUT_ADHB={N1: 100}, NTB_ADHB={N1: 60}, IH={N1: 100}, parameter={"IH_TD": 100})],
         "G": [dfl(2, OUT_ADHB={N1: 10}, NTB_ADHB={N1: 5}, IH={N1: 100}, parameter={"IH_TD": 100})]}
    _, n = hitung(d, pohon=pohon, baseline=2024, jdd=False)
    assert n("PDRB", N1) == (110, 65, 110, 110)  # NTB ADHK = (1 − RKA_TD kosong) x output ADHK


def test_baris_tanpa_data_tidak_punya_hasil():
    h, _ = hitung({"A.1": [dfl(OUT_ADHB={N1: 1}, IH={N1: 100}, parameter={"IH_TD": 100})],
                   "G": [Item(9, "PDK", seri={"NILAI": {N1: 5.0}})]})
    assert ID["A.2"] not in h.lapus and ID["G"] not in h.lapus and ID["B"] not in h.lapus
    assert ID["A"] in h.lapus and ID["PDRB.NM"] in h.lapus and ID["TOP.SOP"] in h.lapus


def test_lapus_di_luar_pohon_aktif_diabaikan():
    pohon = [r for r in POHON if r.kode != "A.2"]
    d = {ID["A.2"]: DataLapus([dfl(OUT_ADHB={N1: 99}, IH={N1: 100}, parameter={"IH_TD": 100})])}
    h = hitung_wilayah(MasukanWilayah(KonfigTD(2025, True), Sumbu(N1, N1), pohon, d))
    assert h.lapus == {}


# ------------------------------------------------------------------ graf dependensi
def test_siklus_dan_rujukan_diri_ditolak():
    a = dfl(1, tautan=(Tautan("IH", "HASIL_LAPUS", lapus_sumber=(6,), besaran="IMPLISIT_OUT"),))
    g = dfl(2, R_MARGIN={N1: 0.1}, tautan=(Tautan("OUT_ADHB", "RUMUS", "MARGIN_X_OUTPUT", lapus_sumber=(1,)),))
    with pytest.raises(SiklusTautan, match="A.1, G"):
        hitung({"A.1": [a], "G": [g]})
    with pytest.raises(SiklusTautan, match="dirinya sendiri"):
        hitung({"A.1": [dfl(1, tautan=(Tautan("IH", "HASIL_LAPUS", lapus_sumber=(1,), besaran="OUT_CP"),))]})


def test_sumber_tanpa_data_bernilai_nol():
    it = dfl(1, OUT_ADHB={N1: 10}, parameter={"IH_TD": 100},
             tautan=(Tautan("IH", "HASIL_LAPUS", lapus_sumber=(3,), besaran="IMPLISIT_OUT"),))
    _, n = hitung({"A.1": [it]})
    assert n("A.1", N1)[2] == 0


# ------------------------------------------------------------------ tabel turunan
def test_laju_qtq_yoy_ctc_sumbu_mulai_q3():
    sb = Sumbu(urut(2024, 3), urut(2026, 1))
    x = [100.0, 110.0, 105.0, 121.0, 115.0, 130.0, 116.0]  # 2024Q3 .. 2026Q1
    assert tt.laju_qtq(x)[1] == pytest.approx(10) and tt.laju_qtq(x)[0] is None
    assert tt.laju_yoy(x)[4] == pytest.approx(15) and tt.laju_yoy(x)[3] is None
    ctc = tt.laju_ctc(x, sb)
    assert ctc[2] is None and ctc[3] is None  # 2025Q1-Q2: tahun lalu tidak lengkap di sumbu
    assert ctc[6] == pytest.approx(116 / 105 * 100 - 100)


def test_sog_distribusi_implisit_dan_kosong():
    sb = Sumbu(urut(2025, 1), urut(2026, 2))
    x = [10.0, 12.0, 11.0, 13.0, 14.0, 15.0]
    pdrb = [100.0, 0.0, 110.0, 120.0, 130.0, 140.0]
    assert tt.sog(x, pdrb, 1)[1] == pytest.approx(2) and tt.sog(x, pdrb, 1)[2] is None
    assert tt.sog(x, pdrb, 4)[4] == pytest.approx(4)
    assert tt.sog_ctc(x, pdrb, sb)[5] == pytest.approx((29 - 22) / 100 * 100)
    assert tt.distribusi([5.0, 1.0], [50.0, 0.0]) == [pytest.approx(10), None]
    imp = tt.implisit([110.0, 0.0], [100.0, 0.0])
    assert imp[0] == pytest.approx(110) and imp[1] is None and tt.laju_qtq(imp)[1] is None
    ic = tt.laju_implisit_ctc([110.0] * 6, [100.0] * 5 + [50.0], sb)
    assert ic[4] == pytest.approx(0) and ic[5] == pytest.approx((220 / 150) / (220 / 200) * 100 - 100)


# ------------------------------------------------------------------ sidik masukan dan sumbu
def test_sidik_deterministik_dan_peka_masukan():
    d = {"A.1": [_dasar()], "G": [dfl(2, OUT_ADHB={N1: 5}, IH={N1: 100}, parameter={"IH_TD": 100})]}
    h1, _ = hitung(d)
    h2, _ = hitung(d)
    assert h1.lapus[ID["A.1"]].hash_input == h2.lapus[ID["A.1"]].hash_input
    d["A.1"][0].seri["OUT_ADHB"][N1] = 101.0
    h3, _ = hitung(d)
    assert h3.lapus[ID["A.1"]].hash_input != h1.lapus[ID["A.1"]].hash_input
    assert h3.lapus[ID["G"]].hash_input == h1.lapus[ID["G"]].hash_input
    assert h3.lapus[ID["PDRB"]].hash_input != h1.lapus[ID["PDRB"]].hash_input


def test_sumbu_diperluas_ke_tahun_baseline_dan_rentang_tidak_valid():
    h, n = hitung({"A.1": [rev(KUANTUM={T1: 10, N1: 10}, HARGA={T1: 2, N1: 3}, parameter={"RKA_TD": 0})]},
                  awal=N1, akhir=N1)
    assert h.sumbu.awal == T1 and n("A.1", N1)[2] == 20
    with pytest.raises(GalatMesin):
        Sumbu(N1, T1)
