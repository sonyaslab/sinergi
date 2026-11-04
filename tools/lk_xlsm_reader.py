"""
Pembaca LK Excel "01 LK PDRB Triwulanan TD2025" (.xlsm) -> struktur engine_ref.
Dipakai untuk (1) validasi engine vs angka LK, (2) migrasi data historis 2019+.
Jalankan HANYA di mesin internal BPS; file LK bersifat RAHASIA.
"""
from __future__ import annotations

import re
import sys
from collections import defaultdict
from pathlib import Path

import openpyxl

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from engine_ref.lk_engine import (ItemREV, ItemEKS, ItemDEF, AdjMetode, AdjRekon,  # noqa: E402
                                  TAHUN_AWAL, TAHUN_AKHIR, t_of)

RX_Q = re.compile(r"^Q([1-4])-(\d{4})$")


def _period_map(hdr1, hdr2, start=8):
    """kolom -> ('Q', t) atau ('Y', tahun) untuk lembar DATA_*."""
    m = {}
    year = None
    for j in range(start, len(hdr2)):
        h = hdr2[j]
        if isinstance(h, str) and RX_Q.match(h):
            q, y = RX_Q.match(h).groups()
            year = int(y)
            if TAHUN_AWAL <= year <= TAHUN_AKHIR:
                m[j] = ("Q", t_of(year, int(q)))
        else:
            y1 = hdr1[j] if j < len(hdr1) else None
            if isinstance(y1, str) and y1.startswith("Y-"):
                m[j] = ("Y", int(y1[2:]))
            elif year is not None:
                m[j] = ("Y", year)
    return m


def _read_data_sheet(ws):
    rows = ws.iter_rows(values_only=True)
    hdr1 = list(next(rows)); hdr2 = list(next(rows))
    pm = _period_map(hdr1, hdr2)
    out = []
    for row in rows:
        if not row or not row[0]:
            continue
        row = list(row) + [None] * (len(hdr2) - len(row))
        q, y = {}, {}
        for j, (kind, key) in pm.items():
            val = row[j]
            if val is None or val == "":
                continue
            (q if kind == "Q" else y)[key] = val
        out.append(dict(key=row[0], wil=str(row[1]), ind=str(row[2]), kode=str(row[3]),
                        rincian=row[4], kol6=row[5], sumber=row[6], kol8=row[7], q=q, y=y, raw=row))
    return out


def _split_kode(kode: str, ind: str):
    """'P_A.1.a_001' -> ('P','001'); 'OUT.CP.PR.ADJ1_A.1.a' -> ('OUT.CP.PR.ADJ1', None)."""
    tag = f"_{ind}"
    if tag in kode:
        pre, post = kode.split(tag, 1)
        return pre, (post[1:] if post.startswith("_") else None)
    return kode, None


def baca_lk(path: str, wil: str = "6500"):
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    data = {sh: _read_data_sheet(wb[sh]) for sh in ("DATA_REV", "DATA_EKS", "DATA_DEF") if sh in wb.sheetnames}
    per_ind = defaultdict(lambda: {"rev": {}, "eks": {}, "def": {}, "adj": {"rev": AdjMetode(), "eks": AdjMetode(), "def": AdjMetode()}, "meta": []})

    adj_map = {"OUT.CP.PR.ADJ1": "cp_adj1", "OUT.CP.PR.ADJ2": "cp_adj2", "OUT.CP.SC": "cp_sc",
               "OUT.FBY.PR.ADJ1": "k_adj1", "OUT.FBY.PR.ADJ2": "k_adj2", "OUT.FBY.SC": "k_sc"}

    for sh, rows in data.items():
        m = {"DATA_REV": "rev", "DATA_EKS": "eks", "DATA_DEF": "def"}[sh]
        for r in rows:
            if r["wil"] != wil:
                continue
            ind = r["ind"]; pre, nnn = _split_kode(r["kode"], ind)
            d = per_ind[ind]
            if pre in adj_map:
                setattr(d["adj"][m], adj_map[pre], r["q"]); continue
            if nnn is None:
                continue  # baris agregat / turunan
            items = d[m]
            if m == "rev":
                it = items.setdefault(nnn, ItemREV(nama=""))
                if pre == "P":
                    it.nama = r["rincian"] or ""; it.P = r["q"]
                    d["meta"].append(("REV", nnn, r["rincian"], r["kol6"], r["sumber"], r["kol8"]))
                elif pre == "H": it.H = r["q"]
                elif pre == "r.IC.CP": it.RKA = r["q"]; it.RKA_TD = r["y"].get(2025)
            elif m == "eks":
                it = items.setdefault(nnn, ItemEKS(nama=""))
                if pre in ("IPB", "IP", "IB"):
                    it.nama = r["rincian"] or ""; it.I = r["q"]; it.jenis = (r["kol6"] or "")
                    it.bobot = r["kol8"] if isinstance(r["kol8"], (int, float)) else None
                    d["meta"].append(("EKS", nnn, r["rincian"], r["kol6"], r["sumber"], r["kol8"]))
                elif pre == "DEF": it.IH = r["q"]
                elif pre == "OUT.BASE":
                    raw = r["raw"]; it.base_cp = raw[8:12]; it.base_k = raw[13:17]
                elif pre == "r.IC.CP": it.RKA = r["q"]; it.RKA_TD = r["y"].get(2025)
            else:
                it = items.setdefault(nnn, ItemDEF(nama=""))
                if pre == "OUT.CP":
                    it.nama = r["rincian"] or ""; it.OUT_CP = r["q"]
                    d["meta"].append(("DEF", nnn, r["rincian"], r["kol6"], r["sumber"], r["kol8"]))
                elif pre == "GVA.CP": it.GVA_CP = r["q"]
                elif pre == "DEF": it.IH = r["q"]

    tersimpan = {}
    for name in wb.sheetnames:
        if not name.startswith(wil + "_"):
            continue
        ind = name[len(wil) + 1:]
        ws = wb[name]
        rows = list(ws.iter_rows(min_row=7, max_row=28, values_only=True))
        hdr = rows[0]
        cols = {}
        for j, h in enumerate(hdr):
            if isinstance(h, str) and RX_Q.match(h):
                q, y = RX_Q.match(h).groups(); cols[j] = t_of(int(y), int(q))
        rec = {}
        for row in rows[1:]:
            kode = row[5]
            if isinstance(kode, str) and kode not in ("KET",):
                rec[kode] = {t: row[j] for j, t in cols.items() if isinstance(row[j], (int, float))}
        tersimpan[ind] = rec
    return per_ind, tersimpan


def adj_rekon_dari_tersimpan(rec: dict) -> AdjRekon:
    g = lambda k: rec.get(k, {})
    return AdjRekon(out_cp_adj3=g("OUT.CP.ADJ3"), out_cp_adj4=g("OUT.CP.ADJ4"), gva_cp_adj4=g("GVA.CP.ADJ4"),
                    out_k_adj3=g("OUT.FBY.ADJ3"), out_k_adj4=g("OUT.FBY.ADJ4"), gva_k_adj4=g("GVA.FBY.ADJ4"))
