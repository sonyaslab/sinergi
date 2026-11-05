"""Uji unit mesin rujukan dengan angka kecil yang dihitung manual (jalankan: python -m pytest engine_ref)."""
from engine_ref.lk_engine import ItemREV, ItemEKS, ItemDEF, hitung_rev, hitung_eks, hitung_def, t_of

T1, T2, T3, T4 = (t_of(2025, q) for q in (1, 2, 3, 4))
N1 = t_of(2026, 1)


def test_rev_td2025_harga_tertimbang():
    it = ItemREV("x", P={T1: 10, T2: 30, T3: 0, T4: 0, N1: 20}, H={T1: 2, T2: 4, N1: 5}, RKA={N1: 0.25}, RKA_TD=0.2)
    oc, gc, ok, gk = hitung_rev([it])
    hbar = (10 * 2 + 30 * 4) / 40          # 3,5
    assert oc[N1] == 100 and gc[N1] == 75
    assert abs(ok[N1] - 20 * hbar) < 1e-9 and abs(gk[N1] - 0.8 * 20 * hbar) < 1e-9


def test_rev_td2010_jangkar_harga():
    it = ItemREV("x", P={N1: 20}, H={N1: 5}, RKA={N1: 0.1}, RKA_TD=0.1, H_TD=1.5)
    oc, gc, ok, gk = hitung_rev([it])
    assert ok[N1] == 30 and abs(gk[N1] - 27) < 1e-9


def test_eks_ip_rantai_maju_mundur():
    I = {t_of(2024, 4): 90, T1: 100, T2: 100, T3: 100, T4: 100, N1: 110}
    it = ItemEKS("x", jenis="INDEKS PRODUKSI", I=I, IH={t: 100 for t in I}, base_k=[50, 50, 50, 50], RKA_TD=0.0)
    oc, gc, ok, gk = hitung_eks([it])
    assert abs(ok[N1] - 55) < 1e-9 and abs(ok[t_of(2024, 4)] - 45) < 1e-9


def test_def_td2025_dan_td2010():
    a = ItemDEF("a", OUT_CP={T1: 100, T2: 100, T3: 100, T4: 100, N1: 120}, GVA_CP={T1: 60, T2: 60, T3: 60, T4: 60, N1: 70},
                IH={T1: 100, T2: 100, T3: 100, T4: 100, N1: 120})
    oc, gc, ok, gk = hitung_def([a])
    assert ok[N1] == 100 and abs(gk[N1] - 60) < 1e-9 and gc[N1] == 70
    b = ItemDEF("b", OUT_CP={N1: 120}, IH={N1: 120}, RKA_TD=0.0, IH_TD=100)   # pola PEN TD2010: NTB = output
    oc, gc, ok, gk = hitung_def([b])
    assert gc[N1] == 120 and ok[N1] == 100 and gk[N1] == 100


# ---------------------------------------------------------------- keputusan 5 Nov 2026 (docs/02 §11)
from engine_ref.lk_engine import AdjRekon, Hasil, t_base_tahun, tahap_rekon  # noqa: E402

TB10 = t_base_tahun(2024)   # TD2010: tahun baseline EKS 2024
B1, B2, B3, B4 = TB10


def test_rev_td2010_tanpa_h_td_tidak_dari_data():
    it = ItemREV("x", P={T1: 10, T2: 30, N1: 20}, H={T1: 2, T2: 4, N1: 5}, RKA_TD=0.2)
    oc, gc, ok, gk = hitung_rev([it], jangkar_dari_data=False)
    assert oc[N1] == 100 and ok[N1] == 0 and gk[N1] == 0       # H_TD kosong -> ADHK 0 (V03)


def test_eks_td2010_ih_td_parameter_dan_baseline_2024():
    I = {B4: 100, N1: 120}
    it = ItemEKS("x", jenis="INDEKS BERLAKU", I={B1: 100, B2: 100, B3: 100, **I}, IH={B1: 90, B2: 90, B3: 90, B4: 90},
                 base_cp=[90, 90, 90, 90], RKA_TD=0.0, IH_TD=100)
    oc, gc, ok, gk = hitung_eks([it], t_base=TB10, jangkar_dari_data=False)
    assert oc[B4] == 90 and abs(ok[B4] - 100) < 1e-9           # K = CP / IH x IH_TD
    it.IH_TD = None
    oc, gc, ok, gk = hitung_eks([it], t_base=TB10, jangkar_dari_data=False)
    assert ok[B4] == 0                                         # IH_TD kosong -> 0, bukan rata-rata 2024


def test_def_td2010_rka_td_dari_parameter_bukan_data():
    a = ItemDEF("a", OUT_CP={B1: 100, B2: 100, B3: 100, B4: 100, N1: 120},
                GVA_CP={B1: 60, B2: 60, B3: 60, B4: 60, N1: 70}, IH={N1: 120}, RKA_TD=0.1, IH_TD=100)
    oc, gc, ok, gk = hitung_def([a], t_base=TB10, jangkar_dari_data=False)
    assert ok[N1] == 100 and abs(gk[N1] - 90) < 1e-9 and gc[N1] == 70
    oc, gc, ok, gk = hitung_def([a], t_base=TB10, jangkar_dari_data=True)   # perilaku lama: rasio data 2024
    assert abs(gk[N1] - 60) < 1e-9


def test_tanpa_ka_top_sop():
    r = ItemREV("cukai", P={N1: 10}, H={N1: 3}, RKA={N1: 0.4}, RKA_TD=0.5, H_TD=2)
    d = ItemDEF("ppn", OUT_CP={N1: 50}, GVA_CP={N1: 10}, IH={N1: 125}, IH_TD=100, RKA_TD=0.3)
    oc, gc, ok, gk = hitung_rev([r], tanpa_ka=True)
    assert (oc[N1], gc[N1], ok[N1], gk[N1]) == (30, 30, 20, 20)
    oc, gc, ok, gk = hitung_def([d], tanpa_ka=True)
    assert (oc[N1], gc[N1], ok[N1], gk[N1]) == (50, 50, 40, 40)


def test_def_out_k_langsung():
    d = ItemDEF("margin", OUT_CP={N1: 50}, IH={N1: 200}, IH_TD=100, RKA={N1: 0.2}, RKA_TD=0.25, OUT_K={N1: 40})
    oc, gc, ok, gk = hitung_def([d], jangkar_dari_data=False)
    assert ok[N1] == 40 and gk[N1] == 30 and gc[N1] == 40


def test_tahap_rekon_pre_post_benc():
    p = ([100.0] + [0.0] * 107, [60.0] + [0.0] * 107, [80.0] + [0.0] * 107, [50.0] + [0.0] * 107)
    adj = AdjRekon(out_cp_adj3={0: 10}, out_cp_adj4={0: 5}, gva_cp_adj4={0: -2}, out_k_adj3={0: -8})
    pre, post, benc = tahap_rekon([p], adj)
    assert isinstance(benc, Hasil) and pre.out_cp[0] == 100
    assert post.out_cp[0] == 110 and abs(post.gva_cp[0] - 66) < 1e-12
    assert benc.out_cp[0] == 115 and abs(benc.gva_cp[0] - 64) < 1e-12
    assert post.out_k[0] == 72 and abs(post.gva_k[0] - 45) < 1e-12
