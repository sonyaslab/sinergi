"""Adaptor format "spek" netral (engine_ref/kompilasi.py) ke mesin produksi, dari LK 01 (.xlsm) dan templat terisi.

Dipakai golden test (sintetis dan data rahasia di golden/). Tidak mencetak angka.
"""
from __future__ import annotations

import math
import re
from collections import defaultdict
from typing import Any

from sinergi_api.engine import DataLapus, Empat, Item, KonfigTD, Lapus, MasukanWilayah, Penyesuaian, Sumbu, Tautan, urut

URUT0 = 2019 * 4  # t engine_ref = urut - URUT0
RX_P = re.compile(r"^(\d{4})-T([1-4])$")


# ------------------------------------------------------------------ spek -> mesin produksi
def ke_masukan(spec: dict) -> MasukanWilayah:
    pohon = [Lapus(r["id"], r["kode"], r["jenis"], r.get("induk"), r["urutan"], bool(r.get("is_migas")),
                   tuple(r.get("anggota", []))) for r in spec["pohon"]]
    data = {}
    for lid, d in spec["data"].items():
        item = [Item(i["id"], i["metode"], i.get("jenis_indeks"),
                     {k: {u: float(x) for u, x in s.items() if x is not None} for k, s in i.get("seri", {}).items()},
                     {k: float(x) for k, x in i.get("parameter", {}).items() if x is not None},
                     tuple(Tautan(t["jenis_seri"], t["sumber"], t.get("rumus"), t.get("seri_ref"),
                                  tuple(t.get("lapus_sumber") or ()), t.get("besaran"), float(t.get("faktor", 1.0)))
                           for t in i.get("tautan", [])),
                     i.get("mulai"), i.get("selesai")) for i in d.get("item", [])]
        adj = [Penyesuaian(a["tahap"], a["jenis"], a["harga"], a["periode"], float(a["nilai"]), a.get("metode"))
               for a in d.get("penyesuaian", [])]
        data[lid] = DataLapus(item, adj)
    return MasukanWilayah(KonfigTD(spec["tahun_baseline"], spec["jangkar_dari_data"]),
                          Sumbu(spec["awal"], spec["akhir"]), pohon, data,
                          {k: {u: float(x) for u, x in s.items()} for k, s in spec.get("referensi", {}).items()})


def pohon_datar(kode_lapus: list[str], jenis: dict[str, str] | None = None) -> list[dict]:
    """Pohon sederhana: tiap lapus = daun akar (cukup untuk membandingkan BENC per lapus)."""
    jenis = jenis or {}
    return [{"id": i + 1, "kode": k, "jenis": jenis.get(k, "daun"), "induk": None, "urutan": i + 1}
            for i, k in enumerate(kode_lapus)]


def kode_sumber(data: dict[str, dict]) -> set[str]:
    """Kode lapus yang dirujuk tautan (MARGIN/HASIL); lapus sumber tanpa data tetap perlu baris pohon (bernilai 0)."""
    return {x for d in data.values() for it in d["item"] for t in it.get("tautan", [])
            for x in (t.get("lapus_sumber") or []) if isinstance(x, str)}


def petakan_lapus_sumber(data: dict[str, dict], ids: dict[str, int]) -> None:
    """Ganti kode lapus sumber tautan (dari templat) dengan id pohon spek, di tempat."""
    for d in data.values():
        for it in d["item"]:
            for t in it.get("tautan", []):
                if t.get("lapus_sumber"):
                    t["lapus_sumber"] = [ids[x] if isinstance(x, str) else x for x in t["lapus_sumber"]]


# ------------------------------------------------------------------ perbandingan
def selisih_relatif(a: float, b: float) -> float:
    if math.isnan(a) or math.isnan(b):
        return 0.0 if math.isnan(a) and math.isnan(b) else math.inf
    return abs(a - b) / max(abs(a), abs(b), 1.0)


def terburuk(prod: Empat, ref: Any, sb: Sumbu, awal: int, akhir: int) -> float:
    """Selisih relatif maksimum 4 seri utama pada periode [awal, akhir]; ref = Hasil engine_ref (indeks t)."""
    w = 0.0
    for a in ("out_cp", "gva_cp", "out_k", "gva_k"):
        x, y = getattr(prod, a), getattr(ref, a)
        for u in range(awal, akhir + 1):
            w = max(w, selisih_relatif(x[sb.i(u)], y[u - URUT0]))
    return w


# ------------------------------------------------------------------ LK 01 (objek engine_ref) -> spek
def _ke_urut(s: dict | None) -> dict[int, float]:
    return {t + URUT0: float(x) for t, x in (s or {}).items()
            if isinstance(x, int | float) and not isinstance(x, bool)}


def _num(x: Any) -> bool:
    return isinstance(x, int | float) and not isinstance(x, bool)


def data_dari_lk(d: dict, rekon: Any, id_awal: int = 1) -> dict:
    """d = per_ind[lapus] dari tools.lk_xlsm_reader.baca_lk; rekon = AdjRekon. Kembalikan data lapus spek."""
    items, iid = [], id_awal
    for it in d["rev"].values():
        items.append({"id": iid, "metode": "REV", "seri": {"KUANTUM": _ke_urut(it.P), "HARGA": _ke_urut(it.H),
                                                          "RKA": _ke_urut(it.RKA)},
                      "parameter": {k: x for k, x in (("RKA_TD", it.RKA_TD), ("H_TD", it.H_TD)) if _num(x)}})
        iid += 1
    t0 = [URUT0 + 24 + q for q in range(4)]  # 2025
    for it in d["eks"].values():
        jenis = {"INDEKS PRODUKSI": "IP", "INDEKS BERLAKU": "IB"}.get((it.jenis or "").strip().upper())
        items.append({"id": iid, "metode": "EKS", "jenis_indeks": jenis,
                      "seri": {"INDEKS": _ke_urut(it.I), "IH": _ke_urut(it.IH), "RKA": _ke_urut(it.RKA),
                               "BASE_ADHB": {u: float(x) for u, x in zip(t0, it.base_cp, strict=True) if _num(x)},
                               "BASE_ADHK": {u: float(x) for u, x in zip(t0, it.base_k, strict=True) if _num(x)}},
                      "parameter": {k: x for k, x in (("RKA_TD", it.RKA_TD), ("IH_TD", it.IH_TD)) if _num(x)}})
        iid += 1
    for it in d["def"].values():
        items.append({"id": iid, "metode": "DEF",
                      "seri": {"OUT_ADHB": _ke_urut(it.OUT_CP), "NTB_ADHB": _ke_urut(it.GVA_CP), "IH": _ke_urut(it.IH),
                               "RKA": _ke_urut(it.RKA)},
                      "parameter": {k: x for k, x in (("RKA_TD", it.RKA_TD), ("IH_TD", it.IH_TD)) if _num(x)}})
        iid += 1
    adj = []
    peta_m = {"cp_adj1": ("ADJ1", "CP"), "cp_adj2": ("ADJ2", "CP"), "cp_sc": ("SC", "CP"),
              "k_adj1": ("ADJ1", "K"), "k_adj2": ("ADJ2", "K"), "k_sc": ("SC", "K")}
    for m in ("rev", "eks", "def"):
        for atr, (jenis, harga) in peta_m.items():
            for u, x in _ke_urut(getattr(d["adj"][m], atr)).items():
                adj.append({"tahap": "METODE", "metode": m.upper(), "jenis": jenis, "harga": harga, "periode": u,
                            "nilai": x})
    peta_r = {"out_cp_adj3": ("ADJ3", "CP"), "out_cp_adj4": ("ADJ4_OUTPUT", "CP"), "gva_cp_adj4": ("ADJ4_NTB", "CP"),
              "out_k_adj3": ("ADJ3", "K"), "out_k_adj4": ("ADJ4_OUTPUT", "K"), "gva_k_adj4": ("ADJ4_NTB", "K")}
    for atr, (jenis, harga) in peta_r.items():
        for u, x in _ke_urut(getattr(rekon, atr)).items():
            adj.append({"tahap": "REKON", "jenis": jenis, "harga": harga, "periode": u, "nilai": x})
    return {"item": items, "penyesuaian": adj}


# ------------------------------------------------------------------ templat terisi -> spek
def _label_urut(lbl: str) -> int:
    m = RX_P.match(lbl)
    assert m, lbl
    return urut(int(m.group(1)), int(m.group(2)))


def _baca_blok(path: str, sheet: str, kunci: list[str]) -> list[tuple[dict, dict[int, float]]]:
    import openpyxl

    wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
    if sheet not in wb.sheetnames:
        return []
    rows = wb[sheet].iter_rows(min_row=4, values_only=True)
    hd = list(next(rows))
    col = {h: i for i, h in enumerate(hd) if h}
    per = {i: _label_urut(f"{m.group(1)}-T{m.group(2)}") for i, h in enumerate(hd)
           if isinstance(h, str) and (m := RX_P.match(h))}
    out = []
    for r in rows:
        if not r or not r[col[kunci[0]]]:
            continue
        meta = {k: r[col[k]] for k in kunci if k in col}
        nilai = {u: float(r[i]) for i, u in per.items() if _num(r[i])}
        out.append((meta, nilai))
    return out


def spek_dari_templat(path: str, tahun_baseline: int, jangkar_dari_data: bool) -> tuple[dict[str, dict], dict]:
    """Kembalikan ({wilayah: data_per_kode_lapus}, info) dari templat terisi (pembaca rujukan tools/baca_templat).

    data_per_kode_lapus = {kode_lapus: {"item": [...], "penyesuaian": [...]}}; referensi per wilayah di info.
    Tautan dari kolom "Tautan / Rumus" (tata bahasa sinergi_api.impor.tautan): REF -> SERI_REFERENSI; RUMUS/MARGIN ->
    RUMUS; HASIL -> HASIL_LAPUS (lapus_sumber berisi KODE lapus; petakan ke id sebelum hitung); "ikut item lain" ->
    seri item sumber disalin (setara seri referensi, keputusan 5). Baris rumus/tautan tidak dibaca nilainya. TD tanpa
    jangkar_dari_data: IH bersatuan "2010=100" tanpa jangkar = 100 (keputusan 3).
    """
    from tools.baca_templat import baca

    from sinergi_api.impor import tautan as tt

    items, pesan = baca(path)
    per_wil: dict[str, dict[str, dict]] = defaultdict(lambda: defaultdict(lambda: {"item": [], "penyesuaian": []}))
    nomor = 0
    urutan = sorted(items.items(), key=lambda kv: (str(kv[0][0]), str(kv[0][1]), str(kv[0][2]), int(kv[0][3] or 0)))
    spek_item: dict[tuple, dict] = {}
    nama_item: dict[tuple, str] = {}
    ikut: list[tuple[tuple, str, Any]] = []  # (kunci item pengikut, seri, TautanTeks)
    for (wil, lapus, metode, _no), it in urutan:
        if metode not in ("REV", "EKS", "DEF"):
            continue
        nomor += 1
        seri, par, taut = {}, {}, []
        margin = None
        for kode, s in it["seri"].items():
            t = tt.urai(s.get("tautan"), kode, metode)
            abaikan = t is not None and t.nilai_diabaikan
            seri[kode] = {} if abaikan else {_label_urut(p): x for p, x in s["nilai"].items()}
            j = s.get("jangkar")
            kp = {"RKA": "RKA_TD", "HARGA": "H_TD", "IH": "IH_TD", "R_MARGIN": "R_MARGIN_TD"}.get(kode, kode)
            if _num(j):
                par[kp] = j
            elif kode == "IH" and not jangkar_dari_data and "2010=100" in str(s.get("satuan") or "").replace(" ", ""):
                par[kp] = 100.0
            if t is None or t.jenis in ("KETERANGAN", "HITUNG_SISTEM"):
                continue
            if t.jenis == "REF":
                taut.append({"jenis_seri": kode, "sumber": "SERI_REFERENSI", "seri_ref": t.seri_ref,
                             "faktor": t.faktor})
            elif t.jenis == "RUMUS":
                taut.append({"jenis_seri": kode, "sumber": "RUMUS", "rumus": t.rumus, "faktor": t.faktor})
            elif t.jenis == "MARGIN":
                margin = {"jenis_seri": "OUT_ADHB", "sumber": "RUMUS", "rumus": t.rumus, "lapus_sumber": list(t.lapus),
                          "faktor": t.faktor}
            elif t.jenis == "HASIL":
                taut.append({"jenis_seri": kode, "sumber": "HASIL_LAPUS", "lapus_sumber": list(t.lapus),
                             "besaran": t.besaran, "faktor": t.faktor})
            elif t.jenis == "IKUT":
                ikut.append(((str(wil), str(lapus), metode, int(_no)), kode, t))
        if margin is not None:
            seri["OUT_ADHB"] = {}
            taut.append(margin)
        spek = {"id": nomor, "metode": metode, "jenis_indeks": it.get("jenis_indeks"), "seri": seri, "parameter": par,
                "tautan": taut}
        kunci = (str(wil), str(lapus), metode, int(_no))
        spek_item[kunci] = spek
        nama_item[kunci] = " ".join(str(it["nama"]).split()).lower()
        per_wil[str(wil)][str(lapus)]["item"].append(spek)
    for kp_, kode, t in ikut:
        cocok = [k for k in spek_item if k[0] == kp_[0] and k != kp_ and (
            (t.ikut_kode and f"{k[1].replace('.', '').upper()}{k[3]:02d}" == t.ikut_kode) or
            (t.ikut_nama and k[1] == kp_[1] and nama_item[k] == t.ikut_nama.lower()))]
        if len(cocok) > 1:
            cocok = [k for k in cocok if k[2] == kp_[2]] or cocok
        assert len(cocok) == 1, (t, cocok)
        seri_s = t.ikut_seri or kode
        spek_item[kp_]["seri"][seri_s] = dict(spek_item[cocok[0]]["seri"].get(seri_s, {}))
    kol = ["Kode Wilayah", "Kode Lapus", "Tahap", "Metode", "Jenis", "Harga"]
    for meta, nilai in _baca_blok(path, "PENYESUAIAN", kol):
        for u, x in nilai.items():
            per_wil[str(meta["Kode Wilayah"])][str(meta["Kode Lapus"])]["penyesuaian"].append(
                {"tahap": meta["Tahap"], "metode": meta.get("Metode") or None, "jenis": meta["Jenis"],
                 "harga": meta["Harga"], "periode": u, "nilai": x})
    referensi: dict[str, dict] = defaultdict(dict)
    for meta, nilai in _baca_blok(path, "SERI_REFERENSI", ["Kode Wilayah", "Kode Referensi"]):
        if meta.get("Kode Referensi"):
            referensi[str(meta["Kode Wilayah"])][meta["Kode Referensi"]] = nilai
    return ({w: dict(d) for w, d in per_wil.items()},
            {"referensi": dict(referensi), "pesan": pesan, "tahun_baseline": tahun_baseline,
             "jangkar_dari_data": jangkar_dari_data})
