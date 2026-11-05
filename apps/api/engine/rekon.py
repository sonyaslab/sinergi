"""Rekonsiliasi lapus (docs/02 §6, tahap REKON): PRE = REV + EKS + DEF; POST = + ADJ3 (NTB proporsional);
BENC = + ADJ4_OUTPUT / ADJ4_NTB (terpisah). KA = Output − NTB. CT_* hanya pembanding (tidak masuk mesin)."""
from __future__ import annotations

from .model import Empat, Seri
from .umum import bagi, v


def rekonsiliasi(pres: list[Empat], adj: dict[tuple[str, str], Seri], periode: range) -> tuple[Empat, Empat, Empat]:
    n = len(periode)
    pre = Empat.nol(n)
    for p in pres:
        pre.tambah(p)
    post, benc = Empat.nol(n), Empat.nol(n)
    for t, u in enumerate(periode):
        a3, a4 = v(adj.get(("ADJ3", "CP")), u), v(adj.get(("ADJ4_OUTPUT", "CP")), u)
        g4 = v(adj.get(("ADJ4_NTB", "CP")), u)
        post.out_cp[t] = pre.out_cp[t] + a3
        post.gva_cp[t] = pre.gva_cp[t] + bagi(a3, pre.out_cp[t]) * pre.gva_cp[t]
        benc.out_cp[t] = post.out_cp[t] + a4
        benc.gva_cp[t] = post.gva_cp[t] + g4
        a3, a4 = v(adj.get(("ADJ3", "K")), u), v(adj.get(("ADJ4_OUTPUT", "K")), u)
        g4 = v(adj.get(("ADJ4_NTB", "K")), u)
        post.out_k[t] = pre.out_k[t] + a3
        post.gva_k[t] = pre.gva_k[t] + bagi(a3, pre.out_k[t]) * pre.gva_k[t]
        benc.out_k[t] = post.out_k[t] + a4
        benc.gva_k[t] = post.gva_k[t] + g4
    return pre, post, benc
