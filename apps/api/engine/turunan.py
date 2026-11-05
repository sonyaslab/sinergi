"""Penyelesaian seri item sebelum hitung: masa berlaku, tautan (lk.tautan_seri), dan rumus turunan baku.

Urutan: (1) potong nilai di luar masa berlaku item, (2) SERI_REFERENSI, (3) HASIL_LAPUS (tahap BENC),
(4) RUMUS menurut urutan baku, (5) potong masa berlaku lagi. Seri tertaut menggantikan isian manual.

Aturan kosong: nilai rumus pada triwulan t kosong bila semua komponen seri item pada t kosong; komponen kosong
lainnya = 0. Hasil lapus lain selalu terisi. Lihat docs/02 §7 dan §11; oracle: engine_ref/turunan.py.
"""
from __future__ import annotations

from collections.abc import Callable, Sequence

from .model import Empat, GalatMesin, Item, ItemSiap, KonfigTD, Seri, Sumbu
from .umum import bagi, rata_isi, v

RUMUS_BAKU = ("TPK_X_KAMAR", "JANGKAR_X_IH_100", "KAPITA_X_PENDUDUK_X_3", "MARGIN_X_OUTPUT", "MARGIN_X_IMPOR")
# rumus -> (metode yang boleh, seri sasaran)
SASARAN = {
    "TPK_X_KAMAR": ("REV", "KUANTUM"),
    "JANGKAR_X_IH_100": ("REV", "HARGA"),
    "KAPITA_X_PENDUDUK_X_3": ("DEF", "OUT_ADHB"),
    "MARGIN_X_OUTPUT": ("DEF", "OUT_ADHB"),
    "MARGIN_X_IMPOR": ("DEF", "OUT_ADHB"),
}
BESARAN = ("OUT_CP", "OUT_K", "GVA_CP", "GVA_K", "IMPLISIT_OUT")

# Penyedia hasil BENC lapus sumber: daftar lapus_id (sudah diurai) -> Empat per lapus.
PenyediaBenc = Callable[[Sequence[int]], list[Empat]]
PenguraiSumber = Callable[[Sequence[int]], list[int]]


def potong_masa(s: Seri | None, mulai: int | None, selesai: int | None) -> Seri | None:
    if s is None or (mulai is None and selesai is None):
        return s
    return {u: x for u, x in s.items() if (mulai is None or u >= mulai) and (selesai is None or u <= selesai)}


def _gabung(fn: Callable[..., float], *seri: Seri) -> Seri:
    us = sorted(set().union(*(s.keys() for s in seri)))
    return {u: fn(*(v(s, u) for s in seri)) for u in us if any(u in s for s in seri)}


def jumlah(hs: list[Empat], besaran: str, n: int) -> list[float]:
    if besaran == "IMPLISIT_OUT":
        cp, k = jumlah(hs, "OUT_CP", n), jumlah(hs, "OUT_K", n)
        return [bagi(cp[t], k[t]) * 100 for t in range(n)]
    out = [0.0] * n
    for h in hs:
        s = h.besaran(besaran)
        for t in range(n):
            out[t] += s[t]
    return out


def _r_td(r: Seri, basis_cp: list[float], sb: Sumbu, r_td: float | None, konfig: KonfigTD) -> float:
    if r_td is not None:
        return r_td
    if not konfig.jangkar_dari_data:
        return 0.0
    t0 = konfig.t0
    return bagi(sum(v(r, u) * basis_cp[sb.i(u)] for u in t0), sum(basis_cp[sb.i(u)] for u in t0))


def selesaikan(item: Item, sb: Sumbu, konfig: KonfigTD, referensi: dict[str, Seri],
               urai: PenguraiSumber, benc: PenyediaBenc) -> ItemSiap:
    m0, m1 = item.mulai, item.selesai
    seri: dict[str, Seri] = {k: potong_masa(s, m0, m1) or {} for k, s in item.seri.items()}
    par = dict(item.parameter)
    out_k: Seri | None = None
    n = len(sb)

    for tt in item.tautan:
        if tt.sumber == "SERI_REFERENSI":  # seri referensi belum diisi = kosong (ditandai validasi F3)
            seri[tt.jenis_seri] = {u: x * tt.faktor for u, x in referensi.get(tt.seri_ref or "", {}).items()}
    for tt in item.tautan:
        if tt.sumber == "HASIL_LAPUS":
            if tt.besaran not in BESARAN:
                raise GalatMesin(f"Besaran tautan item {item.id} tidak dikenal.")
            s = jumlah(benc(urai(tt.lapus_sumber)), tt.besaran, n)
            seri[tt.jenis_seri] = {u: s[t] * tt.faktor for t, u in enumerate(sb.periode)}
    rumus = sorted((tt for tt in item.tautan if tt.sumber == "RUMUS"), key=lambda x: _urutan_rumus(x.rumus, item.id))
    for tt in rumus:
        rm = tt.rumus or ""
        metode, sasaran = SASARAN[rm]
        if item.metode != metode or tt.jenis_seri != sasaran:
            raise GalatMesin(f"Rumus {rm} hanya untuk seri {sasaran} metode {metode} (item {item.id}).")
        f = tt.faktor
        g = seri.get
        if rm == "TPK_X_KAMAR":
            seri["KUANTUM"] = _gabung(lambda a, b: a * b, g("TPK", {}), g("KAMAR", {}))
        elif rm == "JANGKAR_X_IH_100":
            h = par.get("H_TD") or 0.0
            seri["HARGA"] = _gabung(lambda x, h=h: h * x / 100, g("IH", {}))
        elif rm == "KAPITA_X_PENDUDUK_X_3":
            seri["OUT_ADHB"] = _gabung(lambda a, b, f=f: a * b * 3 / 1e6 * f, g("NILAI_KAPITA", {}), g("PENDUDUK", {}))
        elif rm == "MARGIN_X_OUTPUT":
            hs = benc(urai(tt.lapus_sumber))
            bcp, bk = jumlah(hs, "OUT_CP", n), jumlah(hs, "OUT_K", n)
            r = g("R_MARGIN", {})
            rb = _r_td(r, bcp, sb, par.get("R_MARGIN_TD"), konfig)
            ada = [u for u in sorted(r) if sb.awal <= u <= sb.akhir]
            seri["OUT_ADHB"] = {u: r[u] * bcp[sb.i(u)] * f for u in ada}
            out_k = {u: rb * bk[sb.i(u)] * f for u in ada}
        elif rm == "MARGIN_X_IMPOR":
            r, vi, ih = g("R_MARGIN", {}), g("V_IMPOR", {}), g("IH", {})
            kurs = seri.get("KURS")  # tidak ada seri KURS = kurs 1
            bcp = [v(vi, u) * (v(kurs, u) if kurs is not None else 1.0) for u in sb.periode]
            ih_td = par.get("IH_TD")
            if ih_td is not None:
                ih_bar = ih_td
            else:
                ih_bar = rata_isi(ih, konfig.t0) if konfig.jangkar_dari_data else 0.0
            bk = [bagi(bcp[t], v(ih, u)) * ih_bar for t, u in enumerate(sb.periode)]
            rb = _r_td(r, bcp, sb, par.get("R_MARGIN_TD"), konfig)
            komponen = [r, vi] + ([kurs] if kurs is not None else [])
            ada = sorted(u for u in set().union(*(s.keys() for s in komponen)) if sb.awal <= u <= sb.akhir)
            seri["OUT_ADHB"] = {u: v(r, u) * bcp[sb.i(u)] * f for u in ada}
            out_k = {u: rb * bk[sb.i(u)] * f for u in ada}
    seri = {k: potong_masa(s, m0, m1) or {} for k, s in seri.items()}
    return ItemSiap(item.id, item.metode, item.jenis_indeks, seri, par, potong_masa(out_k, m0, m1))


def _urutan_rumus(rumus: str | None, item_id: int) -> int:
    if rumus not in RUMUS_BAKU:
        raise GalatMesin(f"Rumus turunan item {item_id} tidak ada di daftar baku.")
    return RUMUS_BAKU.index(rumus)


def sumber_tautan(item: Item) -> list[int]:
    """Lapus sumber yang harus dihitung (sampai BENC) sebelum item ini."""
    return [x for tt in item.tautan for x in tt.lapus_sumber
            if tt.sumber == "HASIL_LAPUS" or tt.rumus == "MARGIN_X_OUTPUT"]
