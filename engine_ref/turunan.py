"""
Oracle rumus turunan dan tautan seri (docs/02 §7 dan §11), dalam gaya engine_ref: Series = dict t -> nilai.

Seri turunan diselesaikan sebelum hitung item (REV/EKS/DEF). Aturan kosong:
- Nilai turunan pada triwulan t KOSONG (tidak ada kunci) bila semua komponen seri item pada t kosong;
  bila sebagian terisi, komponen kosong = 0 (perilaku Excel).
- Hasil lapus lain (HASIL_LAPUS, basis margin) selalu dianggap terisi.

Keputusan 5 November 2026 (docs/02 §11):
- MARGIN_X_OUTPUT: basis = Σ output lapus barang tahap BENC (bukan FINAL). ADHB memakai rasio margin triwulan
  berjalan; ADHK = rasio margin tahun dasar × Σ output ADHK BENC lapus barang × faktor (arus barang).
- MARGIN_X_IMPOR: ADHB = R × V_IMPOR × KURS × faktor; ADHK = R_TD × (V_IMPOR × KURS ÷ IH × ĪH) × faktor.
- Rasio margin tahun dasar (R_TD): parameter R_MARGIN_TD; bila kosong dan jangkar_dari_data (TD2025)
  = Σ₍T₀₎ (R × basis ADHB) ÷ Σ₍T₀₎ basis ADHB; bila kosong dan TD2010 = 0 (V03).
- Output ADHK margin hanya ada pada triwulan yang output ADHB-nya ada (rasio margin terisi).
"""
from __future__ import annotations

from typing import Callable, List, Optional

from engine_ref.lk_engine import NQ, Series, avg_nonblank, div, v

KODE_RUMUS = ("TPK_X_KAMAR", "JANGKAR_X_IH_100", "KAPITA_X_PENDUDUK_X_3", "MARGIN_X_OUTPUT", "MARGIN_X_IMPOR")
BESARAN = ("OUT_CP", "OUT_K", "GVA_CP", "GVA_K", "IMPLISIT_OUT")


def _num(x) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def _gabung(fn: Callable[..., float], *seri: Series) -> Series:
    """Nilai turunan per t; kosong bila semua komponen kosong pada t."""
    ts = sorted(set().union(*(s.keys() for s in seri if s)))
    return {t: fn(*(v(s, t) for s in seri)) for t in ts if any(_num((s or {}).get(t)) for s in seri)}


def tpk_x_kamar(tpk: Series, kamar: Series) -> Series:
    """KUANTUM = TPK (persen) × KAMAR (sama dengan LK TD2025: 35,99 × 375 = 13.496,25)."""
    return _gabung(lambda a, b: a * b, tpk, kamar)


def jangkar_x_ih_100(h_td: Optional[float], ih: Series) -> Series:
    """HARGA = H_TD × IH ÷ 100 (TD2010 hortikultura). H_TD kosong = 0."""
    h = h_td if _num(h_td) else 0.0
    return _gabung(lambda x: h * x / 100, ih)


def kapita_x_penduduk_x_3(kapita: Series, penduduk: Series, faktor: float = 1.0) -> Series:
    """OUT_ADHB = per kapita × penduduk × 3 ÷ 10⁶ × faktor (TD2010 I.1 sewa, I.2 makan minum)."""
    return _gabung(lambda a, b: a * b * 3 / 1e6 * faktor, kapita, penduduk)


def seri_referensi(ref: Series, faktor: float = 1.0) -> Series:
    """Seri diambil dari lk.nilai_seri_referensi (satu seri untuk banyak item) × faktor."""
    return {t: float(x) * faktor for t, x in (ref or {}).items() if _num(x)}


def jumlah_hasil(hasil: List[object], besaran: str) -> List[float]:
    """Σ besaran (OUT_CP/OUT_K/GVA_CP/GVA_K) beberapa Hasil; IMPLISIT_OUT = ΣOUT_CP ÷ ΣOUT_K × 100."""
    if besaran == "IMPLISIT_OUT":
        cp, k = jumlah_hasil(hasil, "OUT_CP"), jumlah_hasil(hasil, "OUT_K")
        return [div(cp[t], k[t]) * 100 for t in range(NQ)]
    atr = besaran.lower()
    out = [0.0] * NQ
    for h in hasil:
        s = getattr(h, atr)
        for t in range(NQ):
            out[t] += s[t]
    return out


def hasil_lapus(hasil: List[object], besaran: str, faktor: float = 1.0) -> Series:
    """Seri = Σ hasil lapus lain tahap BENC (besaran) × faktor. Selalu terisi."""
    s = jumlah_hasil(hasil, besaran)
    return {t: s[t] * faktor for t in range(NQ)}


def _r_td(r: Series, basis_cp: List[float], r_td: Optional[float], t_base: List[int],
          jangkar_dari_data: bool) -> float:
    if _num(r_td):
        return float(r_td)
    if not jangkar_dari_data:
        return 0.0
    return div(sum(v(r, t) * basis_cp[t] for t in t_base), sum(basis_cp[t] for t in t_base))


def margin_x_output(r: Series, basis_cp: List[float], basis_k: List[float], faktor: float,
                    r_td: Optional[float], t_base: List[int], jangkar_dari_data: bool):
    """(OUT_ADHB, OUT_ADHK) margin perdagangan atas barang; basis = Σ output BENC lapus barang."""
    rb = _r_td(r, basis_cp, r_td, t_base, jangkar_dari_data)
    out_cp = {t: v(r, t) * basis_cp[t] * faktor for t in sorted(r) if _num(r.get(t))}
    out_k = {t: rb * basis_k[t] * faktor for t in out_cp}
    return out_cp, out_k


def margin_x_impor(r: Series, v_impor: Series, kurs: Optional[Series], ih: Series, ih_td: Optional[float],
                   faktor: float, r_td: Optional[float], t_base: List[int], jangkar_dari_data: bool):
    """(OUT_ADHB, OUT_ADHK) margin perdagangan barang impor. kurs None = item tanpa seri KURS (kurs 1)."""
    komponen = [r, v_impor] + ([kurs] if kurs is not None else [])
    basis_cp = [v(v_impor, t) * (v(kurs, t) if kurs is not None else 1.0) for t in range(NQ)]
    if _num(ih_td):
        ih_bar = float(ih_td)
    else:
        ih_bar = avg_nonblank(ih, t_base) if jangkar_dari_data else 0.0
    basis_k = [div(basis_cp[t], v(ih, t)) * ih_bar for t in range(NQ)]
    rb = _r_td(r, basis_cp, r_td, t_base, jangkar_dari_data)
    ts = sorted(set().union(*(s.keys() for s in komponen if s)))
    ada = [t for t in ts if any(_num((s or {}).get(t)) for s in komponen)]
    out_cp = {t: v(r, t) * basis_cp[t] * faktor for t in ada}
    out_k = {t: rb * basis_k[t] * faktor for t in ada}
    return out_cp, out_k


def potong_masa(s: Optional[Series], mulai: Optional[int], selesai: Optional[int]) -> Optional[Series]:
    """Nilai di luar masa berlaku item dianggap tidak ada (keputusan F2)."""
    if s is None:
        return None
    return {t: x for t, x in s.items()
            if (mulai is None or t >= mulai) and (selesai is None or t <= selesai)}
