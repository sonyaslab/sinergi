"""DEF — deflasi: ADHK = output ADHB ÷ IH × ĪH; NTB ADHB input atau (1 − RKA) × output (docs/02 §5, §2, §11).

RKA_TD: TD2025 (jangkar_dari_data) = 1 − Σ₍T₀₎ NTB ADHB ÷ Σ₍T₀₎ output ADHB, parameter hanya bila tidak ada data
T₀; TD2010 = selalu parameter (keputusan 3). Item margin membawa output ADHK langsung (arus barang, keputusan 4).
"""
from __future__ import annotations

from .model import Empat, ItemSiap, Sumbu
from .umum import bagi, rata_isi, v


def hitung(it: ItemSiap, sb: Sumbu, t0: list[int], jangkar_dari_data: bool, tanpa_ka: bool) -> Empat:
    out, gva, ih, rka = it.s("OUT_ADHB"), it.s("NTB_ADHB"), it.s("IH"), it.s("RKA")
    rka_p, ih_td = it.p("RKA_TD"), it.p("IH_TD")
    if ih_td is not None:
        ih_bar = ih_td
    else:
        ih_bar = rata_isi(ih, t0) if jangkar_dari_data else 0.0
    if jangkar_dari_data:
        out_t0 = sum(v(out, u) for u in t0)
        rka_td = 1 - bagi(sum(v(gva, u) for u in t0), out_t0)
        if out_t0 == 0:
            rka_td = rka_p if rka_p is not None else 0.0  # tidak ada data T₀ -> jangkar
    else:
        rka_td = rka_p if rka_p is not None else 0.0
    punya_rka = bool(rka)
    n = len(sb)
    e = Empat.nol(n)
    for t, u in enumerate(sb.periode):
        o = v(out, u)
        k = v(it.out_k, u) if it.out_k is not None else bagi(o, v(ih, u)) * ih_bar
        e.out_cp[t] = o
        e.out_k[t] = k
        if tanpa_ka:
            e.gva_cp[t] = o
            e.gva_k[t] = k
            continue
        g = gva.get(u)
        if g is None and (punya_rka or rka_p is not None):
            r = rka.get(u)
            g = (1 - (r if r is not None else (rka_p or 0.0))) * o
        e.gva_cp[t] = g if g is not None else 0.0
        e.gva_k[t] = (1 - rka_td) * k
    return e
