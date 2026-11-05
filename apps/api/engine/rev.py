"""REV — revaluasi: output = kuantum × harga; ADHK = kuantum × harga tahun dasar (docs/02 §3, §2, §11)."""
from __future__ import annotations

from .model import Empat, ItemSiap, Sumbu
from .umum import bagi, v


def hitung(it: ItemSiap, sb: Sumbu, t0: list[int], jangkar_dari_data: bool, tanpa_ka: bool) -> Empat:
    p, h, rka = it.s("KUANTUM"), it.s("HARGA"), it.s("RKA")
    h_td = it.p("H_TD")
    if h_td is not None:
        h_bar = h_td
    elif jangkar_dari_data:
        h_bar = bagi(sum(v(p, u) * v(h, u) for u in t0), sum(v(p, u) for u in t0))
    else:
        h_bar = 0.0  # TD2010: H_TD wajib (V03)
    rka_td = it.p("RKA_TD") or 0.0
    n = len(sb)
    e = Empat.nol(n)
    for t, u in enumerate(sb.periode):
        out_cp = v(p, u) * v(h, u)
        out_k = v(p, u) * h_bar
        e.out_cp[t] = out_cp
        e.out_k[t] = out_k
        if tanpa_ka:
            e.gva_cp[t] = out_cp
            e.gva_k[t] = out_k
        else:
            e.gva_cp[t] = (1 - v(rka, u)) * out_cp
            e.gva_k[t] = (1 - rka_td) * out_k
    return e
