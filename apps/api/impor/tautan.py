"""Tata bahasa kolom "Tautan / Rumus" templat (docs/05 §2) <-> lk.tautan_seri. Modul murni.

Bentuk yang dikenali (huruf besar/kecil bebas; faktor opsional "faktor 0,8865" atau persen "88,65%"):

    REF: REF_UPAH                                  -> SERI_REFERENSI pada seri baris ini
    RUMUS: HARGA = harga dasar 2010 (jangkar) x IH / 100   -> RUMUS baku menurut seri sasaran (atau kode baku)
    MARGIN: output barang lapus A.1.a[, A.1.b]     -> RUMUS MARGIN_X_OUTPUT pada OUT_ADHB (baris R_MARGIN/OUT_ADHB)
    MARGIN: nilai impor                            -> RUMUS MARGIN_X_IMPOR pada OUT_ADHB
    HASIL: OUT_CP lapus A.1.a, A.1.b               -> HASIL_LAPUS pada seri baris ini
    Dihitung sistem: ...                           -> baris hasil hitung (nilai tidak diimpor; tautan dari baris MARGIN)
    Ikut IH item C201 / Harga mengikuti item Sapi  -> "ikut item lain": diubah menjadi seri referensi (keputusan 5)

Teks lain = keterangan biasa (nilai baris tetap diimpor).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

RUMUS_BAKU = ("TPK_X_KAMAR", "JANGKAR_X_IH_100", "KAPITA_X_PENDUDUK_X_3", "MARGIN_X_OUTPUT", "MARGIN_X_IMPOR")
# rumus -> (metode, seri sasaran); sama dengan engine/turunan.py SASARAN
SASARAN = {
    "TPK_X_KAMAR": ("REV", "KUANTUM"),
    "JANGKAR_X_IH_100": ("REV", "HARGA"),
    "KAPITA_X_PENDUDUK_X_3": ("DEF", "OUT_ADHB"),
    "MARGIN_X_OUTPUT": ("DEF", "OUT_ADHB"),
    "MARGIN_X_IMPOR": ("DEF", "OUT_ADHB"),
}
KOMPONEN_RUMUS = {
    "TPK_X_KAMAR": ("TPK", "KAMAR"),
    "JANGKAR_X_IH_100": ("IH",),
    "KAPITA_X_PENDUDUK_X_3": ("NILAI_KAPITA", "PENDUDUK"),
    "MARGIN_X_OUTPUT": ("R_MARGIN",),
    "MARGIN_X_IMPOR": ("R_MARGIN", "V_IMPOR"),
}
BESARAN = ("OUT_CP", "OUT_K", "GVA_CP", "GVA_K", "IMPLISIT_OUT")
TEKS_RUMUS = {
    "TPK_X_KAMAR": "RUMUS: KUANTUM = TPK (persen) x KAMAR",
    "JANGKAR_X_IH_100": "RUMUS: HARGA = harga dasar (jangkar) x IH / 100",
    "KAPITA_X_PENDUDUK_X_3": "RUMUS: OUTPUT = per kapita x penduduk x 3 bulan / 1 juta",
}
TEKS_HITUNG_SISTEM = "Dihitung sistem: rasio margin x output barang"

RX_KODE_LAPUS = re.compile(r"[A-Z][A-Za-z0-9]*(?:\.[A-Za-z0-9]+)*")
RX_FAKTOR = re.compile(r"faktor\s*=?\s*(-?\d+(?:[.,]\d+)?)", re.I)
RX_PERSEN = re.compile(r"(\d+(?:[.,]\d+)?)\s*%")
RX_IKUT_KODE = re.compile(r"^ikut\s+([A-Za-z_]+)\s+item\s+(\S+)\s*$", re.I)
RX_MENGIKUTI = re.compile(r"^([A-Za-z_]+)\s+mengikuti\s+item\s+(.+?)\s*$", re.I)


class GalatTautan(ValueError):
    """Teks tautan tidak dapat dipahami (pesan untuk pengguna)."""


@dataclass(frozen=True)
class TautanTeks:
    jenis: str  # REF | RUMUS | MARGIN | HASIL | HITUNG_SISTEM | IKUT | KETERANGAN
    seri_ref: str | None = None
    rumus: str | None = None
    lapus: tuple[str, ...] = ()
    besaran: str | None = None
    faktor: float = 1.0
    ikut_seri: str | None = None
    ikut_kode: str | None = None  # kode item, mis. C201 (lapus tanpa titik + nomor 2 digit)
    ikut_nama: str | None = None  # nama item pada lapus yang sama

    @property
    def nilai_diabaikan(self) -> bool:
        """Nilai baris ini tidak diimpor (seri tertaut/rumus menggantikan isian manual)."""
        return self.jenis in ("REF", "RUMUS", "HASIL", "HITUNG_SISTEM", "IKUT")


def angka(teks: str) -> float:
    """Angka dari teks templat: koma atau titik desimal, tanpa pemisah ribuan."""
    try:
        return float(Decimal(teks.replace(",", ".")))
    except InvalidOperation as e:
        raise GalatTautan(f"Faktor '{teks}' bukan angka.") from e


def _faktor(teks: str) -> float:
    m = RX_FAKTOR.search(teks)
    if m:
        return angka(m.group(1))
    m = RX_PERSEN.search(teks)
    if m:
        return float(Decimal(m.group(1).replace(",", ".")) / 100)
    return 1.0


def _lapus(teks: str) -> tuple[str, ...]:
    m = re.search(r"\blapus\b(.*)$", teks, re.I)
    if not m:
        return ()
    isi = RX_FAKTOR.sub("", m.group(1))
    return tuple(RX_KODE_LAPUS.findall(isi))


def urai(teks: str | None, seri: str, metode: str) -> TautanTeks | None:
    """Teks kolom Tautan / Rumus satu baris -> struktur. None bila kosong. GalatTautan bila tidak dikenali."""
    t = (teks or "").strip()
    if not t:
        return None
    low = t.lower()
    if low.startswith("ref:"):
        isi = t[4:].strip()
        m = re.match(r"([A-Za-z0-9_.\-]+)", isi)
        if not m:
            raise GalatTautan("Kode seri referensi setelah 'REF:' kosong.")
        return TautanTeks("REF", seri_ref=m.group(1), faktor=_faktor(isi[m.end():]))
    if low.startswith("rumus:"):
        atas = t.upper()
        kode = next((r for r in RUMUS_BAKU if r in atas), None)
        if kode is None:
            if metode == "REV" and seri == "KUANTUM":
                kode = "TPK_X_KAMAR"
            elif metode == "REV" and seri == "HARGA":
                kode = "JANGKAR_X_IH_100"
            elif metode == "DEF" and seri == "OUT_ADHB" and "kapita" in low:
                kode = "KAPITA_X_PENDUDUK_X_3"
            else:
                raise GalatTautan(f"Rumus untuk seri {seri} metode {metode} tidak ada di daftar baku.")
        if kode in ("MARGIN_X_OUTPUT", "MARGIN_X_IMPOR"):
            return TautanTeks("MARGIN", rumus=kode, lapus=_lapus(t), faktor=_faktor(t))
        return TautanTeks("RUMUS", rumus=kode, faktor=_faktor(t))
    if low.startswith("margin:"):
        if "impor" in low:
            return TautanTeks("MARGIN", rumus="MARGIN_X_IMPOR", faktor=_faktor(t))
        lap = _lapus(t)
        if not lap:
            raise GalatTautan("Tautan MARGIN harus menyebut lapus barang, mis. 'MARGIN: output barang lapus A.1.a'.")
        return TautanTeks("MARGIN", rumus="MARGIN_X_OUTPUT", lapus=lap, faktor=_faktor(t))
    if low.startswith("hasil:"):
        isi = t[6:].strip()
        m = re.match(r"([A-Za-z_]+)", isi)
        besaran = m.group(1).upper() if m else ""
        if besaran not in BESARAN:
            raise GalatTautan(f"Besaran HASIL harus salah satu dari {', '.join(BESARAN)}.")
        lap = _lapus(isi)
        if not lap:
            raise GalatTautan("Tautan HASIL harus menyebut lapus sumber, mis. 'HASIL: OUT_CP lapus A.1.a'.")
        return TautanTeks("HASIL", besaran=besaran, lapus=lap, faktor=_faktor(isi))
    if low.startswith("dihitung sistem"):
        return TautanTeks("HITUNG_SISTEM")
    m = RX_IKUT_KODE.match(t)
    if m:
        return TautanTeks("IKUT", ikut_seri=m.group(1).upper(), ikut_kode=m.group(2).upper())
    m = RX_MENGIKUTI.match(t)
    if m:
        return TautanTeks("IKUT", ikut_seri=m.group(1).upper(), ikut_nama=m.group(2).strip())
    return TautanTeks("KETERANGAN")


def _f(x: float) -> str:
    return format(x, ".15g")


def _sufiks_faktor(f: float) -> str:
    return "" if f == 1 else f" faktor {_f(f)}"


def teks_kanonik(sumber: str, rumus: str | None, seri_ref: str | None, lapus: tuple[str, ...],
                 besaran: str | None, faktor: float) -> str:
    """Teks bawaan ekspor untuk satu tautan pada baris seri sasarannya."""
    if sumber == "SERI_REFERENSI":
        return f"REF: {seri_ref}{_sufiks_faktor(faktor)}"
    if sumber == "HASIL_LAPUS":
        return f"HASIL: {besaran} lapus {', '.join(lapus)}{_sufiks_faktor(faktor)}"
    if rumus == "MARGIN_X_OUTPUT":
        return f"MARGIN: output barang lapus {', '.join(lapus)}{_sufiks_faktor(faktor)}"
    if rumus == "MARGIN_X_IMPOR":
        return f"MARGIN: nilai impor{_sufiks_faktor(faktor)}"
    return TEKS_RUMUS[rumus or ""] + _sufiks_faktor(faktor)


def setara(t: TautanTeks | None, sumber: str, rumus: str | None, seri_ref: str | None, lapus: tuple[str, ...],
           besaran: str | None, faktor: float) -> bool:
    """Apakah teks tersimpan masih menggambarkan tautan yang sama (agar ekspor memakai teks asli)."""
    if t is None:
        return False
    if sumber == "SERI_REFERENSI":
        return t.jenis == "REF" and t.seri_ref == seri_ref and t.faktor == faktor
    if sumber == "HASIL_LAPUS":
        return t.jenis == "HASIL" and t.besaran == besaran and t.lapus == lapus and t.faktor == faktor
    if rumus in ("MARGIN_X_OUTPUT", "MARGIN_X_IMPOR"):
        return t.jenis == "MARGIN" and t.rumus == rumus and t.lapus == lapus and t.faktor == faktor
    return t.jenis == "RUMUS" and t.rumus == rumus and t.faktor == faktor
