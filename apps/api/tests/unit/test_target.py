"""Uji unit bantuan target penyesuaian (putaran/target.py, keputusan 18) dan urutan cari Biaya Antara.

Setiap nilai hasil balikan dimasukkan kembali ke mesin hitung: tahap hasilnya harus tepat sama dengan target
(relatif 1e-9). Angka fiktif.
"""
from __future__ import annotations

import math

import pytest

from sinergi_api.engine import (
    DataLapus,
    Item,
    KonfigTD,
    Lapus,
    MasukanWilayah,
    Penyesuaian,
    Sumbu,
    hitung_wilayah,
    urut,
)
from sinergi_api.putaran.biaya_antara import rencana_rka
from sinergi_api.putaran.target import GalatTarget, mode_untuk, nilai_penyesuaian

AWAL, AKHIR = urut(2024, 1), urut(2026, 1)
PER = list(range(AWAL, AKHIR + 1))
POHON = [Lapus(1, "A", "kategori", None, 1), Lapus(2, "A.1", "daun", 1, 2)]
U = urut(2025, 3)


def s(f) -> dict[int, float]:
    return {u: float(f(i)) for i, u in enumerate(PER)}


def item() -> list[Item]:
    rev = Item(1, "REV", seri={"KUANTUM": s(lambda i: 100 + 3 * i), "HARGA": s(lambda i: 2.0 + 0.05 * i),
                               "RKA": s(lambda i: 0.3)}, parameter={"RKA_TD": 0.25})
    dfn = Item(2, "DEF", seri={"OUT_ADHB": s(lambda i: 50 + i), "NTB_ADHB": s(lambda i: 0.6 * (50 + i)),
                               "IH": s(lambda i: 100 + i)})
    return [rev, dfn]


def hitung(adj: list[Penyesuaian]):
    m = MasukanWilayah(KonfigTD(2025, True), Sumbu(AWAL, AKHIR), POHON, {2: DataLapus(item(), adj)})
    return hitung_wilayah(m)


DASAR = [Penyesuaian("METODE", "ADJ2", "CP", U, 3.0, "REV"), Penyesuaian("REKON", "ADJ4_NTB", "K", U, -1.5),
         Penyesuaian("SIMULASI", "SIM_NTB", "K", U - 4, 2.0)]


def _tahap(h, jenis: str, metode: str | None):
    hl = h.lapus[2]
    if jenis in ("ADJ1", "ADJ2", "SC"):
        pr, pre = hl.metode[metode]
        return pre, pr
    if jenis == "ADJ3":
        return hl.tahap["POST"], hl.tahap["PRE"]
    if jenis in ("ADJ4_OUTPUT", "ADJ4_NTB"):
        return hl.tahap["BENC"], None
    return hl.tahap["FINAL"], None


def _cek(jenis: str, harga: str, mode: str, target: float, metode: str | None = None) -> None:
    tahap = "METODE" if jenis in ("ADJ1", "ADJ2", "SC") else "SIMULASI" if jenis == "SIM_NTB" else "REKON"
    # seperti API: hasil tahap dihitung TANPA penyesuaian berkunci sama (yang sedang diisi)
    lain = [a for a in DASAR if (a.tahap, a.jenis, a.harga, a.periode, a.metode) != (tahap, jenis, harga, U, metode)]
    h0 = hitung(lain)
    hasil, dasar = _tahap(h0, jenis, metode)
    t = h0.sumbu.i(U)
    r = nilai_penyesuaian(jenis, harga, mode, target, t, h0.sumbu.i(U - 4), hasil, dasar)
    h1 = hitung([*lain, Penyesuaian(tahap, jenis, harga, U, r.nilai, metode)])
    akhir, _ = _tahap(h1, jenis, metode)
    out, ntb = (akhir.out_cp[t], akhir.gva_cp[t]) if harga == "CP" else (akhir.out_k[t], akhir.gva_k[t])
    if mode == "target_output":
        assert math.isclose(out, target, rel_tol=1e-9)
    else:
        assert r.target_ntb is not None and math.isclose(ntb, r.target_ntb, rel_tol=1e-9)
    if mode == "target_ntb":
        assert math.isclose(ntb, target, rel_tol=1e-9)
    if mode == "target_laju":
        lalu = (akhir.gva_cp if harga == "CP" else akhir.gva_k)[t - 4]
        assert math.isclose(ntb / lalu * 100 - 100, target, rel_tol=1e-9)
    if mode == "target_implisit":
        assert math.isclose(ntb / akhir.gva_k[t] * 100, target, rel_tol=1e-9)


@pytest.mark.parametrize("jenis,metode", [("ADJ1", "REV"), ("ADJ2", "REV"), ("SC", "DEF"), ("ADJ3", None),
                                          ("ADJ4_NTB", None), ("SIM_NTB", None)])
@pytest.mark.parametrize("harga", ["CP", "K"])
def test_target_ntb_dan_laju_dibalik_tepat(jenis, metode, harga):
    _cek(jenis, harga, "target_ntb", 321.5, metode)
    _cek(jenis, harga, "target_laju", 7.25, metode)
    if harga == "CP":
        _cek(jenis, harga, "target_implisit", 104.5, metode)


@pytest.mark.parametrize("jenis,metode", [("ADJ1", "DEF"), ("SC", "REV"), ("ADJ3", None), ("ADJ4_OUTPUT", None)])
def test_target_output(jenis, metode):
    _cek(jenis, "CP", "target_output", 999.0, metode)
    _cek(jenis, "K", "target_output", 888.0, metode)


def test_sim_laju_sama_dengan_rumus_docs02():
    """SIM ADHK: adj = NTB(t−4) × (1 + g/100) − NTB kompilasi (docs/02 §6), NTB(t−4) = FINAL."""
    h = hitung(DASAR)
    t = h.sumbu.i(U)
    fin, benc = h.lapus[2].tahap["FINAL"], h.lapus[2].tahap["BENC"]
    r = nilai_penyesuaian("SIM_NTB", "K", "target_laju", 5.0, t, t - 4, fin, None)
    assert math.isclose(r.nilai, fin.gva_k[t - 4] * 1.05 - benc.gva_k[t], rel_tol=1e-12)
    r = nilai_penyesuaian("SIM_NTB", "CP", "target_implisit", 110.0, t, t - 4, fin, None)
    assert math.isclose(r.nilai, 110.0 * fin.gva_k[t] / 100 - benc.gva_cp[t], rel_tol=1e-12)


def test_mode_dan_galat():
    assert mode_untuk("ADJ4_OUTPUT", "CP") == ["nilai", "target_output"]
    assert "target_implisit" not in mode_untuk("SIM_NTB", "K")
    assert mode_untuk("CT_NTB", "CP") == ["nilai"]
    h = hitung([])
    t = h.sumbu.i(U)
    with pytest.raises(GalatTarget):  # implisit hanya ADHB
        nilai_penyesuaian("SIM_NTB", "K", "target_implisit", 100, t, t - 4, h.lapus[2].tahap["FINAL"])
    with pytest.raises(GalatTarget):  # t−4 di luar cakupan
        nilai_penyesuaian("ADJ4_NTB", "CP", "target_laju", 5, t, None, h.lapus[2].tahap["BENC"])
    pr, pre = h.lapus[2].metode["EKS"]  # metode tanpa item: rasio NTB/output 0
    with pytest.raises(GalatTarget, match="Rasio"):
        nilai_penyesuaian("ADJ1", "CP", "target_ntb", 10, t, t - 4, pre, pr)
    assert nilai_penyesuaian("ADJ1", "CP", "nilai", 12.5, t, None, pre, pr).nilai == 12.5


def test_biaya_antara_urutan_cari_item_lapus_induk():
    pohon = {1: {"id": 1, "kode": "A", "induk_id": None}, 2: {"id": 2, "kode": "A.1", "induk_id": 1},
             3: {"id": 3, "kode": "A.1.a", "induk_id": 2}, 4: {"id": 4, "kode": "A.1.b", "induk_id": 2},
             5: {"id": 5, "kode": "B.1", "induk_id": None}}
    item = [{"id": 10, "lapus_id": 3}, {"id": 11, "lapus_id": 3}, {"id": 12, "lapus_id": 4}, {"id": 13, "lapus_id": 5}]
    hasil = rencana_rka(item, pohon, per_item={10: 0.1}, per_lapus={3: 0.2, 1: 0.4})
    assert [(r, sb) for _, r, sb in hasil] == [(0.1, "item"), (0.2, "lapus A.1.a"), (0.4, "induk A"), (None, None)]
