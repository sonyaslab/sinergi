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
