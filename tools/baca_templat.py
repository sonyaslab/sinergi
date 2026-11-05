"""
Pembaca rujukan templat data dasar terpadu (TD2010 / TD2025) -> struktur item + validasi format.
Dipakai sebagai acuan importer backend (apps/api/impor). Tidak menyimpan berkas mentah.

    python tools/baca_templat.py Templat_Data_Dasar_TD2025_KOSONG.xlsx  > ringkasan.json

Aturan baca (WAJIB sama di backend apps/api/impor/templat.py):
- Sheet kategori = sheet yang namanya satu huruf A..V, plus sheet TOP_SOP (item pajak/subsidi atas produk, keputusan 1).
  Header di baris 4; data mulai baris 5.
- Kolom kunci: Kode Wilayah, Kode Lapus, Metode, No Item, Komoditas / Rincian, Kode Seri, Satuan, Jangkar Tahun Dasar.
- Kolom periode berlabel 'YYYY-Tq'. Sel kosong = tidak tersedia (BUKAN 0).
- Baris dengan Tautan/Rumus diawali 'RUMUS:' TIDAK dibaca nilainya (sistem menghitung ulang dari komponen).
- Baris dengan Tautan 'REF: <kode>' mengambil seri dari sheet SERI_REFERENSI.
- Tata bahasa lengkap kolom Tautan / Rumus (MARGIN:, HASIL:, "Dihitung sistem", "Ikut IH item C201", "Harga mengikuti
  item Sapi", faktor) ada di apps/api/impor/tautan.py; pembaca ini mengembalikan teksnya apa adanya.
- Satu item = (Kode Wilayah, Kode Lapus, Metode, No Item). Nama komoditas harus sama di semua baris item.
"""
from __future__ import annotations

import json
import re
import sys
from collections import defaultdict

import openpyxl

RX_P = re.compile(r"^(\d{4})-T([1-4])$")
WAJIB = {"REV": {"KUANTUM", "HARGA", "RKA"}, "EKS": {"INDEKS", "IH", "RKA"}, "DEF": {"OUT_ADHB", "IH"}, "PDK": {"NILAI"}}
KOMPONEN = {"TPK", "KAMAR", "NILAI_KAPITA", "PENDUDUK", "VOLUME", "V_IMPOR", "R_MARGIN", "KURS"}
BOLEH = {"REV": {"KUANTUM", "HARGA", "IH", "RKA", "TPK", "KAMAR"},
         "EKS": {"INDEKS", "IH", "BASE_ADHB", "BASE_ADHK", "RKA"},
         "DEF": {"OUT_ADHB", "NTB_ADHB", "IH", "RKA", "NILAI_KAPITA", "PENDUDUK", "VOLUME", "V_IMPOR", "R_MARGIN", "KURS"},
         "PDK": {"NILAI"}}


def baca(path: str):
    wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
    items, pesan = {}, []
    for sh in wb.sheetnames:
        if not re.fullmatch(r"[A-V]", sh) and sh != "TOP_SOP":
            continue
        rows = wb[sh].iter_rows(min_row=4, values_only=True)
        hd = list(next(rows))
        col = {h: i for i, h in enumerate(hd) if h}
        per = {i: f"{m.group(1)}-T{m.group(2)}" for i, h in enumerate(hd) if isinstance(h, str) and (m := RX_P.match(h))}
        for n, r in enumerate(rows, start=5):
            if not r or not r[col["Kode Wilayah"]] or not r[col["Kode Seri"]]:
                continue
            g = lambda h: r[col[h]] if h in col else None
            key = (str(g("Kode Wilayah")), g("Kode Lapus"), g("Metode"), g("No Item"))
            if sh != "TOP_SOP" and not str(key[1]).startswith(sh):
                pesan.append(f"{sh}!baris {n}: lapus {key[1]} bukan kategori {sh}")
            it = items.setdefault(key, {"nama": g("Komoditas / Rincian"), "seri": {}, "jenis_indeks": None})
            if it["nama"] != g("Komoditas / Rincian"):
                pesan.append(f"{sh}!baris {n}: nama komoditas berbeda dalam satu item {key}")
            seri = g("Kode Seri")
            if seri not in BOLEH.get(key[2], set()):
                pesan.append(f"{sh}!baris {n}: seri {seri} tidak berlaku untuk metode {key[2]}")
            tautan = (g("Tautan / Rumus") or "").strip()
            nilai = {} if tautan.upper().startswith("RUMUS:") else {
                p: float(r[i]) for i, p in per.items() if isinstance(r[i], (int, float)) and not isinstance(r[i], bool)}
            for i, p in per.items():
                if isinstance(r[i], str) and r[i].strip():
                    pesan.append(f"{sh}!baris {n} {p}: teks '{r[i][:20]}' bukan angka")
            it["seri"][seri] = {"satuan": g("Satuan"), "jangkar": g("Jangkar Tahun Dasar"), "tautan": tautan, "nilai": nilai}
            if seri == "INDEKS":
                it["jenis_indeks"] = g("Jenis Indeks (EKS)")
    for key, it in items.items():
        kurang = WAJIB.get(key[2], set()) - set(it["seri"])
        if kurang and not (key[2] == "REV" and "KUANTUM" in kurang and {"TPK", "KAMAR"} <= set(it["seri"])):
            pesan.append(f"Item {key} '{it['nama']}': seri wajib belum ada {sorted(kurang)}")
        if key[2] == "EKS" and it["jenis_indeks"] not in ("IP", "IB"):
            pesan.append(f"Item {key} '{it['nama']}': Jenis Indeks harus IP atau IB")
        rka = it["seri"].get("RKA")
        if rka and key[2] in ("REV", "EKS") and rka["jangkar"] is None:
            pesan.append(f"Item {key} '{it['nama']}': jangkar RKA (rasio KA tahun dasar) kosong [V02]")
    return items, pesan


if __name__ == "__main__":
    items, pesan = baca(sys.argv[1])
    per_lapus = defaultdict(int)
    for k in items:
        per_lapus[k[1]] += 1
    print(json.dumps({"jumlah_item": len(items), "item_per_lapus": per_lapus, "pesan": pesan[:200],
                      "jumlah_pesan": len(pesan)}, ensure_ascii=False, indent=1, default=str))
