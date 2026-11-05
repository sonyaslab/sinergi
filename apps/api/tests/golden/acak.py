"""Pembangkit wilayah acak (format spek) untuk golden sintetis: semua metode, jangkar, tautan, rumus turunan,
masa berlaku, penyesuaian tiga tahap, TOP/SOP, kelompok, dan migas. Angka acak, bukan data nyata."""
from __future__ import annotations

import random

from sinergi_api.engine import urut

POHON = [
    # id, kode, jenis, induk, is_migas, anggota
    (1, "A", "kategori", None, False, ()),
    (2, "A.1", "sub", 1, False, ()),
    (3, "A.1.a", "daun", 2, False, ()),
    (4, "A.1.b", "daun", 2, False, ()),
    (5, "A.2", "daun", 1, False, ()),
    (6, "B", "kategori", None, False, ()),
    (7, "B.1", "sub", 6, True, ()),        # sub migas: anaknya juga migas -> tidak dihitung ganda
    (8, "B.1.a", "daun", 7, True, ()),
    (9, "B.2", "daun", 6, False, ()),
    (10, "C.1", "daun", None, True, ()),
    (11, "G", "daun", None, False, ()),
    (12, "I", "daun", None, False, ()),
    (13, "BC", "kelompok", None, False, (6, 10)),
    (14, "NTB", "ntb", None, False, ()),
    (15, "TOP", "top", None, False, ()),
    (16, "SOP", "sop", None, False, ()),
    (17, "TOP.SOP", "topsop", None, False, ()),
    (18, "PDRB", "pdrb", None, False, ()),
    (19, "PDRB.NM", "pdrb_nonmigas", None, False, ()),
]
DATA = [3, 4, 5, 8, 9, 10, 11, 12, 15, 16]


def _seri(rng: random.Random, us: list[int], lo: float, hi: float, kosong: float = 0.12) -> dict[int, float]:
    out = {}
    for u in us:
        r = rng.random()
        if r < kosong:
            continue
        out[u] = 0.0 if r < kosong + 0.02 else rng.uniform(lo, hi)
    return out


def wilayah(seed: int) -> dict:
    rng = random.Random(seed)  # noqa: S311 - angka uji, bukan kriptografi
    td2010 = seed % 3 == 2
    tb = 2024 if td2010 else 2025
    awal = urut(2022, 1) if td2010 else urut(2019, 1) + rng.choice([0, 0, 4])
    akhir = urut(2027, 4)
    us = list(range(max(urut(2019, 1), min(awal, urut(tb, 1)) - 4), akhir + 1))  # data boleh di luar sumbu
    t0 = [urut(tb, q) for q in (1, 2, 3, 4)]
    pohon = [{"id": i, "kode": k, "jenis": j, "induk": p, "urutan": i, "is_migas": m, "anggota": list(a)}
             for i, k, j, p, m, a in POHON]
    referensi = {"REF_IH": _seri(rng, us, 80, 160, 0.05), "REF_KURS": _seri(rng, us, 13000, 16500, 0.05)}
    data: dict[int, dict] = {}
    iid = 0
    for n_l, lid in enumerate(DATA):
        if rng.random() < 0.08:
            continue  # lapus tanpa data (baris kosong)
        items = []
        for _ in range(rng.randint(1, 5)):
            iid += 1
            m = rng.choice(["REV", "REV", "EKS", "EKS", "DEF", "DEF", "PDK"])
            it: dict = {"id": iid, "metode": m, "seri": {}, "parameter": {}, "tautan": []}
            if m == "REV":
                it["seri"] = {"KUANTUM": _seri(rng, us, 10, 5000), "HARGA": _seri(rng, us, 1, 300),
                              "RKA": _seri(rng, us, 0, 0.9)}
                if rng.random() < 0.2:
                    it["seri"].update(TPK=_seri(rng, us, 20, 90), KAMAR=_seri(rng, us, 50, 400))
                    it["tautan"].append({"jenis_seri": "KUANTUM", "sumber": "RUMUS", "rumus": "TPK_X_KAMAR"})
                elif rng.random() < 0.2:
                    it["seri"]["IH"] = _seri(rng, us, 80, 160)
                    it["tautan"].append({"jenis_seri": "HARGA", "sumber": "RUMUS", "rumus": "JANGKAR_X_IH_100"})
                    it["parameter"]["H_TD"] = rng.uniform(1, 300)
            elif m == "EKS":
                it["jenis_indeks"] = rng.choice(["IP", "IB", "IP", "IB", None])
                it["seri"] = {"INDEKS": _seri(rng, us, 50, 200, 0.06), "IH": _seri(rng, us, 80, 160, 0.06),
                              "RKA": _seri(rng, us, 0, 0.9), "BASE_ADHB": _seri(rng, t0, 100, 9000, 0.1),
                              "BASE_ADHK": _seri(rng, t0, 100, 9000, 0.1)}
                if rng.random() < 0.15 and n_l > 0:  # indeks = hasil lapus lain (DAG: hanya lapus sebelumnya)
                    src = rng.choice(DATA[:n_l])
                    it["tautan"].append({"jenis_seri": "INDEKS", "sumber": "HASIL_LAPUS", "lapus_sumber": [src],
                                         "besaran": rng.choice(["OUT_K", "OUT_CP", "GVA_K"]),
                                         "faktor": rng.uniform(0.5, 2)})
            elif m == "DEF":
                it["seri"] = {"OUT_ADHB": _seri(rng, us, 100, 9000), "IH": _seri(rng, us, 80, 160)}
                if rng.random() < 0.6:
                    it["seri"]["NTB_ADHB"] = _seri(rng, us, 50, 4000, 0.25)
                if rng.random() < 0.5:
                    it["seri"]["RKA"] = _seri(rng, us, 0, 0.9, 0.4)
                r = rng.random()
                if r < 0.2:
                    it["tautan"].append({"jenis_seri": "IH", "sumber": "SERI_REFERENSI", "seri_ref": "REF_IH",
                                         "faktor": rng.choice([1.0, 0.98])})
                elif r < 0.3:
                    it["seri"].update(NILAI_KAPITA=_seri(rng, us, 1e4, 5e5), PENDUDUK=_seri(rng, us, 1e5, 8e5))
                    it["tautan"].append({"jenis_seri": "OUT_ADHB", "sumber": "RUMUS", "rumus": "KAPITA_X_PENDUDUK_X_3",
                                         "faktor": rng.choice([1.0, 0.8865])})
                elif r < 0.4 and n_l > 0:
                    src = rng.choice(DATA[:n_l])
                    it["tautan"].append({"jenis_seri": "IH", "sumber": "HASIL_LAPUS", "lapus_sumber": [src],
                                         "besaran": "IMPLISIT_OUT", "faktor": 1.0})
            if m in ("REV", "EKS", "DEF") and rng.random() < 0.85:
                it["parameter"]["RKA_TD"] = rng.uniform(0, 0.9)
            if m == "REV" and rng.random() < (0.9 if td2010 else 0.3):
                it["parameter"].setdefault("H_TD", rng.uniform(1, 300))
            if m in ("EKS", "DEF") and rng.random() < (0.9 if td2010 else 0.3):
                it["parameter"]["IH_TD"] = rng.choice([100.0, rng.uniform(80, 160)])
            if rng.random() < 0.2:
                a = rng.choice(us[:len(us) // 2])
                it["mulai"] = a
                if rng.random() < 0.5:
                    it["selesai"] = rng.choice([u for u in us if u >= a])
            items.append(it)
        if lid == 11:  # G: margin perdagangan atas output lapus barang (kategori A + C.1) dan impor
            for src, rumus in (([1, 10], "MARGIN_X_OUTPUT"), ([], "MARGIN_X_IMPOR")):
                iid += 1
                it = {"id": iid, "metode": "DEF", "seri": {"R_MARGIN": _seri(rng, us, 0.05, 0.3),
                                                         "IH": _seri(rng, us, 80, 160), "RKA": _seri(rng, us, 0, 0.5)},
                      "parameter": {}, "tautan": [{"jenis_seri": "OUT_ADHB", "sumber": "RUMUS", "rumus": rumus,
                                                   "lapus_sumber": src, "faktor": rng.choice([1.0, 0.5])}]}
                if rng.random() < 0.7:
                    it["parameter"]["R_MARGIN_TD"] = rng.uniform(0.05, 0.3)
                if rng.random() < 0.8:
                    it["parameter"]["RKA_TD"] = rng.uniform(0, 0.5)
                if rumus == "MARGIN_X_IMPOR":
                    it["seri"]["V_IMPOR"] = _seri(rng, us, 1, 500)
                    if rng.random() < 0.6:
                        it["seri"]["KURS"] = {}
                        it["tautan"].append({"jenis_seri": "KURS", "sumber": "SERI_REFERENSI", "seri_ref": "REF_KURS"})
                    if rng.random() < 0.5:
                        it["parameter"]["IH_TD"] = 100.0
                items.append(it)
        adj = []
        for _ in range(rng.randint(0, 8)):
            u = rng.choice(list(range(awal, akhir + 1)))
            tahap = rng.choice(["METODE", "METODE", "REKON", "REKON", "SIMULASI"])
            if tahap == "METODE":
                adj.append({"tahap": tahap, "metode": rng.choice(["REV", "EKS", "DEF"]),
                            "jenis": rng.choice(["ADJ1", "ADJ2", "SC"]), "harga": rng.choice(["CP", "K"]),
                            "periode": u, "nilai": rng.uniform(-500, 500)})
            elif tahap == "REKON":
                adj.append({"tahap": tahap, "jenis": rng.choice(["ADJ3", "ADJ4_OUTPUT", "ADJ4_NTB", "CT_OUTPUT"]),
                            "harga": rng.choice(["CP", "K"]), "periode": u, "nilai": rng.uniform(-500, 500)})
            else:
                adj.append({"tahap": tahap, "jenis": "SIM_NTB", "harga": rng.choice(["CP", "K"]), "periode": u,
                            "nilai": rng.uniform(-300, 300)})
        uniq = {(a["tahap"], a.get("metode"), a["jenis"], a["harga"], a["periode"]): a for a in adj}
        data[lid] = {"item": items, "penyesuaian": list(uniq.values())}
    return {"tahun_baseline": tb, "jangkar_dari_data": not td2010, "awal": awal, "akhir": akhir, "pohon": pohon,
            "referensi": referensi, "data": data}
