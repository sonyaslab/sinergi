"""Uji alur golden dengan data PALSU: templat KOSONG TD2025 diisi angka acak, lalu dibuat berkas LK 01 tiruan
(tata letak DATA_REV/DATA_EKS/DATA_DEF + lembar hasil simpan) dari data yang sama. Memastikan pemeriksaan golden
(tests/golden/periksa.py) benar-benar berjalan sebelum dipakai pada data rahasia di mesin internal.
Semua berkas dibuat di direktori sementara (tidak pernah di repo)."""
from __future__ import annotations

import json
import random
import re
import shutil
from pathlib import Path

import openpyxl
import pytest
from engine_ref import kompilasi as kp
from engine_ref.lk_engine import TAHUN_AWAL, AdjMetode, AdjRekon, hitung_industri, t_base_tahun, t_of

from . import periksa as pk

pytestmark = pytest.mark.golden
ROOT = Path(__file__).resolve().parents[4]
KOSONG = ROOT / "templates" / "Templat_Data_Dasar_TD2025_KOSONG.xlsx"
RX_P = re.compile(r"^(\d{4})-T([1-4])$")
NQ_LK = 32  # Q1-2019 .. Q4-2026
RENTANG = {"BASE_ADHB": (100, 9000), "BASE_ADHK": (100, 9000), "KUANTUM": (10, 5000), "HARGA": (1, 300),
           "RKA": (0.0, 0.6), "INDEKS": (80, 150), "IH": (80, 150), "OUT_ADHB": (100, 9000), "NTB_ADHB": (50, 4000)}


def _isi_templat(tujuan: Path, rng: random.Random) -> None:
    wb = openpyxl.load_workbook(KOSONG)
    for sh in wb.sheetnames:
        if not re.fullmatch(r"[A-V]", sh):
            continue
        ws = wb[sh]
        hd = [c.value for c in ws[4]]
        col = {h: i + 1 for i, h in enumerate(hd) if h}
        per = {i + 1: (int(m.group(1)), int(m.group(2))) for i, h in enumerate(hd)
               if isinstance(h, str) and (m := RX_P.match(h))}
        for r in range(5, ws.max_row + 1):
            seri = ws.cell(r, col["Kode Seri"]).value
            if not ws.cell(r, col["Kode Wilayah"]).value or seri not in RENTANG:
                continue
            lo, hi = RENTANG[seri]
            for c, (y, _q) in per.items():
                if seri.startswith("BASE_") and y != 2025:
                    continue
                if rng.random() > 0.05:
                    ws.cell(r, c).value = round(rng.uniform(lo, hi), 6)
            if seri == "RKA":
                ws.cell(r, col["Jangkar Tahun Dasar"]).value = round(rng.uniform(0, 0.6), 6)
    ws = wb["PENYESUAIAN"]
    hd = [c.value for c in ws[4]]
    col = {h: i + 1 for i, h in enumerate(hd) if h}
    for r, (lap, tahap, met, jenis, harga, per) in enumerate(
            [("A.1.a", "METODE", "REV", "ADJ1", "CP", "2025-T2"), ("C.2.1", "REKON", None, "ADJ3", "K", "2024-T3"),
             ("D.1", "REKON", None, "ADJ4_NTB", "CP", "2026-T1")], start=5):
        for k, v in (("Kode Wilayah", "6500"), ("Kode Lapus", lap), ("Tahap", tahap), ("Metode", met),
                     ("Jenis", jenis), ("Harga", harga), ("Alasan", "penyesuaian uji alur golden"), (per, 25.5)):
            ws.cell(r, col[k]).value = v
    wb.save(tujuan)


def _baris(ws, r: int, meta: list, nilai: dict[int, float] | None = None, tahun: float | None = None) -> None:
    for j, x in enumerate(meta):
        ws.cell(r, j + 1).value = x
    for t, x in (nilai or {}).items():
        if 0 <= t < NQ_LK:
            ws.cell(r, 9 + t).value = x
    if tahun is not None:
        ws.cell(r, 9 + NQ_LK).value = tahun


def _tulis_lk(path: Path, lapus: list[tuple[str, dict]], usang: set[str]) -> None:
    """lapus = [(kode_lk, data_lapus_spek)] -> LK 01 tiruan yang dapat dibaca tools/lk_xlsm_reader.baca_lk."""
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    lembar, baris = {}, {}
    for nama in ("DATA_REV", "DATA_EKS", "DATA_DEF"):
        ws = wb.create_sheet(nama)
        _baris(ws, 1, [None] * 8)
        ws.cell(1, 9 + NQ_LK).value = "Y-2025"
        _baris(ws, 2, ["KEY", "WIL", "IND", "KODE", "RINCIAN", "KET", "SUMBER", "BOBOT"])
        for t in range(NQ_LK):
            ws.cell(2, 9 + t).value = f"Q{t % 4 + 1}-{TAHUN_AWAL + t // 4}"
        lembar[nama], baris[nama] = ws, 3
    tb = t_base_tahun(2025)
    spec0 = {"tahun_baseline": 2025, "jangkar_dari_data": True, "referensi": {}}
    pohon = kp.Pohon([])

    def tambah(nama: str, meta: list, nilai=None, tahun=None) -> None:
        _baris(lembar[nama], baris[nama], meta, nilai, tahun)
        baris[nama] += 1

    for ind, d in lapus:
        objs: dict[str, list] = {"REV": [], "EKS": [], "DEF": []}
        for it in d["item"]:
            seri, out_k = kp._selesaikan(it, spec0, pohon, {}, tb)
            objs[it["metode"]].append(kp._item_ref(it, seri, out_k, tb))
        for i, o in enumerate(objs["REV"], start=1):
            n = f"{i:03d}"
            tambah("DATA_REV", [f"k{ind}{n}P", "6500", ind, f"P_{ind}_{n}", o.nama], o.P)
            tambah("DATA_REV", [f"k{ind}{n}H", "6500", ind, f"H_{ind}_{n}", o.nama], o.H)
            tambah("DATA_REV", [f"k{ind}{n}R", "6500", ind, f"r.IC.CP_{ind}_{n}", o.nama], o.RKA, o.RKA_TD)
        for i, o in enumerate(objs["EKS"], start=1):
            n = f"{i:03d}"
            tambah("DATA_EKS", [f"k{ind}{n}I", "6500", ind, f"IP_{ind}_{n}", o.nama, o.jenis], o.I)
            tambah("DATA_EKS", [f"k{ind}{n}D", "6500", ind, f"DEF_{ind}_{n}", o.nama], o.IH)
            tambah("DATA_EKS", [f"k{ind}{n}B", "6500", ind, f"OUT.BASE_{ind}_{n}", o.nama],
                   {**dict(enumerate(o.base_cp)), **{5 + q: x for q, x in enumerate(o.base_k)}})
            tambah("DATA_EKS", [f"k{ind}{n}R", "6500", ind, f"r.IC.CP_{ind}_{n}", o.nama], o.RKA, o.RKA_TD)
        for i, o in enumerate(objs["DEF"], start=1):
            n = f"{i:03d}"
            tambah("DATA_DEF", [f"k{ind}{n}O", "6500", ind, f"OUT.CP_{ind}_{n}", o.nama], o.OUT_CP)
            tambah("DATA_DEF", [f"k{ind}{n}G", "6500", ind, f"GVA.CP_{ind}_{n}", o.nama], o.GVA_CP)
            tambah("DATA_DEF", [f"k{ind}{n}D", "6500", ind, f"DEF_{ind}_{n}", o.nama], o.IH)
        adj_m = {m: AdjMetode() for m in objs}
        adj_r = AdjRekon()
        for a in d["penyesuaian"]:
            t = a["periode"] - TAHUN_AWAL * 4
            if a["tahap"] == "METODE":
                getattr(adj_m[a["metode"]], kp.ATR_METODE[(a["jenis"], a["harga"])])[t] = a["nilai"]
                pre = {"ADJ1": "PR.ADJ1", "ADJ2": "PR.ADJ2", "SC": "SC"}[a["jenis"]]
                h = "CP" if a["harga"] == "CP" else "FBY"
                tambah(f"DATA_{a['metode']}", [f"k{ind}adj", "6500", ind, f"OUT.{h}.{pre}_{ind}"], {t: a["nilai"]})
            else:
                getattr(adj_r, kp.ATR_REKON[(a["jenis"], a["harga"])])[t] = a["nilai"]
        res = hitung_industri(objs["REV"], objs["EKS"], objs["DEF"], adj_m["REV"], adj_m["EKS"], adj_m["DEF"], adj_r)
        ws = wb.create_sheet(f"6500_{ind}")
        ws.cell(7, 6).value = "KODE"
        for t in range(NQ_LK):
            ws.cell(7, 7 + t).value = f"Q{t % 4 + 1}-{TAHUN_AWAL + t // 4}"
        simpan = {"OUT.CP.BENC": res.out_cp, "GVA.CP.BENC": res.gva_cp, "OUT.FBY.BENC": res.out_k,
                  "GVA.FBY.BENC": res.gva_k, "OUT.CP.ADJ3": adj_r.out_cp_adj3, "OUT.CP.ADJ4": adj_r.out_cp_adj4,
                  "GVA.CP.ADJ4": adj_r.gva_cp_adj4, "OUT.FBY.ADJ3": adj_r.out_k_adj3, "OUT.FBY.ADJ4": adj_r.out_k_adj4,
                  "GVA.FBY.ADJ4": adj_r.gva_k_adj4}
        for r, (kode, s) in enumerate(simpan.items(), start=8):
            ws.cell(r, 6).value = kode
            vals = s if isinstance(s, list) else [s.get(t) for t in range(NQ_LK)]
            for t in range(NQ_LK):
                x = vals[t]
                if x is not None:
                    ws.cell(r, 7 + t).value = x * (1.5 if ind in usang and kode.endswith("BENC") else 1)
    wb.save(path)


@pytest.fixture(scope="module")
def golden_palsu(tmp_path_factory) -> Path:
    g = tmp_path_factory.mktemp("golden")
    rng = random.Random(2026)  # noqa: S311 - angka uji, bukan kriptografi
    templat = g / "Templat_Data_Dasar_TD2025_TERISI.xlsx"
    _isi_templat(templat, rng)
    spec, kode = pk._spek_templat(templat, "6500", t_of(2019, 1) + TAHUN_AWAL * 4, t_of(2026, 2) + TAHUN_AWAL * 4)
    ke_lk = pk.kode_lk_templat(templat)
    lapus = [(ke_lk.get(k, k), spec["data"][lid]) for lid, k in sorted(kode.items(), key=lambda kv: kv[1])]
    (g / "lk01").mkdir()
    _tulis_lk(g / "lk01" / "LK01_A.xlsm", lapus[0::2], {"B.3"})
    _tulis_lk(g / "lk01" / "LK01_B.xlsm", lapus[1::2], {"B.3"})
    peta = {ind: f"lk01/LK01_{'A' if i % 2 == 0 else 'B'}.xlsm" for i, (ind, _) in enumerate(lapus)}
    manifest = {"wilayah": "6500", "periode": ["2019-T1", "2026-T2"], "lk01": peta,
                "templat_td2025": templat.name, "tersimpan_usang": ["B.3"], "harap_identik": len(lapus)}
    (g / "manifest.json").write_text(json.dumps(manifest))
    return g


def test_alur_golden_palsu_lulus(golden_palsu):
    m = pk.baca_manifest(golden_palsu)
    awal, akhir = pk.rentang(m)
    assert m["harap_identik"] == 73
    for b in sorted((golden_palsu / "lk01").glob("*.xlsm")):
        lap = pk.lk01_vs_oracle(b, "6500", awal, akhir)
        assert not lap.beda and len(lap.identik) >= 36, lap.ringkas()
    lap = pk.lk01_vs_tersimpan(golden_palsu, m, awal, akhir)
    assert not lap.beda and len(lap.identik) == 72, lap.ringkas()
    lap = pk.templat_vs_oracle(golden_palsu / m["templat_td2025"], "6500", awal, akhir)
    assert not lap.beda and len(lap.identik) == 73, lap.ringkas()
    lap = pk.templat_vs_lk(golden_palsu, m, awal, akhir)
    assert not lap.beda and len(lap.identik) == 73, lap.ringkas()


def test_alur_golden_peka_terhadap_selisih(golden_palsu, tmp_path):
    m = pk.baca_manifest(golden_palsu)
    m["tersimpan_usang"] = []
    lap = pk.lk01_vs_tersimpan(golden_palsu, m, *pk.rentang(m))
    assert list(lap.beda) == ["B.3"] and "rel=" in lap.ringkas()
    salinan = tmp_path / "g"
    shutil.copytree(golden_palsu, salinan)
    wb = openpyxl.load_workbook(salinan / m["templat_td2025"])
    ws = wb["A"]
    hd = [c.value for c in ws[4]]
    c = hd.index("2025-T1") + 1
    for r in range(5, ws.max_row + 1):
        if ws.cell(r, 2).value == "A.1.a" and ws.cell(r, 6).value == "KUANTUM":
            ws.cell(r, c).value = (ws.cell(r, c).value or 0) + 1000
            break
    wb.save(salinan / m["templat_td2025"])
    lap = pk.templat_vs_lk(salinan, m, *pk.rentang(m))
    assert list(lap.beda) == ["A.1.a"] and lap.beda["A.1.a"].startswith(("out_", "gva_"))
