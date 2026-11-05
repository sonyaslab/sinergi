"""Uji oracle tingkat wilayah: tautan, siklus, simulasi, agregasi, total, tabel turunan."""
import pytest

from engine_ref import kompilasi as kp
from engine_ref.lk_engine import t_of

U0 = 2019 * 4
N1 = 2026 * 4          # urut 2026Q1
T25 = [2025 * 4 + q for q in range(4)]


def _pohon():
    return [
        {"id": 1, "kode": "A", "jenis": "kategori", "induk": None, "urutan": 1},
        {"id": 2, "kode": "A.1", "jenis": "daun", "induk": 1, "urutan": 2},
        {"id": 3, "kode": "A.2", "jenis": "daun", "induk": 1, "urutan": 3, "is_migas": True},
        {"id": 4, "kode": "G", "jenis": "daun", "induk": None, "urutan": 4},
        {"id": 5, "kode": "AG", "jenis": "kelompok", "induk": None, "urutan": 5, "anggota": [1, 4]},
        {"id": 6, "kode": "NTB", "jenis": "ntb", "induk": None, "urutan": 6},
        {"id": 7, "kode": "TOP", "jenis": "top", "induk": None, "urutan": 7},
        {"id": 8, "kode": "SOP", "jenis": "sop", "induk": None, "urutan": 8},
        {"id": 9, "kode": "TOP.SOP", "jenis": "topsop", "induk": None, "urutan": 9},
        {"id": 10, "kode": "PDRB", "jenis": "pdrb", "induk": None, "urutan": 10},
        {"id": 11, "kode": "PDRB.NM", "jenis": "pdrb_nonmigas", "induk": None, "urutan": 11},
    ]


def _def(iid, out, ntb, ih=100.0):
    return {"id": iid, "metode": "DEF", "seri": {"OUT_ADHB": {u: out for u in T25 + [N1]},
            "NTB_ADHB": {u: ntb for u in T25 + [N1]}, "IH": {u: ih for u in T25 + [N1]}}}


def _spec(data):
    return {"tahun_baseline": 2025, "jangkar_dari_data": True, "awal": U0, "akhir": N1, "pohon": _pohon(),
            "referensi": {}, "data": data}


def test_agregasi_total_dan_migas():
    data = {2: {"item": [_def(1, 100, 60)]}, 3: {"item": [_def(2, 50, 20)]}, 4: {"item": [_def(3, 30, 10)]},
            7: {"item": [_def(4, 8, 1)]}, 8: {"item": [_def(5, 3, 3)]}}
    h = kp.hitung_wilayah(_spec(data))
    t = N1 - U0
    assert h[1]["benc"].gva_cp[t] == 80 and h[5]["final"].gva_cp[t] == 90 and h[6]["benc"].gva_cp[t] == 90
    assert h[7]["benc"].gva_cp[t] == 8 and h[7]["benc"].out_cp[t] == 8         # TOP: NTB = output
    assert h[9]["benc"].gva_cp[t] == 5 and h[10]["benc"].gva_cp[t] == 95 and h[11]["benc"].gva_cp[t] == 75
    assert h[10]["benc"].out_cp[t] == 185


def test_margin_dari_benc_dan_siklus():
    g = {"id": 9, "metode": "DEF", "seri": {"R_MARGIN": {u: 0.1 for u in T25 + [N1]}, "IH": {}},
         "parameter": {"R_MARGIN_TD": 0.1},
         "tautan": [{"jenis_seri": "OUT_ADHB", "sumber": "RUMUS", "rumus": "MARGIN_X_OUTPUT", "lapus_sumber": [1],
                     "faktor": 1.0}]}
    sim = {"tahap": "SIMULASI", "jenis": "SIM_NTB", "harga": "CP", "periode": N1, "nilai": 40.0}
    data = {2: {"item": [_def(1, 100, 60)], "penyesuaian": [sim]}, 3: {"item": [_def(2, 50, 20)]},
            4: {"item": [g]}}
    h = kp.hitung_wilayah(_spec(data))
    t = N1 - U0
    assert abs(h[4]["benc"].out_cp[t] - 15) < 1e-12 and abs(h[4]["benc"].out_k[t] - 15) < 1e-12
    assert h[2]["final"].gva_cp[t] == 100 and abs(h[2]["final"].out_cp[t] - 100 * 100 / 60) < 1e-9
    data[2]["item"][0]["tautan"] = [{"jenis_seri": "IH", "sumber": "HASIL_LAPUS", "lapus_sumber": [4],
                                     "besaran": "IMPLISIT_OUT", "faktor": 1.0}]
    with pytest.raises(kp.GalatSpek):
        kp.hitung_wilayah(_spec(data))


def test_tabel_turunan():
    x = [100.0, 110.0, 0.0, 120.0, 105.0, 121.0, 10.0, 126.0]
    assert kp.laju(x, 1)[1] == pytest.approx(10) and kp.laju(x, 1)[3] is None and kp.laju(x, 1)[0] is None
    assert kp.laju(x, 4)[4] == pytest.approx(5)
    assert kp.laju_ctc(x)[5] == pytest.approx((105 + 121) / 210 * 100 - 100)
    assert kp.sog(x, [1000.0] * 8, 4)[4] == pytest.approx(0.5)
    assert kp.sog_ctc(x, [1000.0] * 8)[5] == pytest.approx(16 / 2000 * 100)
    assert kp.implisit([110.0], [100.0])[0] == pytest.approx(110) and kp.distribusi([5.0], [0.0])[0] is None
    assert kp.laju_ctc(x, awal_q=2)[3] is None and kp.laju_ctc(x, awal_q=2)[7] == pytest.approx(136 / 120 * 100 - 100)
    assert t_of(2019, 1) == 0
