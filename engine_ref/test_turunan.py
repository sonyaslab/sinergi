"""Uji oracle rumus turunan (angka kecil dihitung manual)."""
from engine_ref import turunan as tr
from engine_ref.lk_engine import NQ, Hasil, t_base_tahun, t_of

TB = t_base_tahun(2025)
N1 = t_of(2026, 1)


def test_tpk_x_kamar_sesuai_lk():
    s = tr.tpk_x_kamar({N1: 35.99, N1 + 1: None}, {N1: 375, N1 + 2: 10})
    assert abs(s[N1] - 13496.25) < 1e-9 and N1 + 1 not in s and s[N1 + 2] == 0


def test_jangkar_x_ih_100_dan_kapita():
    assert tr.jangkar_x_ih_100(1500, {N1: 110}) == {N1: 1650}
    assert tr.jangkar_x_ih_100(None, {N1: 110}) == {N1: 0}
    s = tr.kapita_x_penduduk_x_3({N1: 200000}, {N1: 700000}, 0.8865)
    assert abs(s[N1] - 200000 * 700000 * 3 / 1e6 * 0.8865) < 1e-6


def test_seri_referensi_dan_hasil_lapus():
    assert tr.seri_referensi({N1: 120.0, N1 + 1: None}, 0.5) == {N1: 60.0}
    a = Hasil([1.0] * NQ, [0.5] * NQ, [2.0] * NQ, [1.0] * NQ)
    b = Hasil([3.0] * NQ, [1.0] * NQ, [2.0] * NQ, [1.5] * NQ)
    assert tr.hasil_lapus([a, b], "OUT_CP", 2)[N1] == 8
    assert tr.hasil_lapus([a, b], "IMPLISIT_OUT")[N1] == 100


def test_margin_x_output_arus_barang():
    cp = [0.0] * NQ; k = [0.0] * NQ
    for t in TB:
        cp[t], k[t] = 100.0, 100.0
    cp[N1], k[N1] = 150.0, 120.0
    r = {t: 0.1 for t in TB} | {N1: 0.12}
    o_cp, o_k = tr.margin_x_output(r, cp, k, 1.0, None, TB, True)       # TD2025: R_TD dari data = 0,1
    assert abs(o_cp[N1] - 18) < 1e-12 and abs(o_k[N1] - 12) < 1e-12 and N1 + 1 not in o_k
    o_cp, o_k = tr.margin_x_output(r, cp, k, 2.0, 0.05, TB, False)      # TD2010: R_MARGIN_TD parameter
    assert abs(o_cp[N1] - 36) < 1e-12 and abs(o_k[N1] - 12) < 1e-12
    _, o_k = tr.margin_x_output(r, cp, k, 1.0, None, TB, False)         # parameter kosong -> 0 (V03)
    assert o_k[N1] == 0


def test_margin_x_impor_dengan_kurs():
    r = {N1: 0.2}; vi = {N1: 10.0}; kurs = {N1: 15000.0}; ih = {N1: 150.0}
    o_cp, o_k = tr.margin_x_impor(r, vi, kurs, ih, 100.0, 0.001, 0.1, TB, False)
    assert abs(o_cp[N1] - 0.2 * 10 * 15000 * 0.001) < 1e-12
    assert abs(o_k[N1] - 0.1 * (150000 / 150 * 100) * 0.001) < 1e-12
    o_cp, _ = tr.margin_x_impor(r, vi, None, ih, 100.0, 1.0, 0.1, TB, False)   # tanpa seri KURS -> 1
    assert abs(o_cp[N1] - 2.0) < 1e-12


def test_potong_masa():
    assert tr.potong_masa({1: 1.0, 5: 2.0, 9: 3.0}, 2, 8) == {5: 2.0}
    assert tr.potong_masa({1: 1.0}, None, None) == {1: 1.0}
