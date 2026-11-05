"""Ekspor templat data dasar (docs/05) dari basis data: format sama dengan templates/*_KOSONG.xlsx, sehingga hasil
ekspor dapat diimpor kembali (round-trip: ekspor -> impor -> hitung sama).

- Sheet kategori A..V (+ TOP_SOP bila ada item pajak/subsidi), SERI_REFERENSI, PENYESUAIAN, REF_LAPUS, REF_SERI,
  REF_WILAYAH, PETUNJUK. Warna: kuning isian, hijau rumus, biru tertaut; tahun lama dapat dilipat (outline).
- Nilai hanya yang berada dalam masa berlaku item (nilai di luar masa tidak dipakai mesin), sehingga impor ulang ke
  tahun dasar lain menghasilkan hitungan sama. Seri tertaut kosong (diambil dari sumber tautan); baris rumus berisi
  rumus Excel yang setara.
- Setiap berkas memuat tanda air (audit.ekspor) di PETUNJUK dan kaki halaman semua sheet.
"""
from __future__ import annotations

import io
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation
from sqlalchemy import Connection, text

from . import tautan as tt
from .templat import JANGKAR, SHEET_TOP_SOP, label_periode, urut

BIRU_TUA = "FF1F3A5F"
F_KEPALA = PatternFill("solid", fgColor=BIRU_TUA)
F_TAHUN = PatternFill("solid", fgColor="FFD6DEEA")
F_ITEM = (PatternFill("solid", fgColor="FFEEF1F5"), PatternFill("solid", fgColor="FFF7F7F7"))
F_ISIAN = PatternFill("solid", fgColor="FFFFF7CC")
F_RUMUS = PatternFill("solid", fgColor="FFE3F1E6")
F_TAUT = PatternFill("solid", fgColor="FFE6F0FA")
TIPIS = Side(style="thin", color="FFD0D5DD")
BINGKAI = Border(left=TIPIS, right=TIPIS, top=TIPIS, bottom=TIPIS)
FMT_NILAI = "#,##0.00####"
FMT_JANGKAR = "#,##0.000000####"
METODE_URUT = {"REV": 0, "EKS": 1, "DEF": 2, "PDK": 3}
KOLOM_DEPAN = ["Kode Wilayah", "Kode Lapus", "Metode", "No Item", "Komoditas / Rincian", "Kode Seri", "Satuan",
               "Jangkar Tahun Dasar"]
LEBAR_DEPAN = [7, 8, 7, 5, 34, 12, 14, 12]
LEBAR_BELAKANG = [22, 9, 26, 30, 14, 40, 46]
LABEL_SERI = {"KUANTUM": "Kuantum produksi", "HARGA": "Harga per satuan", "IH": "Indeks harga", "RKA":
              "Rasio konsumsi antara", "INDEKS": "Indeks ekstrapolator", "BASE_ADHB": "Baseline output ADHB",
              "BASE_ADHK": "Baseline output ADHK", "OUT_ADHB": "Output ADHB", "NTB_ADHB": "NTB ADHB"}

PETUNJUK_ISI: list[tuple[str | None, str | None, str | None, str | None]] = [
    ("Isi berkas", "{isi_berkas}", None, None),
    (None, "Satu baris = satu seri data (misalnya kuantum atau harga) dari satu komoditas/rincian di satu wilayah.",
     None, None),
    (None, "Baris-baris berwarna sama yang berurutan = satu item. Item dikenali dari Kode Wilayah + Kode Lapus + "
     "Metode + No Item.", None, None),
    (None, "{kolom_triwulan}", None, None),
    (None, None, None, None),
    ("Cara mengisi", "1. Pilih sheet kategori, cari item. Isi angka hanya di sel kuning (kolom triwulan dan kolom "
     "Jangkar).", None, None),
    (None, "2. Komoditas baru: pakai baris kosong di bawah tabel. Isi Kode Wilayah, Kode Lapus, Metode, No Item "
     "(nomor baru), Komoditas,", None, None),
    (None, "    lalu satu baris per seri sesuai daftar di bawah. Komoditas boleh berbeda antartriwulan; kosongkan "
     "triwulan yang tidak ada datanya.", None, None),
    (None, "3. Data kosong bukan nol. Isi 0 hanya bila memang nol (produksi tidak ada).", None, None),
    (None, "4. Satuan isian harus sama dengan kolom Satuan. RKA berupa desimal (0,25 bukan 25%).", None, None),
    (None, "5. Baris hijau dihitung otomatis dari baris komponen (rumus Excel); jangan diketik. Baris biru mengambil "
     "seri dari tempat lain (kolom Tautan).", None, None),
    (None, "6. Unggah lewat menu Data Dasar > Impor templat. Sistem menampilkan pratinjau selisih sebelum disimpan.",
     None, None),
    (None, None, None, None),
    ("Kolom Jangkar", "Nilai tahun dasar yang dipakai menghitung ADHK. Baris RKA: rasio konsumsi antara tahun dasar "
     "(wajib).", None, None),
    (None, "Baris HARGA: harga tahun dasar (TD2010 = harga 2010; TD2025 boleh kosong karena dihitung dari rata-rata "
     "tertimbang 2025).", None, None),
    (None, "Baris IH: indeks tahun dasar (TD2010 = 100; TD2025 kosong = rata-rata IH 2025). Item tanpa data tahun "
     "dasar wajib diberi jangkar.", None, None),
    (None, None, None, None),
    ("Warna", "Kuning = isian · Abu-abu = kode/keterangan · Hijau = rumus otomatis · Biru muda = seri tertaut · "
     "Oranye = perlu dicek.", None, None),
    (None, "Angka biru = angka hasil pengisian otomatis dari sumber (lihat kolom Lokasi Sumber di paling kanan).",
     None, None),
    (None, None, None, None),
    ("Keamanan", "Berkas terisi memuat angka PDRB sebelum rilis. Simpan di folder terbatas dan hapus salinan setelah "
     "diunggah.", None, None),
    (None, "Data mikro perusahaan (nama, NIB, KIP) tidak boleh dimasukkan ke templat ini.", None, None),
    (None, None, None, None),
    ("Seri per metode", None, None, None),
]
REF_SERI: list[tuple[str, str, str, str]] = [
    ("REV", "KUANTUM", "wajib", "Kuantum produksi. Jumlah fisik (ton, kWh, penumpang, dll.)"),
    ("REV", "HARGA", "wajib", "Harga per satuan. Satuan harga harus sepadan dengan satuan kuantum. Jangkar = harga "
     "tahun dasar (opsional, kosong = dihitung dari data tahun dasar)"),
    ("REV", "IH", "opsional", "Indeks harga. Dipakai bila harga dihitung dari indeks: HARGA = jangkar x IH / 100"),
    ("REV", "RKA", "wajib", "Rasio konsumsi antara. Per triwulan untuk ADHB; jangkar = rasio KA tahun dasar untuk "
     "ADHK (wajib)"),
    ("EKS", "INDEKS", "wajib", "Indeks ekstrapolator. Isi kolom Jenis Indeks: IP = indeks produksi (volume), IB = "
     "indeks berlaku (nilai)"),
    ("EKS", "IH", "wajib", "Indeks harga. Deflator item"),
    ("EKS", "BASE_ADHB", "wajib*", "Baseline output ADHB. Output ADHB tahun dasar per triwulan (IB wajib)"),
    ("EKS", "BASE_ADHK", "wajib*", "Baseline output ADHK. Output ADHK tahun dasar per triwulan (IP wajib)"),
    ("EKS", "RKA", "wajib", "Rasio konsumsi antara. Sama seperti REV"),
    ("DEF", "OUT_ADHB", "wajib", "Output ADHB. Nilai output berlaku (juta Rp, atau satuan sumber dengan faktor di "
     "Catatan)"),
    ("DEF", "NTB_ADHB", "opsional", "NTB ADHB. Bila kosong: NTB = (1 - RKA) x Output"),
    ("DEF", "IH", "wajib", "Indeks harga. Deflator; boleh ditautkan ke SERI_REFERENSI (kolom Tautan: REF: kode)"),
    ("DEF", "RKA", "opsional", "Rasio konsumsi antara. Dipakai bila NTB_ADHB kosong; jangkar = rasio KA tahun dasar"),
    ("PDK", "NILAI", "-", "Indikator pendukung. Tidak dihitung ke output; untuk cek arah dan fenomena"),
    ("BANTU", "TPK, KAMAR, NILAI_KAPITA, PENDUDUK, VOLUME, V_IMPOR, R_MARGIN, KURS", "-",
     "Seri komponen. Komponen rumus; baris hijau dihitung otomatis dari komponen"),
]
PETUNJUK_METODE = [
    ("Metode", "REV", "Revaluasi: Output = kuantum x harga; ADHK = kuantum x harga tahun dasar"),
    (None, "EKS", "Ekstrapolasi: baseline tahun dasar digerakkan indeks (IP menggerakkan ADHK, IB menggerakkan ADHB)"),
    (None, "DEF", "Deflasi: ADHK = Output ADHB / IH x IH tahun dasar"),
    (None, "PDK", "Indikator pendukung (tidak dihitung)"),
]


# ======================================================================== data dari DB
@dataclass
class SeriEkspor:
    kode: str
    satuan: str | None = None
    label: str | None = None
    catatan: str | None = None
    lokasi: str | None = None
    teks_tautan: str | None = None
    tautan: dict | None = None  # lk.tautan_seri (kode lapus, kode seri ref)
    jangkar: float | None = None
    nilai: dict[int, float] = field(default_factory=dict)


@dataclass
class ItemEkspor:
    id: int
    wilayah: str
    lapus: str
    urutan_lapus: int
    metode: str
    nomor: int
    nama: str
    jenis_indeks: str | None
    sumber: str | None
    padanan: str | None
    seri: list[SeriEkspor] = field(default_factory=list)


@dataclass
class DataEkspor:
    td_kode: str
    tahun_dasar: int
    klasifikasi: str
    pohon: list[dict]  # ref.lapus aktif urut
    kelompok: dict[str, list[str]]
    padanan_lapus: dict[str, list[str]]
    wilayah: list[tuple[str, str]]
    item: list[ItemEkspor]
    seri_ref: list[dict]  # kode, nama, satuan, keterangan, wilayah, nilai
    penyesuaian: list[dict]
    periode: list[int]
    tanda_air: str
    kosong: bool


def _rentang(conn: Connection, putaran_id: int | None) -> tuple[int, int]:
    a, b = 2019, 2026
    if putaran_id is not None:
        r = conn.execute(text("SELECT pa.tahun, pz.tahun FROM lk.putaran p JOIN ref.periode pa ON pa.id ="
                              " p.periode_awal_id JOIN ref.periode pz ON pz.id = p.periode_akhir_id WHERE p.id = :p"),
                         {"p": putaran_id}).first()
        if r is not None:
            a, b = min(a, r[0]), max(b, r[1])
    return a, b


def muat_data(conn: Connection, tahun_dasar_id: int, putaran_id: int | None, wilayah: list[str] | None,
              kosong: bool, tanda_air: str) -> DataEkspor:
    q: dict[str, Any] = {"td": tahun_dasar_id, "p": putaran_id}
    td = conn.execute(text("SELECT kode, tahun_dasar, klasifikasi FROM ref.tahun_dasar WHERE id = :td"), q).one()
    pohon = [dict(r) for r in conn.execute(text(
        "SELECT l.id, l.kode, l.nama, l.level, l.urutan, l.jenis, l.is_migas, i.kode AS induk FROM ref.lapus l"
        " LEFT JOIN ref.lapus i ON i.id = l.induk_id WHERE l.tahun_dasar_id = :td AND l.aktif ORDER BY l.urutan"),
        q).mappings()]
    kode_id = {r["id"]: r["kode"] for r in pohon}
    urutan = {r["kode"]: r["urutan"] for r in pohon}
    kelompok: dict[str, list[str]] = defaultdict(list)
    for k, a in conn.execute(text(
            "SELECT kl.kode, an.kode FROM ref.lapus_kelompok x JOIN ref.lapus kl ON kl.id = x.kelompok_id"
            " JOIN ref.lapus an ON an.id = x.anggota_id WHERE kl.tahun_dasar_id = :td ORDER BY an.urutan"), q):
        kelompok[k].append(a)
    padanan: dict[str, list[str]] = defaultdict(list)
    for a, b in conn.execute(text(
            "SELECT x.kode, y.kode FROM ref.konkordansi_lapus k JOIN ref.lapus x ON x.id = k.lapus_asal_id"
            " JOIN ref.lapus y ON y.id = k.lapus_tujuan_id WHERE x.tahun_dasar_id = :td ORDER BY y.urutan"), q):
        padanan[a].append(b)
    for a, b in conn.execute(text(
            "SELECT y.kode, x.kode FROM ref.konkordansi_lapus k JOIN ref.lapus x ON x.id = k.lapus_asal_id"
            " JOIN ref.lapus y ON y.id = k.lapus_tujuan_id WHERE y.tahun_dasar_id = :td ORDER BY x.urutan"), q):
        padanan[a].append(b)
    wil_semua = [(r[0].strip(), r[1]) for r in conn.execute(text(
        "SELECT kode, nama FROM ref.wilayah WHERE aktif ORDER BY urutan"))]
    q["w"] = wilayah or [w for w, _ in wil_semua]
    items: dict[int, ItemEkspor] = {}
    masa: dict[int, tuple[int | None, int | None]] = {}
    for r in conn.execute(text(
            "SELECT i.id, i.wilayah_kode, i.lapus_id, i.metode_kode, i.nomor, i.nama, i.jenis_indeks, i.sumber_teks,"
            " i.padanan_teks, pm.urut AS mulai, ps.urut AS selesai, lp.kode AS kode_padanan FROM lk.item i"
            " LEFT JOIN ref.periode pm ON pm.id = i.periode_mulai_id LEFT JOIN ref.periode ps"
            " ON ps.id = i.periode_selesai_id LEFT JOIN ref.lapus lp ON lp.id = i.lapus_padanan_id"
            " WHERE i.tahun_dasar_id = :td AND i.wilayah_kode = ANY(:w)"), q).mappings():
        if r["lapus_id"] not in kode_id:
            continue
        kd = kode_id[r["lapus_id"]]
        items[r["id"]] = ItemEkspor(r["id"], r["wilayah_kode"].strip(), kd, urutan[kd], r["metode_kode"], r["nomor"],
                                    r["nama"], r["jenis_indeks"], r["sumber_teks"],
                                    r["padanan_teks"] or r["kode_padanan"])
        masa[r["id"]] = (r["mulai"], r["selesai"])
    ids = list(items)
    meta: dict[int, dict[str, dict]] = defaultdict(dict)
    for r in conn.execute(text("SELECT * FROM lk.seri_item WHERE item_id = ANY(:i) ORDER BY item_id, urutan"),
                          {"i": ids}).mappings():
        meta[r["item_id"]][r["jenis_seri"]] = dict(r)
    taut: dict[int, dict[str, dict]] = defaultdict(dict)
    for r in conn.execute(text(
            "SELECT t.*, s.kode AS kode_ref FROM lk.tautan_seri t LEFT JOIN lk.seri_referensi s ON s.id = t.seri_id"
            " WHERE t.item_id = ANY(:i)"), {"i": ids}).mappings():
        taut[r["item_id"]][r["jenis_seri"]] = {
            "sumber": r["sumber"], "rumus": r["rumus"], "seri_ref": r["kode_ref"], "besaran": r["besaran"],
            "faktor": float(r["faktor"]), "lapus": tuple(kode_id.get(x, "") for x in (r["lapus_sumber_ids"] or ()))}
    param: dict[int, dict[str, float]] = defaultdict(dict)
    nilai: dict[int, dict[str, dict[int, float]]] = defaultdict(lambda: defaultdict(dict))
    if putaran_id is not None and not kosong:  # templat kosong: tanpa angka (termasuk jangkar)
        for i, k, v in conn.execute(text("SELECT item_id, kode, nilai::float8 FROM lk.parameter_item"
                                         " WHERE putaran_id = :p AND item_id = ANY(:i)"), {"p": putaran_id, "i": ids}):
            param[i][k] = v
        for i, s, u, v in conn.execute(text(
                "SELECT n.item_id, n.jenis_seri, p.urut, n.nilai::float8 FROM lk.nilai_item n JOIN ref.periode p"
                " ON p.id = n.periode_id WHERE n.putaran_id = :p AND n.item_id = ANY(:i) AND n.status_sel = 'isi'"
                " AND n.nilai IS NOT NULL"), {"p": putaran_id, "i": ids}):
            m0, m1 = masa[i]
            if (m0 is None or u >= m0) and (m1 is None or u <= m1):
                nilai[i][s][u] = v
    urut_seri = {(m, k): u for m, k, u in conn.execute(text("SELECT metode_kode, kode, urutan FROM ref.jenis_seri"))}
    bawaan = defaultdict(list)
    for m, k in conn.execute(text("SELECT metode_kode, kode FROM ref.jenis_seri WHERE NOT komponen ORDER BY urutan")):
        bawaan[m].append(k)
    for iid, it in items.items():
        kode_seri = list(meta[iid])
        lain = (set(nilai[iid]) | set(taut[iid]) | {s for s, p in JANGKAR.items() if p in param[iid]}) - set(kode_seri)
        if not kode_seri:
            lain |= set(bawaan[it.metode])
        kode_seri += sorted(lain, key=lambda s: urut_seri.get((it.metode, s), 99))
        for s in kode_seri:
            m = meta[iid].get(s, {})
            it.seri.append(SeriEkspor(s, m.get("satuan"), m.get("label"), m.get("catatan"), m.get("lokasi_sumber"),
                                      m.get("teks_tautan"), taut[iid].get(s),
                                      param[iid].get(JANGKAR[s]) if s in JANGKAR else None,
                                      {} if s in taut[iid] else nilai[iid].get(s, {})))
    daftar = sorted(items.values(), key=lambda x: (x.urutan_lapus, METODE_URUT.get(x.metode, 9), x.wilayah, x.nomor))

    # seri referensi: yang ditautkan item ekspor + yang bernilai di putaran untuk wilayah ekspor
    dipakai = {t["seri_ref"] for d in taut.values() for t in d.values() if t["seri_ref"]}
    seri_ref: list[dict] = []
    if putaran_id is not None or dipakai:
        nilai_ref: dict[tuple[str, str], dict[int, float]] = defaultdict(dict)
        if putaran_id is not None and not kosong:
            for k, w, u, v in conn.execute(text(
                    "SELECT s.kode, n.wilayah_kode, p.urut, n.nilai::float8 FROM lk.nilai_seri_referensi n"
                    " JOIN lk.seri_referensi s ON s.id = n.seri_id JOIN ref.periode p ON p.id = n.periode_id"
                    " WHERE n.putaran_id = :p AND n.wilayah_kode = ANY(:w)"), q):
                nilai_ref[(k, w.strip())][u] = v
        pemakai: dict[str, set[str]] = defaultdict(set)
        for iid, d in taut.items():
            for t in d.values():
                if t["seri_ref"]:
                    pemakai[t["seri_ref"]].add(items[iid].lapus)
        wil_item: dict[str, set[str]] = defaultdict(set)
        for iid, d in taut.items():
            for t in d.values():
                if t["seri_ref"]:
                    wil_item[t["seri_ref"]].add(items[iid].wilayah)
        for r in conn.execute(text("SELECT kode, nama, satuan, keterangan FROM lk.seri_referensi ORDER BY kode"))\
                .mappings():
            kode = r["kode"]
            for w, _ in wil_semua:
                if w not in q["w"]:
                    continue
                if (kode, w) not in nilai_ref and w not in wil_item.get(kode, set()):
                    continue
                seri_ref.append({"kode": kode, "nama": r["nama"], "satuan": r["satuan"], "sumber": r["keterangan"],
                                 "wilayah": w, "dipakai": ", ".join(sorted(pemakai.get(kode, set()),
                                                                           key=lambda x: urutan.get(x, 0))),
                                 "nilai": nilai_ref.get((kode, w), {})})
    penyesuaian: list[dict] = []
    if putaran_id is not None:
        grup: dict[tuple, dict[int, float]] = defaultdict(dict)
        for x in conn.execute(text(
                "SELECT a.wilayah_kode, l.kode, l.urutan, a.tahap, a.metode_kode, a.jenis_kode, a.harga, a.alasan,"
                " p.urut, a.nilai::float8 FROM lk.penyesuaian a JOIN ref.lapus l ON l.id = a.lapus_id"
                " JOIN ref.periode p ON p.id = a.periode_id WHERE a.putaran_id = :p AND a.wilayah_kode = ANY(:w)"
                " AND a.tahap IN ('METODE','REKON') AND a.status <> 'ditolak'"), q):
            grup[(x[2], x[0].strip(), x[1], x[3], x[4], x[5], x[6], x[7])][x[8]] = x[9]
        for k in sorted(grup, key=lambda x: (x[0], x[1], x[3], x[4] or "", x[5], x[6], x[7] or "")):
            penyesuaian.append({"wilayah": k[1], "lapus": k[2], "tahap": k[3], "metode": k[4], "jenis": k[5],
                                "harga": k[6], "alasan": k[7], "nilai": {} if kosong else grup[k]})
    a, b = _rentang(conn, putaran_id)
    return DataEkspor(td.kode, td.tahun_dasar, td.klasifikasi, pohon, dict(kelompok), dict(padanan), wil_semua,
                      daftar, seri_ref, penyesuaian, [urut(y, q_) for y in range(a, b + 1) for q_ in (1, 2, 3, 4)],
                      tanda_air, kosong)


# ======================================================================== tulis xlsx
def _kepala(ws: Any, baris: int, judul: list[str]) -> None:
    for j, h in enumerate(judul, start=1):
        c = ws.cell(baris, j, h)
        c.fill, c.font, c.border = F_KEPALA, Font(b=True, color="FFFFFFFF"), BINGKAI
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    ws.row_dimensions[baris].height = 31.5


def _tahun(ws: Any, periode: list[int], kolom_awal: int) -> None:
    for j, u in enumerate(periode):
        c = ws.cell(3, kolom_awal + j, u // 4 if u % 4 == 0 else None)
        c.fill, c.font, c.alignment = F_TAHUN, Font(b=True), Alignment(horizontal="center")


def _lipat_tahun(ws: Any, periode: list[int], kolom_awal: int) -> None:
    tahun = sorted({u // 4 for u in periode})
    lama = [y for y in tahun if y < tahun[-1] - 1]
    for j, u in enumerate(periode):
        cd = ws.column_dimensions[get_column_letter(kolom_awal + j)]
        cd.width = 11
        if u // 4 in lama:
            cd.outlineLevel = 1


def _kaki(ws: Any, tanda_air: str) -> None:
    ws.oddFooter.center.text = tanda_air
    ws.oddHeader.right.text = "SINERGI - RAHASIA"
    ws.sheet_properties.tabColor = BIRU_TUA


def _sheet_kategori(wb: Workbook, nama: str, judul: str, sub: str, item: list[ItemEkspor], d: DataEkspor,
                    kode_lapus: list[str]) -> None:
    ws = wb.create_sheet(nama)
    per = d.periode
    k0 = len(KOLOM_DEPAN) + 1
    kol_pad = "Kode LK BPS" if d.klasifikasi == "KBLI2025" else "Lapus TD2025 (konkordansi)"
    belakang = ["Seri", "Jenis Indeks (EKS)", "Sumber Data", "Tautan / Rumus", kol_pad, "Catatan", "Lokasi Sumber"]
    c = ws.cell(1, 1, judul)
    c.font = Font(b=True, sz=12, color=BIRU_TUA)
    c = ws.cell(1, 6, sub)
    c.font = Font(i=True, color="FF555555")
    c = ws.cell(2, 1, "Isi sel kuning. Satu baris = satu seri. Baris dengan warna latar sama = satu item. Kosongkan "
                      "triwulan yang belum ada datanya (bukan 0).")
    c.font = Font(i=True, sz=10, color="FF555555")
    _tahun(ws, per, k0)
    _kepala(ws, 4, KOLOM_DEPAN + [label_periode(u) for u in per] + belakang)
    kb = k0 + len(per)
    kol = {h: kb + i for i, h in enumerate(belakang)}
    n = 5
    for idx, it in enumerate(item):
        isi_fill = F_ITEM[idx % 2]
        baris_seri: dict[str, int] = {}
        for j, s in enumerate(it.seri):
            baris_seri[s.kode] = n + j
        for j, s in enumerate(it.seri):
            r = n + j
            nilai_depan = [it.wilayah, it.lapus, it.metode, it.nomor, it.nama, s.kode, s.satuan, s.jangkar]
            for col, v in enumerate(nilai_depan, start=1):
                cell = ws.cell(r, col, v)
                cell.border = BINGKAI
                if col <= 7:
                    cell.fill = isi_fill
                    cell.font = Font(b=(col == 5 and j == 0), color=None if j == 0 else "FF8A8A8A")
            hc = ws.cell(r, 8)
            hc.fill, hc.number_format = F_ISIAN, FMT_JANGKAR
            taut = s.tautan
            jenis = "isian"
            if taut is not None:
                jenis = "rumus" if taut["sumber"] == "RUMUS" and taut["rumus"] not in (
                    "MARGIN_X_OUTPUT", "MARGIN_X_IMPOR") else "taut"
            margin = next((x for x in it.seri if x.tautan and x.tautan.get("rumus") in ("MARGIN_X_OUTPUT",
                                                                                         "MARGIN_X_IMPOR")), None)
            for jj, u in enumerate(per):
                cell = ws.cell(r, k0 + jj, s.nilai.get(u))
                cell.border, cell.number_format = BINGKAI, FMT_NILAI
                cell.fill = {"isian": F_ISIAN, "rumus": F_RUMUS, "taut": F_TAUT}[jenis]
                if jenis == "rumus" and taut is not None:
                    cell.value = _rumus_excel(taut, baris_seri, r, get_column_letter(k0 + jj))
            ws.cell(r, kol["Seri"], s.label or LABEL_SERI.get(s.kode))
            if s.kode == "INDEKS" or (it.metode == "EKS" and j == 0 and "INDEKS" not in baris_seri):
                ws.cell(r, kol["Jenis Indeks (EKS)"], it.jenis_indeks)
            ws.cell(r, kol["Sumber Data"], it.sumber)
            ws.cell(r, kol["Tautan / Rumus"], _teks_tautan(it, s, margin))
            ws.cell(r, kol[kol_pad], it.padanan)
            ws.cell(r, kol["Catatan"], s.catatan)
            ws.cell(r, kol["Lokasi Sumber"], s.lokasi)
            for h in belakang:
                ws.cell(r, kol[h]).border = BINGKAI
        n += len(it.seri)
    akhir = max(n - 1, 5)
    for i, w in enumerate(LEBAR_DEPAN, start=1):
        ws.column_dimensions[get_column_letter(i)].width = w
    _lipat_tahun(ws, per, k0)
    for i, w in enumerate(LEBAR_BELAKANG):
        ws.column_dimensions[get_column_letter(kb + i)].width = w
    ws.freeze_panes = ws.cell(5, k0)
    ws.auto_filter.ref = f"A4:{get_column_letter(kb + len(belakang) - 1)}{akhir}"
    batas = akhir + 200  # baris kosong di bawah tabel untuk komoditas baru
    _validasi(ws, "D", batas, DataValidation(type="whole", operator="between", formula1="1", formula2="200",
                                             allow_blank=True, showErrorMessage=True, errorTitle="No item",
                                             error="No item 1-100 (REV), 1-50 (EKS/DEF), 1-200 (PDK)."))
    _daftar(ws, "A", batas, [w for w, _ in d.wilayah])
    _daftar(ws, "B", batas, kode_lapus)
    _daftar(ws, "C", batas, ["REV", "EKS", "DEF", "PDK"])
    _daftar(ws, get_column_letter(kol["Jenis Indeks (EKS)"]), batas, ["IP", "IB"])
    angka = DataValidation(type="decimal", operator="between", formula1="-1000000000000000",
                           formula2="1000000000000000", allow_blank=True, showErrorMessage=True,
                           errorTitle="Harus angka", error="Isi angka saja (tanpa teks/satuan), atau kosongkan.")
    ws.add_data_validation(angka)
    angka.add(f"H5:{get_column_letter(kb - 1)}{batas}")
    _kaki(ws, d.tanda_air)


def _validasi(ws: Any, kolom: str, batas: int, dv: DataValidation) -> None:
    ws.add_data_validation(dv)
    dv.add(f"{kolom}5:{kolom}{batas}")


def _daftar(ws: Any, kolom: str, batas: int, nilai: list[str]) -> None:
    isi = ",".join(nilai)
    if len(isi) > 250:  # batas Excel daftar langsung
        return
    _validasi(ws, kolom, batas, DataValidation(type="list", formula1=f'"{isi}"', allow_blank=True,
                                               showErrorMessage=True, errorTitle="Pilih dari daftar",
                                               error="Gunakan nilai dari daftar pilihan."))


def _rumus_excel(t: dict, baris: dict[str, int], r: int, kol: str) -> str | None:
    rm, f = t["rumus"], t["faktor"]
    kali = "" if f == 1 else f"*{format(f, '.15g')}"
    if rm == "TPK_X_KAMAR" and {"TPK", "KAMAR"} <= set(baris):
        a, b = f"{kol}{baris['TPK']}", f"{kol}{baris['KAMAR']}"
        return f'=IF(AND(ISNUMBER({a}),ISNUMBER({b})),{a}*{b}{kali},"")'
    if rm == "JANGKAR_X_IH_100" and "IH" in baris:
        a = f"{kol}{baris['IH']}"
        return f'=IF(AND(ISNUMBER({a}),ISNUMBER($H${r})),$H${r}*{a}/100{kali},"")'
    if rm == "KAPITA_X_PENDUDUK_X_3" and {"NILAI_KAPITA", "PENDUDUK"} <= set(baris):
        a, b = f"{kol}{baris['NILAI_KAPITA']}", f"{kol}{baris['PENDUDUK']}"
        return f'=IF(AND(ISNUMBER({a}),ISNUMBER({b})),{a}*{b}*3/1000000{kali},"")'
    return None


def _teks_tautan(it: ItemEkspor, s: SeriEkspor, margin: SeriEkspor | None) -> str | None:
    """Teks kolom Tautan / Rumus: teks asli bila masih setara dengan tautan tersimpan, selain itu teks baku."""
    asli = s.teks_tautan
    try:
        urai = tt.urai(asli, s.kode, it.metode)
    except tt.GalatTautan:
        urai = None
    if margin is not None and margin.tautan is not None:
        m = margin.tautan
        baku = tt.teks_kanonik(m["sumber"], m["rumus"], None, m["lapus"], None, m["faktor"])
        pembawa = "R_MARGIN" if any(x.kode == "R_MARGIN" for x in it.seri) else "OUT_ADHB"
        if s.kode == pembawa:
            if tt.setara(urai, m["sumber"], m["rumus"], None, m["lapus"], None, m["faktor"]):
                return asli
            return baku
        if s.kode == "OUT_ADHB":
            return asli if urai is not None and urai.jenis == "HITUNG_SISTEM" else tt.TEKS_HITUNG_SISTEM
    t = s.tautan
    if t is None or t["rumus"] in ("MARGIN_X_OUTPUT", "MARGIN_X_IMPOR"):
        if urai is None or urai.jenis == "KETERANGAN":
            return asli
        return None  # teks tautan lama tidak berlaku lagi
    if tt.setara(urai, t["sumber"], t["rumus"], t["seri_ref"], t["lapus"], t["besaran"], t["faktor"]):
        return asli
    return tt.teks_kanonik(t["sumber"], t["rumus"], t["seri_ref"], t["lapus"], t["besaran"], t["faktor"])


def _sheet_blok(wb: Workbook, nama: str, judul: str, ket: str, kolom: list[str], baris: list[tuple[list, dict]],
                periode: list[int], tanda_air: str, lebar: list[int]) -> None:
    ws = wb.create_sheet(nama)
    ws.cell(1, 1, judul).font = Font(b=True, sz=12, color=BIRU_TUA)
    ws.cell(2, 1, ket).font = Font(i=True, sz=10, color="FF555555")
    k0 = len(kolom) + 1
    _tahun(ws, periode, k0)
    _kepala(ws, 4, kolom + [label_periode(u) for u in periode] + ["Catatan", "Lokasi Sumber"])
    for i, (depan, nilai) in enumerate(baris, start=5):
        for j, v in enumerate(depan, start=1):
            ws.cell(i, j, v).border = BINGKAI
        for jj, u in enumerate(periode):
            c = ws.cell(i, k0 + jj, nilai.get(u))
            c.fill, c.border, c.number_format = F_ISIAN, BINGKAI, FMT_NILAI
    for i, w in enumerate(lebar, start=1):
        ws.column_dimensions[get_column_letter(i)].width = w
    _lipat_tahun(ws, periode, k0)
    ws.column_dimensions[get_column_letter(k0 + len(periode))].width = 30
    ws.column_dimensions[get_column_letter(k0 + len(periode) + 1)].width = 46
    ws.freeze_panes = ws.cell(5, k0)
    _kaki(ws, tanda_air)


def tulis_xlsx(d: DataEkspor) -> bytes:
    wb = Workbook()
    wb.remove(wb.active)
    akar = [r for r in d.pohon if r["induk"] is None and r["jenis"] in ("kategori", "daun")]
    tahun_awal, tahun_akhir = d.periode[0] // 4, d.periode[-1] // 4
    sheet_kat = [r["kode"] for r in akar]
    ps = wb.create_sheet("PETUNJUK")
    klas = d.klasifikasi.replace("KBLI", "KBLI ")
    judul = (f"Data Dasar LK PDRB Kalimantan Utara - Tahun Dasar {d.tahun_dasar} ({klas}"
             f", {len(sheet_kat)} kategori {sheet_kat[0]}-{sheet_kat[-1]}) - {'KOSONG' if d.kosong else 'TERISI'}")
    ps.cell(2, 2, judul).font = Font(b=True, sz=14, color=BIRU_TUA)
    ps.cell(3, 2, f"Dibangkitkan SINERGI {date.today().isoformat()} · {d.tanda_air}").font = Font(sz=10,
                                                                                                  color="FF555555")
    terpisah = "M dan N terpisah; R, S, T, U" + (", V terpisah." if d.klasifikasi == "KBLI2025" else " terpisah.")
    isi = {"isi_berkas": f"Satu sheet per kategori ({', '.join(sheet_kat)}). {terpisah}",
           "kolom_triwulan": f"Kolom triwulan {tahun_awal}-T1 sampai {tahun_akhir}-T4; klik tanda minus di atas kolom "
                             "untuk menyembunyikan tahun yang tidak dipakai."}
    n = 5
    for row in PETUNJUK_ISI:
        for j, v in enumerate(row, start=2):
            if v is not None:
                c = ps.cell(n, j, v.format(**isi) if "{" in v else v)
                c.font = Font(b=(j == 2), sz=10)
        n += 1
    for j, h in enumerate(["Metode", "Kode Seri", "Wajib", "Keterangan"], start=2):
        c = ps.cell(n, j, h)
        c.fill, c.font, c.border = F_KEPALA, Font(b=True, color="FFFFFFFF"), BINGKAI
    for row in REF_SERI:
        n += 1
        for j, v in enumerate(row, start=2):
            ps.cell(n, j, v)
    n += 2
    for m in PETUNJUK_METODE:
        for j, v in enumerate(m, start=2):
            ps.cell(n, j, v).font = Font(b=(j == 2), sz=10)
        n += 1
    for k, w in zip("ABCDE", (3, 24, 16, 12, 96), strict=True):
        ps.column_dimensions[k].width = w
    _kaki(ps, d.tanda_air)

    anak: dict[str, list[dict]] = defaultdict(list)
    for r in d.pohon:
        if r["induk"]:
            anak[r["induk"]].append(r)

    def daun(kode: str) -> list[dict]:
        r = next(x for x in d.pohon if x["kode"] == kode)
        if r["jenis"] == "daun":
            return [r]
        return [z for c in anak.get(kode, []) for z in daun(c["kode"])]

    for r in akar:
        dd = daun(r["kode"])
        kode_d = [x["kode"] for x in dd]
        it = [i for i in d.item if i.lapus in kode_d]
        sub = "Subkategori: " + "; ".join(f"{x['kode']} {x['nama']}" for x in dd)
        _sheet_kategori(wb, r["kode"], f"Kategori {r['kode']} - {r['nama']}", sub, it, d, kode_d)
    pajak = [x for x in d.pohon if x["jenis"] in ("top", "sop")]
    it_pajak = [i for i in d.item if i.lapus in {x["kode"] for x in pajak}]
    if it_pajak:
        _sheet_kategori(wb, SHEET_TOP_SOP, "Pajak dan Subsidi atas Produk (TOP/SOP)",
                        "Lapus: " + "; ".join(f"{x['kode']} {x['nama']}" for x in pajak), it_pajak, d,
                        [x["kode"] for x in pajak])

    _sheet_blok(wb, "SERI_REFERENSI", "Seri referensi bersama (deflator/indeks yang dipakai banyak item)",
                "Item menautkan seri ini lewat kolom Tautan, contoh: REF: REF_UPAH. Satu seri dipakai banyak item "
                "(tidak disalin).", ["Kode Wilayah", "Kode Referensi", "Nama", "Satuan", "Dipakai Lapus", "Sumber",
                                     "-", "-"],
                [([s["wilayah"], s["kode"], s["nama"], s["satuan"], s["dipakai"] or None, s["sumber"], None, None],
                  s["nilai"]) for s in d.seri_ref] or [([d.wilayah[0][0]] + [None] * 7, {})],
                d.periode, d.tanda_air, [7, 16, 30, 16, 10, 30, 3, 3])
    _sheet_blok(wb, "PENYESUAIAN", "Penyesuaian (adjustment) per lapus - opsional saat unggah",
                "Tahap METODE: ADJ1 coverage, ADJ2 konseptual, SC output sekunder (per metode). Tahap REKON: ADJ3 "
                "rekonsiliasi, ADJ4_OUTPUT/ADJ4_NTB benchmarking. Alasan wajib. Penyesuaian akhir pimpinan "
                "(simulasi) diinput di sistem.", ["Kode Wilayah", "Kode Lapus", "Tahap", "Metode", "Jenis", "Harga",
                                                   "Alasan", "-"],
                [([a["wilayah"], a["lapus"], a["tahap"], a["metode"], a["jenis"], a["harga"], a["alasan"], None],
                  a["nilai"]) for a in d.penyesuaian], d.periode, d.tanda_air, [7, 8, 9, 8, 13, 6, 40, 3])

    rl = wb.create_sheet("REF_LAPUS")
    rl.cell(1, 1, f"Pohon lapangan usaha {d.td_kode} - urutan = baris tabel pokok (format tetap)").font = Font(
        b=True, sz=12, color=BIRU_TUA)
    lain = "TD2010" if d.klasifikasi == "KBLI2025" else "TD2025"
    _kepala(rl, 3, ["Urutan", "Kode Lapus", "Lapangan Usaha", "Level", "Induk", "Jenis", "Migas", f"Padanan {lain}"])
    n = 4
    for r in d.pohon:
        if r["jenis"] == "kelompok":
            continue
        indent = "   " * max(0, r["level"] - 1)
        nilai = [r["urutan"], r["kode"], indent + r["nama"], r["level"], r["induk"], r["jenis"],
                 "Ya" if r["is_migas"] else None, ", ".join(d.padanan_lapus.get(r["kode"], [])) or None]
        for j, v in enumerate(nilai, start=1):
            rl.cell(n, j, v)
        n += 1
    kel = [r for r in d.pohon if r["jenis"] == "kelompok"]
    if kel:
        n += 1
        rl.cell(n, 2, "Kelompok publikasi (dijumlahkan otomatis, tidak diinput):")
        for r in kel:
            n += 1
            rl.cell(n, 2, r["kode"])
            rl.cell(n, 3, f"{r['nama']} = {' + '.join(d.kelompok.get(r['kode'], []))}")
    for k, w in zip("ABCDEFGH", (7, 10, 80, 6, 8, 12, 7, 26), strict=True):
        rl.column_dimensions[k].width = w
    _kaki(rl, d.tanda_air)

    rs = wb.create_sheet("REF_SERI")
    for j, h in enumerate(["Metode", "Kode Seri", "Nama", "Wajib", "Keterangan"], start=1):
        rs.cell(1, j, h).font = Font(b=True)
    for i, (mt, ks, wj, ket) in enumerate(REF_SERI, start=2):
        nm_seri, _, rinci = ket.partition(". ")
        for j, isi_sel in enumerate([mt, ks, nm_seri, wj, rinci or ket], start=1):
            rs.cell(i, j, isi_sel)
    _kaki(rs, d.tanda_air)
    rw = wb.create_sheet("REF_WILAYAH")
    rw.cell(1, 1, "Kode Wilayah").font = Font(b=True)
    rw.cell(1, 2, "Nama").font = Font(b=True)
    for i, (kw, nw) in enumerate(d.wilayah, start=2):
        rw.cell(i, 1, kw)
        rw.cell(i, 2, nw)
    _kaki(rw, d.tanda_air)
    for nama in ("REF_LAPUS", "REF_SERI", "REF_WILAYAH"):
        wb[nama].protection.sheet = True
    wb.properties.title = judul
    wb.properties.creator = "SINERGI"
    wb.properties.keywords = d.tanda_air
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def baris_csv(d: DataEkspor) -> list[dict]:
    """Baris CSV panjang (tanpa tautan; seri tertaut tidak ditulis)."""
    out: list[dict] = []
    for it in d.item:
        for s in it.seri:
            if s.tautan is not None and not s.jangkar:
                continue
            dasar = {"tahun_dasar": d.td_kode, "kode_wilayah": it.wilayah, "kode_lapus": it.lapus, "metode": it.metode,
                     "no_item": it.nomor, "komoditas": it.nama, "kode_seri": s.kode, "satuan": s.satuan or "",
                     "sumber": it.sumber or "", "catatan": s.catatan or ""}
            jangkar = "" if s.jangkar is None else format(s.jangkar, ".17g")
            if not s.nilai:
                if jangkar:
                    out.append({**dasar, "jangkar": jangkar, "periode": "", "nilai": ""})
                continue
            for i, u in enumerate(sorted(s.nilai)):
                out.append({**dasar, "jangkar": jangkar if i == 0 else "", "periode": label_periode(u),
                            "nilai": format(s.nilai[u], ".17g")})
    return out
