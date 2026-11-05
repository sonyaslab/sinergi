"""Penyesuaian tahap METODE dan SIMULASI (docs/02 §6).

METODE (per lapus × metode × triwulan, ADHB/ADHK terpisah):
  Output PRE = ΣOutput + ADJ1 + ADJ2 + SC;  NTB PRE = ΣNTB + r × (ADJ1 + SC) + r × ADJ2, r = ΣNTB ÷ ΣOutput.
SIMULASI (per lapus berdata × triwulan): NTB final = NTB BENC + SIM; Output final = Output × NTB final ÷ NTB.
  Tanpa SIM (nilai 0) baris FINAL = BENC apa adanya.
Hanya penyesuaian yang ikut angka resmi (disetujui) yang masuk; pratinjau draf dihitung terpisah (keputusan 8a).
"""
from __future__ import annotations

from .model import Empat, Seri
from .umum import bagi, v

JENIS_METODE = ("ADJ1", "ADJ2", "SC")


def pre_metode(pr: Empat, adj: dict[tuple[str, str], Seri], periode: range) -> Empat:
    """adj[(jenis, harga)] -> seri; jenis ADJ1/ADJ2/SC, harga CP/K."""
    e = Empat.nol(len(pr.out_cp))
    a1c, a2c, scc = adj.get(("ADJ1", "CP")), adj.get(("ADJ2", "CP")), adj.get(("SC", "CP"))
    a1k, a2k, sck = adj.get(("ADJ1", "K")), adj.get(("ADJ2", "K")), adj.get(("SC", "K"))
    for t, u in enumerate(periode):
        a1, a2, sc = v(a1c, u), v(a2c, u), v(scc, u)
        k1, k2, ksc = v(a1k, u), v(a2k, u), v(sck, u)
        rc = bagi(pr.gva_cp[t], pr.out_cp[t])
        rk = bagi(pr.gva_k[t], pr.out_k[t])
        e.out_cp[t] = pr.out_cp[t] + a1 + a2 + sc
        e.gva_cp[t] = pr.gva_cp[t] + rc * (a1 + sc) + rc * a2
        e.out_k[t] = pr.out_k[t] + k1 + k2 + ksc
        e.gva_k[t] = pr.gva_k[t] + rk * (k1 + ksc) + rk * k2
    return e


def simulasi(benc: Empat, sim_cp: Seri, sim_k: Seri, periode: range) -> Empat:
    fin = benc.salin()
    for t, u in enumerate(periode):
        s = v(sim_cp, u)
        if s != 0:
            fin.gva_cp[t] = benc.gva_cp[t] + s
            fin.out_cp[t] = benc.out_cp[t] * bagi(fin.gva_cp[t], benc.gva_cp[t])
        s = v(sim_k, u)
        if s != 0:
            fin.gva_k[t] = benc.gva_k[t] + s
            fin.out_k[t] = benc.out_k[t] * bagi(fin.gva_k[t], benc.gva_k[t])
    return fin


def adj_target_laju(ntb_t_min_4: float, laju_persen: float, ntb_kompilasi: float) -> float:
    """Bantuan input SIM ADHK: adj = NTB(t−4) × (1 + g/100) − NTB kompilasi."""
    return ntb_t_min_4 * (1 + laju_persen / 100) - ntb_kompilasi


def adj_target_implisit(implisit: float, ntb_adhk: float, ntb_adhb_kompilasi: float) -> float:
    """Bantuan input SIM ADHB: adj = target implisit × NTB ADHK ÷ 100 − NTB ADHB."""
    return implisit * ntb_adhk / 100 - ntb_adhb_kompilasi
