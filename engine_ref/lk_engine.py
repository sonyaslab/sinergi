"""
Referensi mesin hitung LK PDRB Triwulanan TD2025 (replika 1:1 rumus Excel
"01 LK PDRB Triwulanan TD2025 v.1.0").

Dipakai sebagai ORACLE untuk pengujian mesin produksi (apps/api/engine = sinergi_api.engine).
Tidak mengandung data. Semua angka masuk lewat struktur dict.

Keputusan metodologi docs/02 §11 (diterapkan F2):
- `jangkar_dari_data` (ref.tahun_dasar): True (TD2025) = jangkar kosong dihitung dari data tahun baseline;
  False (TD2010) = jangkar hanya dari parameter (kosong = 0, diblokir V03); tahun baseline hanya titik awal
  rantai EKS. DEF TD2010 memakai RKA_TD parameter, bukan rasio tahun baseline (keputusan 3).
- `tanpa_ka`: lapus TOP/SOP tidak punya konsumsi antara, NTB = output (keputusan 1).
- ItemDEF.OUT_K: output ADHK langsung dari rumus turunan margin (arus barang, keputusan 4; engine_ref/turunan.py).

Konvensi periode: t = indeks kuartal mulai 2019Q1 = 0 ... 2045Q4 = 107.
Nilai kosong (None) mengikuti perilaku Excel: dalam perkalian/penjumlahan = 0,
pembagian dengan 0/kosong -> IFERROR -> 0.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

TAHUN_AWAL = 2019
TAHUN_AKHIR = 2045
TAHUN_DASAR = 2025
NQ = (TAHUN_AKHIR - TAHUN_AWAL + 1) * 4


def t_of(tahun: int, q: int) -> int:
    return (tahun - TAHUN_AWAL) * 4 + (q - 1)


def label(t: int) -> str:
    return f"Q{t % 4 + 1}-{TAHUN_AWAL + t // 4}"


T_BASE = [t_of(TAHUN_DASAR, q) for q in (1, 2, 3, 4)]
Series = Dict[int, Optional[float]]  # t -> nilai


def v(s: Series, t: int) -> float:
    x = s.get(t) if s else None
    return float(x) if isinstance(x, (int, float)) else 0.0


def div(a: float, b: float) -> float:
    return a / b if b else 0.0  # IFERROR(...,0)


def avg_nonblank(s: Series, ts: List[int]) -> float:
    xs = [float(s[t]) for t in ts if s and isinstance(s.get(t), (int, float))]
    return sum(xs) / len(xs) if xs else 0.0  # AVERAGE + IFERROR


# ---------------------------------------------------------------- input model
@dataclass
class ItemREV:            # INPUT_REVALUASI baris produk ke-i
    nama: str
    P: Series = field(default_factory=dict)        # kuantum produksi
    H: Series = field(default_factory=dict)        # harga (Rp juta/satuan)
    RKA: Series = field(default_factory=dict)      # rasio konsumsi antara per triwulan
    RKA_TD: Optional[float] = None                 # rasio KA tahunan 2025 (input, kolom Y-2025)
    H_TD: Optional[float] = None                   # jangkar harga tahun dasar (TD2010: harga 2010). None = rata-rata tertimbang tahun dasar


@dataclass
class ItemEKS:            # INPUT_EKSTRAPOLASI item ke-i
    nama: str
    jenis: str = ""                                # "INDEKS PRODUKSI" | "INDEKS BERLAKU" | ""
    I: Series = field(default_factory=dict)        # indeks ekstrapolator
    IH: Series = field(default_factory=dict)       # indeks harga (deflator) item
    base_cp: List[Optional[float]] = field(default_factory=lambda: [None] * 4)  # baseline ADHB 2025 Q1..Q4
    base_k: List[Optional[float]] = field(default_factory=lambda: [None] * 4)   # baseline ADHK 2025 Q1..Q4
    RKA: Series = field(default_factory=dict)
    RKA_TD: Optional[float] = None
    bobot: Optional[float] = None                  # hanya untuk indeks agregat (tampilan)
    IH_TD: Optional[float] = None                  # jangkar IH tahun dasar (TD2010: 100). None = rata-rata IH tahun dasar


@dataclass
class ItemDEF:            # INPUT_DEFLASI item ke-i
    nama: str
    OUT_CP: Series = field(default_factory=dict)
    GVA_CP: Series = field(default_factory=dict)
    IH: Series = field(default_factory=dict)
    RKA: Series = field(default_factory=dict)      # dipakai hanya bila GVA_CP periode itu kosong (pola TD2010)
    RKA_TD: Optional[float] = None                 # dipakai hanya bila tidak ada data tahun dasar (pola TD2010)
    IH_TD: Optional[float] = None
    OUT_K: Optional[Series] = None                 # output ADHK langsung (rumus margin arus barang); None = deflasi


@dataclass
class AdjMetode:          # ADJ1 (coverage), ADJ2 (conceptual), SC (output sekunder), per lembar metode
    cp_adj1: Series = field(default_factory=dict)
    cp_adj2: Series = field(default_factory=dict)
    cp_sc: Series = field(default_factory=dict)
    k_adj1: Series = field(default_factory=dict)
    k_adj2: Series = field(default_factory=dict)
    k_sc: Series = field(default_factory=dict)


@dataclass
class AdjRekon:           # REKONSILIASI: ADJ3 (rekonsiliasi), ADJ4 (benchmarking)
    out_cp_adj3: Series = field(default_factory=dict)
    out_cp_adj4: Series = field(default_factory=dict)
    gva_cp_adj4: Series = field(default_factory=dict)
    out_k_adj3: Series = field(default_factory=dict)
    out_k_adj4: Series = field(default_factory=dict)
    gva_k_adj4: Series = field(default_factory=dict)


@dataclass
class Hasil:              # 4 seri utama + rincian
    out_cp: List[float]
    gva_cp: List[float]
    out_k: List[float]
    gva_k: List[float]


def _zeros():
    return [0.0] * NQ


# ---------------------------------------------------------------- per metode
def _num(x) -> bool:
    return isinstance(x, (int, float))


def hitung_rev(items: List[ItemREV], t_base: List[int] = T_BASE, jangkar_dari_data: bool = True,
               tanpa_ka: bool = False):
    oc, gc, ok, gk = _zeros(), _zeros(), _zeros(), _zeros()
    for it in items:
        out_cp = [v(it.P, t) * v(it.H, t) for t in range(NQ)]
        if _num(it.H_TD):
            h_bar = it.H_TD
        elif jangkar_dari_data:
            h_bar = div(sum(out_cp[t] for t in t_base), sum(v(it.P, t) for t in t_base))
        else:
            h_bar = 0.0  # TD2010: harga tahun dasar wajib diisi (V03)
        rka_td = it.RKA_TD if _num(it.RKA_TD) else 0.0
        for t in range(NQ):
            out_k = v(it.P, t) * h_bar
            oc[t] += out_cp[t]
            ok[t] += out_k
            if tanpa_ka:
                gc[t] += out_cp[t]
                gk[t] += out_k
            else:
                gc[t] += (1 - v(it.RKA, t)) * out_cp[t]
                gk[t] += (1 - rka_td) * out_k
    return oc, gc, ok, gk


def hitung_eks(items: List[ItemEKS], t_base: List[int] = T_BASE, jangkar_dari_data: bool = True,
               tanpa_ka: bool = False):
    oc, gc, ok, gk = _zeros(), _zeros(), _zeros(), _zeros()
    for it in items:
        cp, k = _zeros(), _zeros()
        jenis = (it.jenis or "").strip().upper()
        if jenis not in ("INDEKS PRODUKSI", "INDEKS BERLAKU"):
            continue  # $E kosong -> 0
        ib = jenis == "INDEKS BERLAKU"
        if _num(it.IH_TD):
            ih_bar = it.IH_TD
        else:
            ih_bar = avg_nonblank(it.IH, t_base) if jangkar_dari_data else 0.0
        # 1) tahun baseline (TD2025 = tahun dasar 2025; TD2010 = tahun_baseline_eks, hanya titik awal rantai)
        for q, t in enumerate(t_base):
            if ib:
                cp[t] = v({0: it.base_cp[q]}, 0)
                k[t] = div(cp[t], v(it.IH, t)) * ih_bar
            else:
                k[t] = v({0: it.base_k[q]}, 0)
                k_ = k[t]
                cp[t] = div(k_ * v(it.IH, t), ih_bar)
        # 2) maju (t > 2025Q4): rantai dari kuartal sebelumnya
        for t in range(t_base[-1] + 1, NQ):
            if ib:
                cp[t] = div(v(it.I, t), v(it.I, t - 1)) * cp[t - 1]
                k[t] = div(cp[t], v(it.IH, t)) * ih_bar
            else:
                k[t] = div(v(it.I, t), v(it.I, t - 1)) * k[t - 1]
                cp[t] = div(k[t] * v(it.IH, t), ih_bar)
        # 3) mundur / backcasting (t < 2025Q1): dari kuartal sesudahnya
        for t in range(t_base[0] - 1, -1, -1):
            if ib:
                cp[t] = div(v(it.I, t), v(it.I, t + 1)) * cp[t + 1]
                k[t] = div(cp[t], v(it.IH, t)) * ih_bar
            else:
                k[t] = div(v(it.I, t), v(it.I, t + 1)) * k[t + 1]
                cp[t] = div(k[t] * v(it.IH, t), ih_bar)
        rka_td = it.RKA_TD if _num(it.RKA_TD) else 0.0
        for t in range(NQ):
            oc[t] += cp[t]
            ok[t] += k[t]
            if tanpa_ka:
                gc[t] += cp[t]
                gk[t] += k[t]
            else:
                gc[t] += (1 - v(it.RKA, t)) * cp[t]
                gk[t] += (1 - rka_td) * k[t]
    return oc, gc, ok, gk


def hitung_def(items: List[ItemDEF], t_base: List[int] = T_BASE, jangkar_dari_data: bool = True,
               tanpa_ka: bool = False):
    oc, gc, ok, gk = _zeros(), _zeros(), _zeros(), _zeros()
    for it in items:
        rka_s, rka_p = getattr(it, "RKA", None), getattr(it, "RKA_TD", None)
        if _num(it.IH_TD):
            ih_bar = it.IH_TD
        else:
            ih_bar = avg_nonblank(it.IH, t_base) if jangkar_dari_data else 0.0
        if jangkar_dari_data:
            rka_td = 1 - div(sum(v(it.GVA_CP, t) for t in t_base), sum(v(it.OUT_CP, t) for t in t_base))
            if sum(v(it.OUT_CP, t) for t in t_base) == 0:
                rka_td = 0.0  # IFERROR(1-(AP191/AP11),0)
                if _num(rka_p):
                    rka_td = rka_p  # tidak ada data tahun dasar -> jangkar
        else:
            rka_td = rka_p if _num(rka_p) else 0.0  # TD2010: RKA_TD selalu dari parameter (keputusan 3)
        for t in range(NQ):
            if it.OUT_K is not None:
                k = v(it.OUT_K, t)  # rumus margin arus barang (engine_ref/turunan.py)
            else:
                k = div(v(it.OUT_CP, t), v(it.IH, t)) * ih_bar
            oc[t] += v(it.OUT_CP, t)
            ok[t] += k
            if tanpa_ka:
                gc[t] += v(it.OUT_CP, t)
                gk[t] += k
                continue
            g = it.GVA_CP.get(t) if it.GVA_CP else None
            if not isinstance(g, (int, float)) and (rka_s or isinstance(rka_p, (int, float))):
                r = rka_s.get(t) if rka_s else None
                g = (1 - (r if isinstance(r, (int, float)) else (rka_p or 0.0))) * v(it.OUT_CP, t)
            gc[t] += g if isinstance(g, (int, float)) else 0.0
            gk[t] += (1 - rka_td) * k
    return oc, gc, ok, gk


def pre_rekon(prim, adj: AdjMetode):
    """Tambahkan ADJ1/ADJ2/SC pada satu lembar metode; NTB adj = rasio NTB/output utama x adj."""
    oc, gc, ok, gk = prim
    r_oc, r_gc, r_ok, r_gk = _zeros(), _zeros(), _zeros(), _zeros()
    for t in range(NQ):
        a1, a2, sc = v(adj.cp_adj1, t), v(adj.cp_adj2, t), v(adj.cp_sc, t)
        k1, k2, ksc = v(adj.k_adj1, t), v(adj.k_adj2, t), v(adj.k_sc, t)
        rc = div(gc[t], oc[t])
        rk = div(gk[t], ok[t])
        r_oc[t] = oc[t] + a1 + a2 + sc
        r_gc[t] = gc[t] + rc * (a1 + sc) + rc * a2
        r_ok[t] = ok[t] + k1 + k2 + ksc
        r_gk[t] = gk[t] + rk * (k1 + ksc) + rk * k2
    return r_oc, r_gc, r_ok, r_gk


def tahap_rekon(pres: list, adj: AdjRekon):
    """Jumlahkan REV+EKS+DEF (PRE), lalu ADJ3 (POST, NTB proporsional) dan ADJ4 (BENC, output dan NTB terpisah).

    Mengembalikan (pre, post, benc), masing-masing Hasil.
    """
    oc, gc, ok, gk = _zeros(), _zeros(), _zeros(), _zeros()
    for p in pres:
        for t in range(NQ):
            oc[t] += p[0][t]; gc[t] += p[1][t]; ok[t] += p[2][t]; gk[t] += p[3][t]
    pre = Hasil(list(oc), list(gc), list(ok), list(gk))
    post = Hasil(_zeros(), _zeros(), _zeros(), _zeros())
    res = Hasil(_zeros(), _zeros(), _zeros(), _zeros())
    for t in range(NQ):
        a3, a4, g4 = v(adj.out_cp_adj3, t), v(adj.out_cp_adj4, t), v(adj.gva_cp_adj4, t)
        post.out_cp[t] = oc[t] + a3
        post.gva_cp[t] = gc[t] + div(a3, oc[t]) * gc[t]
        res.out_cp[t] = post.out_cp[t] + a4
        res.gva_cp[t] = post.gva_cp[t] + g4
        a3, a4, g4 = v(adj.out_k_adj3, t), v(adj.out_k_adj4, t), v(adj.gva_k_adj4, t)
        post.out_k[t] = ok[t] + a3
        post.gva_k[t] = gk[t] + div(a3, ok[t]) * gk[t]
        res.out_k[t] = post.out_k[t] + a4
        res.gva_k[t] = post.gva_k[t] + g4
    return pre, post, res


def rekonsiliasi(pres: list, adj: AdjRekon) -> Hasil:
    """Jumlahkan REV+EKS+DEF, lalu ADJ3 (proporsional ke NTB) dan ADJ4 (input terpisah) -> BENC."""
    return tahap_rekon(pres, adj)[2]


def hitung_industri(rev: List[ItemREV], eks: List[ItemEKS], dfl: List[ItemDEF],
                    adj_rev: AdjMetode, adj_eks: AdjMetode, adj_def: AdjMetode,
                    adj_rekon: AdjRekon, t_base: List[int] = T_BASE, jangkar_dari_data: bool = True,
                    tanpa_ka: bool = False) -> Hasil:
    kw = dict(t_base=t_base, jangkar_dari_data=jangkar_dari_data, tanpa_ka=tanpa_ka)
    return rekonsiliasi([
        pre_rekon(hitung_rev(rev, **kw), adj_rev),
        pre_rekon(hitung_eks(eks, **kw), adj_eks),
        pre_rekon(hitung_def(dfl, **kw), adj_def),
    ], adj_rekon)


def t_base_tahun(tahun: int) -> List[int]:
    """4 triwulan tahun baseline (TD2025 = 2025; TD2010 = ref.tahun_dasar.tahun_baseline_eks)."""
    return [t_of(tahun, q) for q in (1, 2, 3, 4)]
