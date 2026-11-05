"""CSV bentuk panjang (docs/05 §3.8) -> struktur Berkas yang sama dengan templat. Modul murni.

Kolom data dasar: tahun_dasar, kode_wilayah, kode_lapus, metode, no_item, komoditas, kode_seri, satuan, jangkar,
periode, nilai, sumber, catatan. Satu baris = satu nilai (atau baris tanpa periode yang hanya membawa jangkar).
Kolom seri referensi: kode_wilayah, kode_referensi, nama, satuan, periode, nilai.
Pemisah ',' atau ';' (dikenali otomatis); desimal titik (koma diterima bila pemisah ';'). CSV tidak membawa tautan.
"""
from __future__ import annotations

import csv
import io
from decimal import Decimal, InvalidOperation

from .templat import (
    JANGKAR,
    METODE,
    Berkas,
    ItemBerkas,
    KonteksTemplat,
    Pesan,
    SeriBerkas,
    SeriRefBerkas,
    curiga_mikro,
    teks,
    urut_label,
)

KOLOM_DATA = ("tahun_dasar", "kode_wilayah", "kode_lapus", "metode", "no_item", "komoditas", "kode_seri", "satuan",
              "jangkar", "periode", "nilai", "sumber", "catatan")
KOLOM_REF = ("kode_wilayah", "kode_referensi", "nama", "satuan", "periode", "nilai")


def _baris(data: bytes) -> tuple[list[dict[str, str]], str] | None:
    try:
        isi = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return None
    contoh = isi.splitlines()[0] if isi else ""
    pemisah = ";" if contoh.count(";") > contoh.count(",") else ","
    rd = csv.DictReader(io.StringIO(isi), delimiter=pemisah)
    rows = [{(k or "").strip().lower(): (v or "").strip() for k, v in r.items()} for r in rd]
    return rows, pemisah


def _angka(s: str, pemisah: str) -> float | None:
    if pemisah == ";":
        s = s.replace(".", "").replace(",", ".") if "," in s else s
    try:
        return float(Decimal(s))
    except InvalidOperation:
        return None


def jenis_csv(data: bytes) -> str | None:
    """'csv_panjang' atau 'seri_referensi' menurut kolom kepala; None bila tidak dikenali."""
    b = _baris(data)
    if b is None:
        return None
    kepala = data.decode("utf-8-sig", errors="ignore").splitlines()[0].lower() if data else ""
    if "kode_referensi" in kepala:
        return "seri_referensi"
    if "kode_seri" in kepala:
        return "csv_panjang"
    return None


def baca(data: bytes, konteks: KonteksTemplat, kode_td: str) -> Berkas:
    b = Berkas()
    hasil = _baris(data)
    if hasil is None:
        b.pesan.append(Pesan("galat", "Berkas CSV harus UTF-8."))
        return b
    rows, pemisah = hasil
    sheet = "CSV"
    if not rows:
        b.pesan.append(Pesan("galat", "CSV kosong."))
        return b
    if "kode_referensi" in rows[0]:
        return _baca_ref(rows, pemisah, konteks, b)
    kurang = [k for k in KOLOM_DATA if k not in rows[0]]
    if kurang:
        b.pesan.append(Pesan("galat", f"Kolom wajib tidak ada: {', '.join(kurang)}.", sheet, 1))
        return b
    per: set[int] = set()
    for n, r in enumerate(rows, start=2):
        if r["tahun_dasar"].upper() != kode_td.upper():
            b.pesan.append(Pesan("galat", f"Tahun dasar harus {kode_td}.", sheet, n, "tahun_dasar"))
            continue
        wil, lap, met = r["kode_wilayah"], r["kode_lapus"], r["metode"].upper()
        seri, nama = r["kode_seri"].upper(), teks(r["komoditas"]) or ""
        if curiga_mikro(nama, [r.get("sumber"), r.get("catatan")]):
            b.pesan.append(Pesan("galat", "Diduga data mikro perusahaan; baris ditolak.", sheet, n))
            continue
        info = konteks.lapus.get(lap)
        if wil not in konteks.wilayah:
            b.pesan.append(Pesan("galat", "Kode wilayah tidak dikenal.", sheet, n, "kode_wilayah"))
            continue
        if info is None or info.jenis not in ("daun", "top", "sop"):
            b.pesan.append(Pesan("galat", f"Kode lapus '{lap}' bukan lapus berdata.", sheet, n, "kode_lapus"))
            continue
        if met not in METODE or seri not in konteks.seri_metode.get(met, []):
            b.pesan.append(Pesan("galat", f"Seri {seri} tidak berlaku untuk metode {met}.", sheet, n, "kode_seri"))
            continue
        if not r["no_item"].isdigit() or not 1 <= int(r["no_item"]) <= konteks.maks_item.get(met, 200):
            b.pesan.append(Pesan("galat", "No item tidak valid.", sheet, n, "no_item"))
            continue
        if not nama:
            b.pesan.append(Pesan("galat", "Komoditas wajib diisi.", sheet, n, "komoditas"))
            continue
        kunci = (wil, lap, met, int(r["no_item"]))
        it = b.items.get(kunci)
        if it is None:
            it = b.items[kunci] = ItemBerkas(kunci, sheet, n, nama, sumber=teks(r.get("sumber")))
        elif it.nama.lower() != nama.lower():
            b.pesan.append(Pesan("galat", "Nama komoditas berbeda dalam satu item.", sheet, n, "komoditas"))
            continue
        s = it.seri.get(seri)
        if s is None:
            s = it.seri[seri] = SeriBerkas(seri, len(it.seri) + 1, n, teks(r["satuan"]), catatan=teks(r.get("catatan")))
        if r["jangkar"]:
            j = _angka(r["jangkar"], pemisah)
            if j is None or seri not in JANGKAR:
                b.pesan.append(Pesan("galat", "Jangkar harus angka dan hanya untuk RKA/HARGA/IH/R_MARGIN.", sheet, n,
                                     "jangkar"))
                continue
            s.jangkar = j
        if r["periode"]:
            u = urut_label(r["periode"])
            x = _angka(r["nilai"], pemisah) if r["nilai"] else None
            if u is None:
                b.pesan.append(Pesan("galat", "Periode harus berbentuk YYYY-Tq.", sheet, n, "periode"))
                continue
            if r["nilai"] and x is None:
                b.pesan.append(Pesan("galat", "Nilai bukan angka.", sheet, n, "nilai"))
                continue
            if x is not None:
                if u in s.nilai:
                    b.pesan.append(Pesan("galat", "Nilai untuk periode yang sama muncul dua kali.", sheet, n,
                                         "periode"))
                    continue
                s.nilai[u] = x
                per.add(u)
    b.periode = sorted(per)
    b.sheet_kategori = [sheet]
    return b


def _baca_ref(rows: list[dict[str, str]], pemisah: str, konteks: KonteksTemplat, b: Berkas) -> Berkas:
    sheet = "CSV"
    kurang = [k for k in KOLOM_REF if k not in rows[0]]
    if kurang:
        b.pesan.append(Pesan("galat", f"Kolom wajib tidak ada: {', '.join(kurang)}.", sheet, 1))
        return b
    peta: dict[tuple[str, str], SeriRefBerkas] = {}
    for n, r in enumerate(rows, start=2):
        wil, kode = r["kode_wilayah"], r["kode_referensi"]
        if wil not in konteks.wilayah or not kode:
            b.pesan.append(Pesan("galat", "Kode wilayah/referensi tidak valid.", sheet, n))
            continue
        s = peta.get((wil, kode))
        if s is None:
            s = peta[(wil, kode)] = SeriRefBerkas(wil, kode, n, teks(r["nama"]), teks(r["satuan"]))
            b.seri_ref.append(s)
        u = urut_label(r["periode"]) if r["periode"] else None
        x = _angka(r["nilai"], pemisah) if r["nilai"] else None
        if r["periode"] and (u is None or (r["nilai"] and x is None)):
            b.pesan.append(Pesan("galat", "Periode/nilai tidak valid.", sheet, n))
            continue
        if u is not None and x is not None:
            s.nilai[u] = x
    return b


def tulis_data(baris: list[dict]) -> bytes:
    """Ekspor CSV panjang (UTF-8 dengan BOM agar terbaca Excel)."""
    out = io.StringIO()
    w = csv.DictWriter(out, fieldnames=list(KOLOM_DATA), lineterminator="\n")
    w.writeheader()
    for r in baris:
        w.writerow(r)
    return ("﻿" + out.getvalue()).encode("utf-8")


def tulis_ref(baris: list[dict]) -> bytes:
    out = io.StringIO()
    w = csv.DictWriter(out, fieldnames=list(KOLOM_REF), lineterminator="\n")
    w.writeheader()
    for r in baris:
        w.writerow(r)
    return ("﻿" + out.getvalue()).encode("utf-8")
