"""Pembaca templat data dasar (docs/05) -> struktur berkas netral + pesan format. Modul murni (tanpa DB).

Aturan baca (sama dengan pembaca rujukan tools/baca_templat.py):
- Sheet kategori = sheet bernama satu huruf A..V (lapus harus anak kategori sheet itu); sheet TOP_SOP untuk item
  pajak/subsidi atas produk (keputusan 1). Judul kolom di baris 4; data mulai baris 5.
- Satu item = (Kode Wilayah, Kode Lapus, Metode, No Item); satu baris = satu seri item.
- Kolom periode berlabel 'YYYY-Tq'. Sel kosong = tidak tersedia (BUKAN 0) dan tidak menghapus nilai di sistem.
- Kolom Jangkar Tahun Dasar: baris RKA -> RKA_TD, HARGA -> H_TD, IH -> IH_TD, R_MARGIN -> R_MARGIN_TD.
- Kolom Tautan / Rumus: lihat impor/tautan.py. Nilai baris rumus/tautan tidak diimpor.
- SERI_REFERENSI dan PENYESUAIAN (opsional). Sheet lain diabaikan (informasi).

Pesan tidak memuat angka sel (hanya sheet, baris, kolom, dan teks pendek).
"""
from __future__ import annotations

import io
import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import openpyxl
from openpyxl.utils import get_column_letter

from . import tautan as tt

RX_PERIODE = re.compile(r"^(\d{4})-T([1-4])$")
RX_SHEET = re.compile(r"^[A-V]$")
SHEET_TOP_SOP = "TOP_SOP"
KOLOM_KUNCI = ("Kode Wilayah", "Kode Lapus", "Metode", "No Item", "Komoditas / Rincian", "Kode Seri")
KOLOM_PADANAN = ("Kode LK BPS", "Lapus TD2025 (konkordansi)", "Lapus TD2010 (konkordansi)", "Lapus padanan")
JANGKAR = {"RKA": "RKA_TD", "HARGA": "H_TD", "IH": "IH_TD", "R_MARGIN": "R_MARGIN_TD"}
METODE = ("REV", "EKS", "DEF", "PDK")

Kunci = tuple[str, str, str, int]  # wilayah, lapus, metode, nomor


def urut(tahun: int, triwulan: int) -> int:
    return tahun * 4 + triwulan - 1


def label_periode(u: int) -> str:
    return f"{u // 4}-T{u % 4 + 1}"


def urut_label(teks: str) -> int | None:
    m = RX_PERIODE.match(teks.strip())
    return urut(int(m.group(1)), int(m.group(2))) if m else None


@dataclass
class Pesan:
    tingkat: str  # galat | peringatan | info
    teks: str
    sheet: str | None = None
    baris: int | None = None
    kolom: str | None = None
    kode: str | None = None  # kode validasi terkait (V02, V16, ...)

    def ke_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items() if v is not None}


@dataclass
class InfoLapus:
    kode: str
    jenis: str
    kategori: str | None  # kode akar pohon (sheet templat); TOP/SOP = None


@dataclass
class KonteksTemplat:
    """Master yang dibutuhkan pembaca (dari DB atau uji)."""

    wilayah: set[str]
    lapus: dict[str, InfoLapus]
    seri_metode: dict[str, list[str]]  # metode -> kode seri (urut ref.jenis_seri)
    wajib: dict[str, set[str]]
    maks_item: dict[str, int]
    jenis_penyesuaian: dict[str, tuple[str, bool]]  # kode -> (tahap, wajib_alasan)


@dataclass
class SeriBerkas:
    kode: str
    urutan: int
    baris: int
    satuan: str | None = None
    label: str | None = None
    catatan: str | None = None
    lokasi: str | None = None
    teks_tautan: str | None = None
    tautan: tt.TautanTeks | None = None
    jangkar: float | None = None
    nilai: dict[int, float] = field(default_factory=dict)


@dataclass
class ItemBerkas:
    kunci: Kunci
    sheet: str
    baris: int
    nama: str
    jenis_indeks: str | None = None
    sumber: str | None = None
    padanan: str | None = None
    seri: dict[str, SeriBerkas] = field(default_factory=dict)

    @property
    def wilayah(self) -> str:
        return self.kunci[0]

    @property
    def lapus(self) -> str:
        return self.kunci[1]

    @property
    def metode(self) -> str:
        return self.kunci[2]

    @property
    def nomor(self) -> int:
        return self.kunci[3]


@dataclass
class SeriRefBerkas:
    wilayah: str
    kode: str
    baris: int
    nama: str | None = None
    satuan: str | None = None
    dipakai: str | None = None
    sumber: str | None = None
    catatan: str | None = None
    lokasi: str | None = None
    nilai: dict[int, float] = field(default_factory=dict)


@dataclass
class PenyesuaianBerkas:
    wilayah: str
    lapus: str
    tahap: str
    metode: str | None
    jenis: str
    harga: str
    alasan: str | None
    baris: int
    catatan: str | None = None
    lokasi: str | None = None
    nilai: dict[int, float] = field(default_factory=dict)


@dataclass
class Berkas:
    items: dict[Kunci, ItemBerkas] = field(default_factory=dict)
    seri_ref: list[SeriRefBerkas] = field(default_factory=list)
    penyesuaian: list[PenyesuaianBerkas] = field(default_factory=list)
    pesan: list[Pesan] = field(default_factory=list)
    periode: list[int] = field(default_factory=list)  # kolom periode yang ada di berkas
    sheet_kategori: list[str] = field(default_factory=list)

    @property
    def galat(self) -> list[Pesan]:
        return [p for p in self.pesan if p.tingkat == "galat"]

    def jumlah_angka(self) -> int:
        n = sum(len(s.nilai) for it in self.items.values() for s in it.seri.values())
        return n + sum(len(r.nilai) for r in self.seri_ref) + sum(len(a.nilai) for a in self.penyesuaian)


# ------------------------------------------------------------------ bantu sel
def teks(x: Any) -> str | None:
    if x is None:
        return None
    if isinstance(x, float) and x.is_integer():
        x = int(x)
    s = re.sub(r"\s+", " ", str(x)).strip()
    return s or None


def adalah_angka(x: Any) -> bool:
    return isinstance(x, int | float) and not isinstance(x, bool)


RX_MIKRO = (re.compile(r"\b(NIB|KIP)\b\s*[:=]?\s*\d", re.I), re.compile(r"(?<!\d)\d{13}(?!\d)"))
RX_BADAN_USAHA = re.compile(r"^(PT|CV|UD|PD|Koperasi)\.?\s|\bTbk\b", re.I)


def curiga_mikro(nama: str | None, lain: Iterable[str | None]) -> bool:
    """Heuristik data mikro perusahaan (nama badan usaha, NIB, KIP) — baris ditolak di impor (CLAUDE.md §8)."""
    if nama and RX_BADAN_USAHA.search(nama):
        return True
    return any(rx.search(t) for t in [nama, *lain] if t for rx in RX_MIKRO)


def _nomor(x: Any) -> int | None:
    if isinstance(x, bool):
        return None
    if isinstance(x, int):
        return x
    if isinstance(x, float) and x.is_integer():
        return int(x)
    if isinstance(x, str) and x.strip().isdigit():
        return int(x.strip())
    return None


def _wilayah(x: Any) -> str | None:
    if adalah_angka(x) and float(x).is_integer():
        return str(int(x))
    return teks(x)


class _Pembaca:
    def __init__(self, konteks: KonteksTemplat):
        self.k = konteks
        self.b = Berkas()

    def pesan(self, tingkat: str, isi: str, sheet: str | None = None, baris: int | None = None,
              kolom: str | None = None, kode: str | None = None) -> None:
        self.b.pesan.append(Pesan(tingkat, isi, sheet, baris, kolom, kode))

    def kepala(self, ws: Any, sheet: str) -> tuple[dict[str, int], dict[int, int], Iterable] | None:
        rows = ws.iter_rows(min_row=4, values_only=True)
        try:
            hd = list(next(rows))
        except StopIteration:
            return None
        col: dict[str, int] = {}
        per: dict[int, int] = {}
        for i, h in enumerate(hd):
            if isinstance(h, str) and h.strip():
                u = urut_label(h)
                if u is not None:
                    per[i] = u
                else:
                    col.setdefault(h.strip(), i)
        return col, per, rows

    def nilai_periode(self, r: tuple, per: dict[int, int], sheet: str, n: int) -> tuple[dict[int, float], bool]:
        """Angka per periode; teks/boolean di kolom angka = galat sel. Kembalikan (nilai, ada_galat)."""
        out: dict[int, float] = {}
        galat = False
        for i, u in per.items():
            x = r[i] if i < len(r) else None
            if x is None or (isinstance(x, str) and not x.strip()):
                continue
            if adalah_angka(x):
                out[u] = float(x)
            else:
                galat = True
                self.pesan("galat", "Isi bukan angka (kosongkan bila tidak tersedia).", sheet, n,
                           get_column_letter(i + 1))
        return out, galat

    # -------------------------------------------------------------- sheet kategori
    def sheet_item(self, ws: Any, sheet: str) -> None:
        kp = self.kepala(ws, sheet)
        if kp is None:
            return
        col, per, rows = kp
        kurang = [k for k in KOLOM_KUNCI if k not in col]
        if kurang:
            self.pesan("galat", f"Kolom wajib tidak ada: {', '.join(kurang)}.", sheet, 4)
            return
        self.b.periode = sorted(set(self.b.periode) | set(per.values()))
        self.b.sheet_kategori.append(sheet)
        c_pad = next((col[k] for k in KOLOM_PADANAN if k in col), None)

        def g(r: tuple, h: str) -> Any:
            i = col.get(h)
            return r[i] if i is not None and i < len(r) else None

        for n, r in enumerate(rows, start=5):
            if not r or all(x is None or (isinstance(x, str) and not x.strip()) for x in r):
                continue
            wil, lap, met = _wilayah(g(r, "Kode Wilayah")), teks(g(r, "Kode Lapus")), teks(g(r, "Metode"))
            seri = teks(g(r, "Kode Seri"))
            if not wil and not lap and not seri:
                continue  # baris keterangan/kosong
            nama = teks(g(r, "Komoditas / Rincian"))
            lain = [teks(g(r, h)) for h in ("Sumber Data", "Catatan", "Lokasi Sumber", "Seri")]
            if curiga_mikro(nama, lain):
                self.pesan("galat", "Diduga data mikro perusahaan (nama badan usaha/NIB/KIP); baris ditolak.",
                           sheet, n)
                continue
            nomor = _nomor(g(r, "No Item"))
            met = (met or "").upper()
            if wil not in self.k.wilayah:
                self.pesan("galat", "Kode wilayah tidak dikenal.", sheet, n, "Kode Wilayah")
                continue
            info = self.k.lapus.get(lap or "")
            if info is None or info.jenis not in ("daun", "top", "sop"):
                self.pesan("galat", f"Kode lapus '{lap}' bukan lapus berdata pada tahun dasar ini.", sheet, n,
                           "Kode Lapus")
                continue
            if (sheet == SHEET_TOP_SOP) != (info.jenis in ("top", "sop")) or (
                    sheet != SHEET_TOP_SOP and info.kategori != sheet):
                self.pesan("galat", f"Lapus {lap} bukan bagian sheet {sheet}.", sheet, n, "Kode Lapus")
                continue
            if met not in METODE:
                self.pesan("galat", "Metode harus REV, EKS, DEF, atau PDK.", sheet, n, "Metode")
                continue
            if nomor is None or not 1 <= nomor <= self.k.maks_item.get(met, 200):
                self.pesan("galat", f"No Item harus bilangan bulat 1-{self.k.maks_item.get(met, 200)} untuk {met}.",
                           sheet, n, "No Item")
                continue
            if not nama:
                self.pesan("galat", "Komoditas / Rincian wajib diisi.", sheet, n, "Komoditas / Rincian")
                continue
            seri = (seri or "").upper()
            if seri not in self.k.seri_metode.get(met, []):
                self.pesan("galat", f"Seri {seri or '(kosong)'} tidak berlaku untuk metode {met}.", sheet, n,
                           "Kode Seri")
                continue
            kunci: Kunci = (wil, lap or "", met, nomor)
            it = self.b.items.get(kunci)
            if it is None:
                it = self.b.items[kunci] = ItemBerkas(kunci, sheet, n, nama)
            elif it.nama.lower() != nama.lower():
                self.pesan("galat", "Nama komoditas berbeda dalam satu item (Kode Wilayah + Lapus + Metode + No).",
                           sheet, n, "Komoditas / Rincian")
                continue
            if seri in it.seri:
                self.pesan("galat", f"Seri {seri} muncul dua kali pada item yang sama.", sheet, n, "Kode Seri")
                continue
            ji = teks(g(r, "Jenis Indeks (EKS)"))
            if ji:
                if ji.upper() not in ("IP", "IB"):
                    self.pesan("galat", "Jenis Indeks harus IP atau IB.", sheet, n, "Jenis Indeks (EKS)")
                elif met != "EKS":
                    self.pesan("peringatan", "Jenis Indeks hanya untuk EKS; diabaikan.", sheet, n,
                               "Jenis Indeks (EKS)")
                else:
                    it.jenis_indeks = ji.upper()
            it.sumber = it.sumber or teks(g(r, "Sumber Data"))
            if c_pad is not None and c_pad < len(r):
                it.padanan = it.padanan or teks(r[c_pad])
            teks_t = teks(g(r, "Tautan / Rumus"))
            try:
                taut = tt.urai(teks_t, seri, met)
            except tt.GalatTautan as e:
                self.pesan("galat", str(e), sheet, n, "Tautan / Rumus")
                continue
            jangkar = g(r, "Jangkar Tahun Dasar")
            j_val: float | None = None
            if jangkar is not None and not (isinstance(jangkar, str) and not jangkar.strip()):
                if not adalah_angka(jangkar):
                    self.pesan("galat", "Jangkar tahun dasar harus angka.", sheet, n, "Jangkar Tahun Dasar")
                    continue
                if seri not in JANGKAR:
                    self.pesan("galat", "Jangkar hanya untuk baris RKA, HARGA, IH, atau R_MARGIN.", sheet, n,
                               "Jangkar Tahun Dasar")
                    continue
                j_val = float(jangkar)
            nilai, galat = self.nilai_periode(r, per, sheet, n)
            if galat:
                continue
            s = SeriBerkas(seri, len(it.seri) + 1, n, teks(g(r, "Satuan")), teks(g(r, "Seri")),
                           teks(g(r, "Catatan")), teks(g(r, "Lokasi Sumber")), teks_t, taut, j_val, nilai)
            if taut is not None and taut.nilai_diabaikan:
                if nilai and taut.jenis in ("REF", "HASIL", "IKUT"):
                    self.pesan("info", "Angka pada baris tautan tidak diimpor (seri diambil dari sumber tautan).",
                               sheet, n)
                s.nilai = {}
            it.seri[seri] = s

    def periksa_item(self) -> None:
        for it in self.b.items.values():
            met, ada = it.metode, set(it.seri)
            margin = any(s.tautan is not None and s.tautan.jenis == "MARGIN" for s in it.seri.values())
            if margin and met != "DEF":
                self.pesan("galat", "Tautan MARGIN hanya untuk item DEF.", it.sheet, it.baris)
            turunan = {s.kode for s in it.seri.values() if s.tautan is not None and s.tautan.nilai_diabaikan}
            if margin:
                turunan.add("OUT_ADHB")
            kurang = self.k.wajib.get(met, set()) - ada - turunan
            if margin:
                kurang -= {"IH"}  # baris IH item margin barang tidak dipakai (keputusan 11)
            if kurang:
                self.pesan("peringatan", f"Seri wajib belum ada: {', '.join(sorted(kurang))}.", it.sheet, it.baris,
                           kode="V01")
            if met == "EKS" and it.jenis_indeks not in ("IP", "IB"):
                self.pesan("galat", "Item EKS wajib punya Jenis Indeks IP atau IB.", it.sheet, it.baris,
                           "Jenis Indeks (EKS)")
            rka = it.seri.get("RKA")
            if met in ("REV", "EKS") and rka is not None and rka.jangkar is None:
                self.pesan("info", "Jangkar RKA (rasio KA tahun dasar) kosong.", it.sheet, rka.baris,
                           "Jangkar Tahun Dasar", "V02")

    # -------------------------------------------------------------- SERI_REFERENSI
    def sheet_seri_ref(self, ws: Any) -> None:
        sheet = "SERI_REFERENSI"
        kp = self.kepala(ws, sheet)
        if kp is None:
            return
        col, per, rows = kp
        if "Kode Wilayah" not in col or "Kode Referensi" not in col:
            self.pesan("galat", "Kolom Kode Wilayah dan Kode Referensi wajib ada.", sheet, 4)
            return

        def g(r: tuple, h: str) -> Any:
            i = col.get(h)
            return r[i] if i is not None and i < len(r) else None

        dilihat: set[tuple[str, str]] = set()
        for n, r in enumerate(rows, start=5):
            if not r:
                continue
            wil, kode = _wilayah(g(r, "Kode Wilayah")), teks(g(r, "Kode Referensi"))
            if not kode:
                continue
            if wil not in self.k.wilayah:
                self.pesan("galat", "Kode wilayah tidak dikenal.", sheet, n, "Kode Wilayah")
                continue
            if not re.fullmatch(r"[A-Za-z0-9_.\-]+", kode):
                self.pesan("galat", "Kode referensi hanya boleh huruf, angka, titik, garis bawah.", sheet, n,
                           "Kode Referensi")
                continue
            if (wil, kode) in dilihat:
                self.pesan("galat", "Seri referensi yang sama muncul dua kali untuk wilayah ini.", sheet, n,
                           "Kode Referensi")
                continue
            dilihat.add((wil, kode))
            nilai, galat = self.nilai_periode(r, per, sheet, n)
            if galat:
                continue
            self.b.seri_ref.append(SeriRefBerkas(wil, kode, n, teks(g(r, "Nama")), teks(g(r, "Satuan")),
                                                 teks(g(r, "Dipakai Lapus")), teks(g(r, "Sumber")),
                                                 teks(g(r, "Catatan")), teks(g(r, "Lokasi Sumber")), nilai))

    # -------------------------------------------------------------- PENYESUAIAN
    def sheet_penyesuaian(self, ws: Any) -> None:
        sheet = "PENYESUAIAN"
        kp = self.kepala(ws, sheet)
        if kp is None:
            return
        col, per, rows = kp
        perlu = ("Kode Wilayah", "Kode Lapus", "Tahap", "Jenis", "Harga")
        if any(k not in col for k in perlu):
            self.pesan("galat", f"Kolom wajib tidak ada: {', '.join(k for k in perlu if k not in col)}.", sheet, 4)
            return

        def g(r: tuple, h: str) -> Any:
            i = col.get(h)
            return r[i] if i is not None and i < len(r) else None

        for n, r in enumerate(rows, start=5):
            if not r:
                continue
            wil, lap = _wilayah(g(r, "Kode Wilayah")), teks(g(r, "Kode Lapus"))
            jenis = (teks(g(r, "Jenis")) or "").upper()
            if not lap and not jenis:
                continue
            tahap = (teks(g(r, "Tahap")) or "").upper()
            met = (teks(g(r, "Metode")) or "").upper() or None
            harga = (teks(g(r, "Harga")) or "").upper()
            alasan = teks(g(r, "Alasan"))
            if wil not in self.k.wilayah:
                self.pesan("galat", "Kode wilayah tidak dikenal.", sheet, n, "Kode Wilayah")
                continue
            info = self.k.lapus.get(lap or "")
            if info is None or info.jenis not in ("daun", "top", "sop"):
                self.pesan("galat", f"Kode lapus '{lap}' bukan lapus berdata.", sheet, n, "Kode Lapus")
                continue
            if tahap not in ("METODE", "REKON"):
                self.pesan("galat", "Tahap harus METODE atau REKON (simulasi diinput di sistem).", sheet, n, "Tahap")
                continue
            jp = self.k.jenis_penyesuaian.get(jenis)
            if jp is None or jp[0] != tahap:
                self.pesan("galat", f"Jenis {jenis or '(kosong)'} tidak berlaku pada tahap {tahap}.", sheet, n,
                           "Jenis")
                continue
            if (tahap == "METODE") != (met is not None) or (met is not None and met not in ("REV", "EKS", "DEF")):
                self.pesan("galat", "Metode wajib (REV/EKS/DEF) untuk tahap METODE dan kosong untuk REKON.", sheet,
                           n, "Metode")
                continue
            if harga not in ("CP", "K"):
                self.pesan("galat", "Harga harus CP (berlaku) atau K (konstan).", sheet, n, "Harga")
                continue
            if jp[1] and len(alasan or "") < 10:
                self.pesan("galat", "Alasan penyesuaian wajib diisi (min. 10 karakter).", sheet, n, "Alasan")
                continue
            nilai, galat = self.nilai_periode(r, per, sheet, n)
            if galat:
                continue
            self.b.penyesuaian.append(PenyesuaianBerkas(wil or "", lap or "", tahap, met, jenis, harga, alasan, n,
                                                        teks(g(r, "Catatan")), teks(g(r, "Lokasi Sumber")), nilai))


def baca(sumber: bytes | str | Path, konteks: KonteksTemplat) -> Berkas:
    """Baca templat xlsx (bytes atau jalur). Berkas mentah tidak disimpan."""
    data = io.BytesIO(sumber) if isinstance(sumber, bytes) else str(sumber)
    try:
        wb = openpyxl.load_workbook(data, data_only=True, read_only=True)
    except Exception as e:  # noqa: BLE001 - berkas rusak/bukan xlsx
        p = _Pembaca(konteks)
        p.pesan("galat", f"Berkas tidak dapat dibaca sebagai xlsx ({type(e).__name__}).")
        return p.b
    p = _Pembaca(konteks)
    try:
        for nama in wb.sheetnames:
            if RX_SHEET.fullmatch(nama) or nama == SHEET_TOP_SOP:
                p.sheet_item(wb[nama], nama)
        if "SERI_REFERENSI" in wb.sheetnames:
            p.sheet_seri_ref(wb["SERI_REFERENSI"])
        if "PENYESUAIAN" in wb.sheetnames:
            p.sheet_penyesuaian(wb["PENYESUAIAN"])
    finally:
        wb.close()
    if not p.b.sheet_kategori and not p.b.seri_ref and "SERI_REFERENSI" not in wb.sheetnames:
        p.pesan("galat", "Tidak ada sheet kategori (A..V) atau SERI_REFERENSI di berkas ini.")
    p.periksa_item()
    return p.b
