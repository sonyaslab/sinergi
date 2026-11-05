"""EKS — ekstrapolasi: baseline T₀ dirantai indeks q-to-q maju dan mundur (docs/02 §4, §2, §11).

IP (indeks produksi) menggerakkan ADHK; IB (indeks berlaku) menggerakkan ADHB. Jenis indeks kosong = item tidak
berkontribusi. Rantai putus (indeks kosong) membuat periode sesudah/sebelumnya 0 (V04).
"""
from __future__ import annotations

from .model import Empat, ItemSiap, Sumbu
from .umum import bagi, rata_isi, v


def hitung(it: ItemSiap, sb: Sumbu, t0: list[int], jangkar_dari_data: bool, tanpa_ka: bool) -> Empat:
    n = len(sb)
    e = Empat.nol(n)
    jenis = (it.jenis_indeks or "").strip().upper()
    if jenis not in ("IP", "IB"):
        return e
    ib = jenis == "IB"
    ind, ih = it.s("INDEKS"), it.s("IH")
    ih_td = it.p("IH_TD")
    if ih_td is not None:
        ih_bar = ih_td
    else:
        ih_bar = rata_isi(ih, t0) if jangkar_dari_data else 0.0
    us = list(sb.periode)
    cp, k = [0.0] * n, [0.0] * n
    # 1) tahun baseline
    for u in t0:
        t = sb.i(u)
        if ib:
            cp[t] = v(it.s("BASE_ADHB"), u)
            k[t] = bagi(cp[t], v(ih, u)) * ih_bar
        else:
            k[t] = v(it.s("BASE_ADHK"), u)
            cp[t] = bagi(k[t] * v(ih, u), ih_bar)
    # 2) maju
    for t in range(sb.i(t0[-1]) + 1, n):
        u = us[t]
        if ib:
            cp[t] = bagi(v(ind, u), v(ind, u - 1)) * cp[t - 1]
            k[t] = bagi(cp[t], v(ih, u)) * ih_bar
        else:
            k[t] = bagi(v(ind, u), v(ind, u - 1)) * k[t - 1]
            cp[t] = bagi(k[t] * v(ih, u), ih_bar)
    # 3) mundur (backcast)
    for t in range(sb.i(t0[0]) - 1, -1, -1):
        u = us[t]
        if ib:
            cp[t] = bagi(v(ind, u), v(ind, u + 1)) * cp[t + 1]
            k[t] = bagi(cp[t], v(ih, u)) * ih_bar
        else:
            k[t] = bagi(v(ind, u), v(ind, u + 1)) * k[t + 1]
            cp[t] = bagi(k[t] * v(ih, u), ih_bar)
    rka, rka_td = it.s("RKA"), it.p("RKA_TD") or 0.0
    for t, u in enumerate(us):
        e.out_cp[t] = cp[t]
        e.out_k[t] = k[t]
        if tanpa_ka:
            e.gva_cp[t] = cp[t]
            e.gva_k[t] = k[t]
        else:
            e.gva_cp[t] = (1 - v(rka, u)) * cp[t]
            e.gva_k[t] = (1 - rka_td) * k[t]
    return e
