"""Pemeriksaan golden yang dipakai bersama oleh test_golden.py (data rahasia golden/) dan test_golden_alur.py (data
palsu). Laporan hanya memuat kode lapus, jumlah, dan selisih relatif; tidak pernah angka PDRB.

Isi folder golden/ (hanya di mesin internal, tidak di-commit):

    golden/
      manifest.json                       (opsional, lihat MANIFEST_CONTOH)
      lk01/*.xlsm                         LK 01 TD2025 Put 0 per berkas operator
      Templat_Data_Dasar_TD2025_TERISI.xlsx
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from engine_ref import kompilasi as kp
from engine_ref.lk_engine import Hasil, hitung_industri
from tools.lk_xlsm_reader import adj_rekon_dari_tersimpan, baca_lk

from sinergi_api.engine import Empat, hitung_wilayah, urut

from .adaptor import URUT0, data_dari_lk, ke_masukan, pohon_datar, selisih_relatif, spek_dari_templat

MANIFEST_CONTOH = {
    "wilayah": "6500",
    "periode": ["2019-T1", "2026-T2"],
    "lk01": {"A.1.a": "lk01/LK01_operator_A.xlsm", "TUV.1": "lk01/LK01_operator_B.xlsm"},
    "templat_td2025": "Templat_Data_Dasar_TD2025_TERISI.xlsx",
    "tersimpan_usang": ["B.3"],
    "templat_beda_lk": [],
    "harap_identik": 72,
}
SERI_SIMPAN = (("OUT.CP.BENC", "out_cp"), ("GVA.CP.BENC", "gva_cp"), ("OUT.FBY.BENC", "out_k"),
               ("GVA.FBY.BENC", "gva_k"))


@dataclass
class Laporan:
    nama: str
    identik: list[str] = field(default_factory=list)
    beda: dict[str, str] = field(default_factory=dict)  # lapus -> "seri@periode rel=..."

    def catat(self, lapus: str, rel: float, letak: str, tol: float) -> None:
        if rel <= tol:
            self.identik.append(lapus)
        else:
            self.beda[lapus] = f"{letak} rel={rel:.1e}"

    def ringkas(self) -> str:
        n = len(self.identik) + len(self.beda)
        teks = f"{self.nama}: identik {len(self.identik)}/{n}"
        if self.beda:
            teks += "; berbeda: " + ", ".join(f"{k} ({v})" for k, v in sorted(self.beda.items()))
        return teks


def baca_manifest(golden: Path) -> dict:
    p = golden / "manifest.json"
    return json.loads(p.read_text()) if p.is_file() else {}


def rentang(manifest: dict) -> tuple[int, int]:
    a, b = manifest.get("periode", ["2019-T1", "2026-T2"])
    return urut(int(a[:4]), int(a[-1])), urut(int(b[:4]), int(b[-1]))


def _label(u: int) -> str:
    return f"{u // 4}-T{u % 4 + 1}"


def _bandingkan(prod: Empat | None, ref: Hasil, sb, awal: int, akhir: int) -> tuple[float, str]:
    w, letak = 0.0, "-"
    for a in ("out_cp", "gva_cp", "out_k", "gva_k"):
        y = getattr(ref, a)
        for u in range(awal, akhir + 1):
            x = getattr(prod, a)[sb.i(u)] if prod is not None else 0.0
            r = selisih_relatif(x, y[u - URUT0])
            if r > w:
                w, letak = r, f"{a}@{_label(u)}"
    return w, letak


def _hitung_lk(d: dict, rekon, awal: int, akhir: int):
    """Mesin produksi pada satu lapus LK 01 -> (Empat BENC atau None, sumbu)."""
    spec = {"tahun_baseline": 2025, "jangkar_dari_data": True, "awal": awal, "akhir": akhir,
            "pohon": pohon_datar(["X"]), "referensi": {}, "data": {1: data_dari_lk(d, rekon)}}
    h = hitung_wilayah(ke_masukan(spec))
    return (h.lapus[1].tahap["BENC"] if 1 in h.lapus else None), h.sumbu


def lk01_vs_oracle(path: Path, wil: str, awal: int, akhir: int, tol: float = 1e-9) -> Laporan:
    """Setiap lapus di berkas LK 01: mesin produksi vs engine_ref pada data yang sama."""
    lap = Laporan(f"mesin vs engine_ref [{path.name}]")
    per_ind, tersimpan = baca_lk(str(path), wil)
    for ind in sorted(per_ind):
        d = per_ind[ind]
        rek = adj_rekon_dari_tersimpan(tersimpan.get(ind, {}))
        ref = hitung_industri(list(d["rev"].values()), list(d["eks"].values()), list(d["def"].values()),
                              d["adj"]["rev"], d["adj"]["eks"], d["adj"]["def"], rek)
        prod, sb = _hitung_lk(d, rek, awal, akhir)
        lap.catat(ind, *_bandingkan(prod, ref, sb, awal, akhir), tol)
    return lap


def lk01_vs_tersimpan(golden: Path, manifest: dict, awal: int, akhir: int, tol: float = 1e-6) -> Laporan:
    """Lapus menurut rekap LK 02 (manifest lk01): mesin produksi vs hasil simpan lembar {wil}_{lapus} (BENC)."""
    wil = str(manifest.get("wilayah", "6500"))
    usang = set(manifest.get("tersimpan_usang", []))
    lap = Laporan("mesin vs hasil simpan LK 01")
    cache: dict[str, tuple] = {}
    for ind, berkas in sorted(manifest["lk01"].items()):
        if berkas not in cache:
            cache[berkas] = baca_lk(str(golden / berkas), wil)
        per_ind, tersimpan = cache[berkas]
        if ind in usang:
            continue
        if ind not in per_ind or ind not in tersimpan:
            lap.beda[ind] = "tidak ada di berkas"
            continue
        rek = adj_rekon_dari_tersimpan(tersimpan[ind])
        prod, sb = _hitung_lk(per_ind[ind], rek, awal, akhir)
        w, letak = 0.0, "-"
        for kode, a in SERI_SIMPAN:
            simpan = tersimpan[ind].get(kode, {})
            for u in range(awal, akhir + 1):
                x = getattr(prod, a)[sb.i(u)] if prod is not None else 0.0
                y = simpan.get(u - URUT0, 0.0) or 0.0
                r = abs(x - y) / max(abs(y), 1.0)  # sama dengan tools/validasi_engine_vs_lk.py
                if r > w:
                    w, letak = r, f"{kode}@{_label(u)}"
        lap.catat(ind, w, letak, tol)
    return lap


def _spek_templat(path: Path, wil: str, awal: int, akhir: int) -> tuple[dict, dict[int, str]]:
    per_wil, info = spek_dari_templat(str(path), 2025, True)
    data = per_wil.get(wil, {})
    kode = sorted(data)
    pohon = pohon_datar(kode, {"TOP": "top", "SOP": "sop"})
    ids = {r["kode"]: r["id"] for r in pohon}
    spec = {"tahun_baseline": 2025, "jangkar_dari_data": True, "awal": awal, "akhir": akhir, "pohon": pohon,
            "referensi": info["referensi"].get(wil, {}), "data": {ids[k]: data[k] for k in kode}}
    return spec, {v: k for k, v in ids.items()}


def templat_vs_oracle(path: Path, wil: str, awal: int, akhir: int, tol: float = 1e-9) -> Laporan:
    """Templat terisi: mesin produksi vs oracle wilayah (engine_ref/kompilasi.py), semua tahap lapus."""
    lap = Laporan(f"templat: mesin vs engine_ref [{path.name}]")
    spec, kode = _spek_templat(path, wil, awal, akhir)
    ref = kp.hitung_wilayah(spec)
    h = hitung_wilayah(ke_masukan(spec))
    for lid, k in sorted(kode.items(), key=lambda kv: kv[1]):
        w, letak = 0.0, "-"
        for th in ("pre", "post", "benc", "final"):
            if lid in ref and th in ref[lid]:
                prod = h.lapus[lid].tahap[th.upper()] if lid in h.lapus else None
                r, lt = _bandingkan(prod, ref[lid][th], h.sumbu, awal, akhir)
                if r > w:
                    w, letak = r, f"{th}:{lt}"
        lap.catat(k, w, letak, tol)
    return lap


def kode_lk_templat(path: Path) -> dict[str, str]:
    """Kode lapus templat -> kode LK BPS (mis. T.1 -> TUV.1)."""
    import re

    import openpyxl

    wb = openpyxl.load_workbook(str(path), read_only=True, data_only=True)
    peta: dict[str, str] = {}
    for sh in wb.sheetnames:
        if not re.fullmatch(r"[A-V]", sh):
            continue
        rows = wb[sh].iter_rows(min_row=4, values_only=True)
        hd = list(next(rows))
        col = {h: i for i, h in enumerate(hd) if h}
        if "Kode LK BPS" not in col:
            continue
        for r in rows:
            if r and r[col["Kode Lapus"]] and r[col["Kode LK BPS"]]:
                peta[str(r[col["Kode Lapus"]])] = str(r[col["Kode LK BPS"]])
    return peta


def templat_vs_lk(golden: Path, manifest: dict, awal: int, akhir: int, tol: float = 1e-9) -> Laporan:
    """Templat terisi (mesin produksi) vs engine_ref atas data LK 01 per rekap LK 02: target 72/72 identik."""
    wil = str(manifest.get("wilayah", "6500"))
    path = golden / manifest["templat_td2025"]
    spec, kode = _spek_templat(path, wil, awal, akhir)
    ke_lk = kode_lk_templat(path)
    h = hitung_wilayah(ke_masukan(spec))
    lewati = set(manifest.get("templat_beda_lk", []))
    lap = Laporan("templat vs LK 01")
    cache: dict[str, tuple] = {}
    for lid, k in sorted(kode.items(), key=lambda kv: kv[1]):
        ind = ke_lk.get(k, k)
        if ind in lewati or ind not in manifest["lk01"]:
            continue
        berkas = manifest["lk01"][ind]
        if berkas not in cache:
            cache[berkas] = baca_lk(str(golden / berkas), wil)
        per_ind, tersimpan = cache[berkas]
        d = per_ind[ind]
        ref = hitung_industri(list(d["rev"].values()), list(d["eks"].values()), list(d["def"].values()),
                              d["adj"]["rev"], d["adj"]["eks"], d["adj"]["def"],
                              adj_rekon_dari_tersimpan(tersimpan.get(ind, {})))
        prod = h.lapus[lid].tahap["BENC"] if lid in h.lapus else None
        lap.catat(ind, *_bandingkan(prod, ref, h.sumbu, awal, akhir), tol)
    return lap
