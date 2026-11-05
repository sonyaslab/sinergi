"""Fixture uji impor/ekspor: tahun dasar salinan (TD2025 atau TD2010), putaran, pengisi templat sintetis."""
from __future__ import annotations

import io
import random
import re
import sys
from pathlib import Path

import openpyxl

ROOT = Path(__file__).resolve().parents[4]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
TEMPLAT = ROOT / "templates"
RX_P = re.compile(r"^(\d{4})-T([1-4])$")


def _sel_angka(ws, r: int, i: int, x: float) -> None:
    ws.cell(r, i + 1).value = x


def isi_sintetis(sumber: Path, benih: int = 7, akhir: str = "2026-T2", adj: bool = True) -> bytes:
    """Isi templat KOSONG dengan angka acak (fiktif) di semua sel kuning, jangkar, seri referensi, dan penyesuaian.

    Baris RUMUS/tautan dibiarkan (nilainya tidak diimpor). BASE_* hanya di tahun baseline (2025 untuk TD2025,
    2024 untuk TD2010). Tidak ada angka nyata.
    """
    rnd = random.Random(benih)  # noqa: S311 - angka uji fiktif, bukan kriptografi
    wb = openpyxl.load_workbook(sumber)
    td2010 = "TD2010" in sumber.name
    baseline = "2024" if td2010 else "2025"
    batas = (int(akhir[:4]), int(akhir[-1]))
    for ws in wb.worksheets:
        if not (re.fullmatch(r"[A-V]", ws.title) or ws.title in ("SERI_REFERENSI", "PENYESUAIAN")):
            continue
        hd = [c.value for c in ws[4]]
        col = {h: i for i, h in enumerate(hd) if isinstance(h, str)}
        per = {i: (int(m.group(1)), int(m.group(2))) for i, h in enumerate(hd)
               if isinstance(h, str) and (m := RX_P.match(h))}
        if ws.title == "SERI_REFERENSI":
            for r in range(5, ws.max_row + 1):
                if ws.cell(r, col["Kode Referensi"] + 1).value:
                    lvl = rnd.uniform(90, 130)
                    for i, (y, q) in per.items():
                        if (y, q) <= batas:
                            _sel_angka(ws, r, i, round(lvl * (1 + 0.01 * ((y - 2019) * 4 + q)), 4))
            continue
        if ws.title == "PENYESUAIAN":
            if not adj:
                continue
            baris = [("6500", "A.1.a", "METODE", "REV", "ADJ1", "CP"), ("6500", "A.1.a", "METODE", "REV", "ADJ1", "K"),
                     ("6500", "B.2" if not td2010 else "B.2", "REKON", None, "ADJ3", "CP"),
                     ("6500", "A.1.a", "REKON", None, "ADJ4_NTB", "K")]
            for j, b in enumerate(baris):
                r = 5 + j
                for h, v in zip(("Kode Wilayah", "Kode Lapus", "Tahap", "Metode", "Jenis", "Harga"), b, strict=True):
                    ws.cell(r, col[h] + 1).value = v
                ws.cell(r, col["Alasan"] + 1).value = "Penyesuaian uji sintetis (angka fiktif)"
                for i, (y, q) in per.items():
                    if (y, q) <= batas and rnd.random() < 0.3:
                        _sel_angka(ws, r, i, round(rnd.uniform(-50, 50), 3))
            continue
        for r in range(5, ws.max_row + 1):
            seri = ws.cell(r, col["Kode Seri"] + 1).value
            if not seri:
                continue
            taut = str(ws.cell(r, col["Tautan / Rumus"] + 1).value or "")
            low = taut.lower()
            if low.startswith(("rumus:", "ref:", "dihitung sistem", "ikut ")) or " mengikuti item " in f" {low}":
                if seri in ("HARGA",) and low.startswith("rumus:"):
                    ws.cell(r, col["Jangkar Tahun Dasar"] + 1).value = round(rnd.uniform(1000, 9000), 2)
                continue
            if seri in ("RKA", "R_MARGIN"):
                base, sk = rnd.uniform(0.1, 0.6), 0.01
            elif seri in ("IH", "INDEKS"):
                base, sk = rnd.uniform(80, 120), 1.0
            elif seri == "TPK":
                base, sk = rnd.uniform(30, 70), 1.0
            else:
                base, sk = rnd.uniform(100, 5000), base_skala(seri)
            mulai = rnd.choice([(2019, 1), (2019, 1), (2019, 1), (2021, 1), (2022, 3)])
            for i, (y, q) in per.items():
                if (y, q) > batas or (y, q) < mulai:
                    continue
                if seri.startswith("BASE_") and str(y) != baseline:
                    continue
                if rnd.random() < 0.03:
                    continue  # sel kosong (kosong != nol)
                _sel_angka(ws, r, i, round(base * (1 + sk * 0.01 * rnd.uniform(-5, 8)), 6))
            if seri in ("RKA", "IH", "HARGA", "R_MARGIN") and rnd.random() < (0.9 if td2010 else 0.5):
                j = {"RKA": rnd.uniform(0.1, 0.6), "IH": 100.0, "HARGA": rnd.uniform(1, 50),
                     "R_MARGIN": rnd.uniform(0.05, 0.2)}[seri]
                ws.cell(r, col["Jangkar Tahun Dasar"] + 1).value = round(j, 6)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def base_skala(seri: str) -> float:
    return 5.0 if seri in ("KUANTUM", "OUT_ADHB", "NTB_ADHB", "V_IMPOR") else 1.0
