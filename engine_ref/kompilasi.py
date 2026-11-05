"""
Oracle tingkat wilayah: tautan antarlapus, rekonsiliasi bertahap, simulasi, agregasi pohon, dan tabel turunan
(docs/02 §1, §6–§8, §11). Ditulis naif dan terpisah dari mesin produksi; dipakai uji golden sintetis.

Masukan = "spek" berbentuk dict biasa (format netral yang juga dipakai adaptor golden):

    {
      "tahun_baseline": 2025, "jangkar_dari_data": True,
      "awal": urut, "akhir": urut,                     # urut = tahun * 4 + triwulan - 1 (ref.periode.urut)
      "pohon": [{"id", "kode", "jenis", "induk", "urutan", "is_migas", "anggota": [id...]}, ...],
      "referensi": {kode: {urut: nilai}},
      "data": {lapus_id: {"item": [...], "penyesuaian": [...]}},
    }
    item = {"id", "metode", "jenis_indeks": "IP"|"IB"|None, "seri": {kode: {urut: nilai}},
            "parameter": {"RKA_TD"|"H_TD"|"IH_TD"|"R_MARGIN_TD": nilai},
            "tautan": [{"jenis_seri", "sumber", "rumus", "seri_ref", "lapus_sumber": [id...], "besaran", "faktor"}],
            "mulai": urut|None, "selesai": urut|None}
    penyesuaian = {"tahap", "metode", "jenis", "harga": "CP"|"K", "periode": urut, "nilai"}   # sudah disaring

Hasil per lapus: {"pre", "post", "benc", "final"} (Hasil berindeks t engine_ref) + "metode" + "item".
"""
from __future__ import annotations

from typing import Dict, List, Optional

from engine_ref import turunan as tr
from engine_ref.lk_engine import (NQ, TAHUN_AWAL, AdjMetode, AdjRekon, Hasil, ItemDEF, ItemEKS, ItemREV, div,
                                  hitung_def, hitung_eks, hitung_rev, pre_rekon, t_base_tahun, tahap_rekon)

BERITEM = ("daun", "top", "sop")
URUT0 = TAHUN_AWAL * 4  # urut 2019Q1 -> t = 0


class GalatSpek(ValueError):
    pass


def _ke_t(s: Dict[int, float]) -> Dict[int, float]:
    return {u - URUT0: float(x) for u, x in (s or {}).items() if 0 <= u - URUT0 < NQ and x is not None}


def _kosong() -> Hasil:
    return Hasil([0.0] * NQ, [0.0] * NQ, [0.0] * NQ, [0.0] * NQ)


def _jumlah(hs: List[Hasil]) -> Hasil:
    out = _kosong()
    for h in hs:
        for a in ("out_cp", "gva_cp", "out_k", "gva_k"):
            x, y = getattr(out, a), getattr(h, a)
            for t in range(NQ):
                x[t] += y[t]
    return out


def _kurang(a: Hasil, b: Hasil) -> Hasil:
    return Hasil(*[[x - y for x, y in zip(getattr(a, k), getattr(b, k))] for k in ("out_cp", "gva_cp", "out_k", "gva_k")])


class Pohon:
    def __init__(self, baris: List[dict]):
        self.b = {r["id"]: r for r in baris}
        self.anak: Dict[int, List[int]] = {}
        for r in sorted(baris, key=lambda r: r["urutan"]):
            if r.get("induk") is not None:
                self.anak.setdefault(r["induk"], []).append(r["id"])

    def urut(self, ids):
        return sorted(set(ids), key=lambda i: self.b[i]["urutan"])

    def daun_data(self, lid: int) -> List[int]:
        """Lapus berdata di bawah (atau sama dengan) lid; kelompok diurai ke anggotanya."""
        r = self.b.get(lid)
        if r is None:
            raise GalatSpek(f"lapus sumber {lid} tidak ada atau tidak aktif")
        if r["jenis"] in BERITEM:
            return [lid]
        if r["jenis"] in ("kategori", "sub"):
            return [d for a in self.anak.get(lid, []) for d in self.daun_data(a)]
        if r["jenis"] == "kelompok":
            return [d for a in r.get("anggota", []) for d in self.daun_data(a)]
        raise GalatSpek(f"lapus sumber {r['kode']} adalah baris total")


def _sumber(item: dict) -> List[int]:
    return [x for tt in item.get("tautan", []) for x in (tt.get("lapus_sumber") or [])
            if tt["sumber"] == "HASIL_LAPUS" or tt.get("rumus") == "MARGIN_X_OUTPUT"]


def _selesaikan(item: dict, spec: dict, pohon: Pohon, benc: Dict[int, Hasil], t_base: List[int]):
    """Seri item setelah masa berlaku, tautan, dan rumus turunan. Kembalikan (seri, out_k)."""
    mulai = item.get("mulai"); selesai = item.get("selesai")
    m0 = None if mulai is None else mulai - URUT0
    m1 = None if selesai is None else selesai - URUT0
    seri = {k: tr.potong_masa(_ke_t(s), m0, m1) for k, s in item.get("seri", {}).items()}
    par = item.get("parameter", {})
    jdd = spec["jangkar_dari_data"]
    out_k: Optional[Dict[int, float]] = None
    taut = item.get("tautan", [])
    for tt in taut:
        if tt["sumber"] == "SERI_REFERENSI":
            seri[tt["jenis_seri"]] = tr.seri_referensi(_ke_t(spec["referensi"].get(tt["seri_ref"], {})),
                                                       tt.get("faktor", 1.0))
    for tt in taut:
        if tt["sumber"] == "HASIL_LAPUS":
            ids = pohon.urut([d for x in tt["lapus_sumber"] for d in pohon.daun_data(x)])
            seri[tt["jenis_seri"]] = tr.hasil_lapus([benc.get(i, _kosong()) for i in ids], tt["besaran"],
                                                    tt.get("faktor", 1.0))
    urutan_rumus = {k: i for i, k in enumerate(tr.KODE_RUMUS)}
    for tt in sorted([x for x in taut if x["sumber"] == "RUMUS"], key=lambda x: urutan_rumus[x["rumus"]]):
        f = tt.get("faktor", 1.0); g = lambda k: seri.get(k, {})  # noqa: E731
        rm = tt["rumus"]
        if rm == "TPK_X_KAMAR":
            seri["KUANTUM"] = tr.tpk_x_kamar(g("TPK"), g("KAMAR"))
        elif rm == "JANGKAR_X_IH_100":
            seri["HARGA"] = tr.jangkar_x_ih_100(par.get("H_TD"), g("IH"))
        elif rm == "KAPITA_X_PENDUDUK_X_3":
            seri["OUT_ADHB"] = tr.kapita_x_penduduk_x_3(g("NILAI_KAPITA"), g("PENDUDUK"), f)
        elif rm == "MARGIN_X_OUTPUT":
            ids = pohon.urut([d for x in tt["lapus_sumber"] for d in pohon.daun_data(x)])
            hs = [benc.get(i, _kosong()) for i in ids]
            seri["OUT_ADHB"], out_k = tr.margin_x_output(
                g("R_MARGIN"), tr.jumlah_hasil(hs, "OUT_CP"), tr.jumlah_hasil(hs, "OUT_K"), f,
                par.get("R_MARGIN_TD"), t_base, jdd)
        elif rm == "MARGIN_X_IMPOR":
            seri["OUT_ADHB"], out_k = tr.margin_x_impor(
                g("R_MARGIN"), g("V_IMPOR"), seri.get("KURS"), g("IH"), par.get("IH_TD"), f,
                par.get("R_MARGIN_TD"), t_base, jdd)
    seri = {k: tr.potong_masa(s, m0, m1) for k, s in seri.items()}
    return seri, tr.potong_masa(out_k, m0, m1)


def _item_ref(item: dict, seri: dict, out_k, t_base: List[int]):
    par = item.get("parameter", {}); g = lambda k: seri.get(k, {})  # noqa: E731
    m = item["metode"]
    if m == "REV":
        return ItemREV(str(item["id"]), P=g("KUANTUM"), H=g("HARGA"), RKA=g("RKA"), RKA_TD=par.get("RKA_TD"),
                       H_TD=par.get("H_TD"))
    if m == "EKS":
        jenis = {"IP": "INDEKS PRODUKSI", "IB": "INDEKS BERLAKU"}.get(item.get("jenis_indeks") or "", "")
        return ItemEKS(str(item["id"]), jenis=jenis, I=g("INDEKS"), IH=g("IH"),
                       base_cp=[g("BASE_ADHB").get(t) for t in t_base], base_k=[g("BASE_ADHK").get(t) for t in t_base],
                       RKA=g("RKA"), RKA_TD=par.get("RKA_TD"), IH_TD=par.get("IH_TD"))
    return ItemDEF(str(item["id"]), OUT_CP=g("OUT_ADHB"), GVA_CP=g("NTB_ADHB"), IH=g("IH"), RKA=g("RKA"),
                   RKA_TD=par.get("RKA_TD"), IH_TD=par.get("IH_TD"), OUT_K=out_k)


ATR_METODE = {("ADJ1", "CP"): "cp_adj1", ("ADJ2", "CP"): "cp_adj2", ("SC", "CP"): "cp_sc",
              ("ADJ1", "K"): "k_adj1", ("ADJ2", "K"): "k_adj2", ("SC", "K"): "k_sc"}
ATR_REKON = {("ADJ3", "CP"): "out_cp_adj3", ("ADJ4_OUTPUT", "CP"): "out_cp_adj4", ("ADJ4_NTB", "CP"): "gva_cp_adj4",
             ("ADJ3", "K"): "out_k_adj3", ("ADJ4_OUTPUT", "K"): "out_k_adj4", ("ADJ4_NTB", "K"): "gva_k_adj4"}


def simulasi(benc: Hasil, sim_cp: Dict[int, float], sim_k: Dict[int, float]) -> Hasil:
    """NTB final = NTB BENC + SIM; output ikut proporsi NTB. Tanpa SIM (0) = BENC apa adanya."""
    fin = Hasil(list(benc.out_cp), list(benc.gva_cp), list(benc.out_k), list(benc.gva_k))
    for t in range(NQ):
        s = sim_cp.get(t, 0.0)
        if s != 0:
            fin.gva_cp[t] = benc.gva_cp[t] + s
            fin.out_cp[t] = benc.out_cp[t] * div(fin.gva_cp[t], benc.gva_cp[t])
        s = sim_k.get(t, 0.0)
        if s != 0:
            fin.gva_k[t] = benc.gva_k[t] + s
            fin.out_k[t] = benc.out_k[t] * div(fin.gva_k[t], benc.gva_k[t])
    return fin


def hitung_lapus(lid: int, spec: dict, pohon: Pohon, benc: Dict[int, Hasil]) -> dict:
    d = spec["data"][lid]
    tb = t_base_tahun(spec["tahun_baseline"])
    jdd = spec["jangkar_dari_data"]
    tanpa_ka = pohon.b[lid]["jenis"] in ("top", "sop")
    per = {"REV": [], "EKS": [], "DEF": []}
    item_hasil = {}
    for it in d.get("item", []):
        if it["metode"] not in per:
            continue
        seri, out_k = _selesaikan(it, spec, pohon, benc, tb)
        obj = _item_ref(it, seri, out_k, tb)
        per[it["metode"]].append(obj)
        fn = {"REV": hitung_rev, "EKS": hitung_eks, "DEF": hitung_def}[it["metode"]]
        item_hasil[it["id"]] = fn([obj], t_base=tb, jangkar_dari_data=jdd, tanpa_ka=tanpa_ka)
    adj_m = {m: AdjMetode() for m in per}
    adj_r = AdjRekon()
    sim_cp: Dict[int, float] = {}
    sim_k: Dict[int, float] = {}
    for a in d.get("penyesuaian", []):
        t = a["periode"] - URUT0
        if a["tahap"] == "METODE":
            getattr(adj_m[a["metode"]], ATR_METODE[(a["jenis"], a["harga"])])[t] = a["nilai"]
        elif a["tahap"] == "REKON" and (a["jenis"], a["harga"]) in ATR_REKON:
            getattr(adj_r, ATR_REKON[(a["jenis"], a["harga"])])[t] = a["nilai"]
        elif a["tahap"] == "SIMULASI":
            (sim_cp if a["harga"] == "CP" else sim_k)[t] = a["nilai"]
    metode = {}
    pres = []
    for m, fn in (("REV", hitung_rev), ("EKS", hitung_eks), ("DEF", hitung_def)):
        pr = fn(per[m], t_base=tb, jangkar_dari_data=jdd, tanpa_ka=tanpa_ka)
        pre = pre_rekon(pr, adj_m[m])
        metode[m] = (Hasil(*pr), Hasil(*pre))
        pres.append(pre)
    pre, post, bn = tahap_rekon(pres, adj_r)
    return {"pre": pre, "post": post, "benc": bn, "final": simulasi(bn, sim_cp, sim_k),
            "metode": metode, "item": item_hasil}


def punya_data(d: Optional[dict]) -> bool:
    if not d:
        return False
    return any(i["metode"] in ("REV", "EKS", "DEF") for i in d.get("item", [])) or bool(d.get("penyesuaian"))


def hitung_wilayah(spec: dict) -> Dict[int, dict]:
    pohon = Pohon(spec["pohon"])
    data_ids = [i for i in pohon.urut(spec["data"]) if i in pohon.b and pohon.b[i]["jenis"] in BERITEM
                and punya_data(spec["data"][i])]
    gantung = {i: {s for it in spec["data"][i].get("item", []) for x in _sumber(it) for s in pohon.daun_data(x)}
               for i in data_ids}
    hasil: Dict[int, dict] = {}
    benc: Dict[int, Hasil] = {}
    sisa = list(data_ids)
    while sisa:
        siap = [i for i in sisa if all(s in benc or s not in data_ids for s in gantung[i]) and i not in gantung[i]]
        if not siap:
            raise GalatSpek("siklus tautan antarlapus")
        i = siap[0]
        hasil[i] = hitung_lapus(i, spec, pohon, benc)
        benc[i] = hasil[i]["benc"]
        sisa.remove(i)
    agregasi(pohon, hasil)
    return hasil


def agregasi(pohon: Pohon, hasil: Dict[int, dict]) -> None:
    """Baris non-data = Σ anak/anggota (tahap BENC dan FINAL). Baris tanpa sumber berdata tetap tanpa hasil."""
    def nilai(lid: int, tahap: str) -> Optional[Hasil]:
        if lid in hasil and tahap in hasil[lid]:
            return hasil[lid][tahap]
        r = pohon.b[lid]
        if r["jenis"] in BERITEM:
            return None
        akar = [i for i in pohon.urut(pohon.b) if pohon.b[i].get("induk") is None
                and pohon.b[i]["jenis"] in ("kategori", "sub", "daun")]
        top = [i for i in pohon.urut(pohon.b) if pohon.b[i]["jenis"] == "top"]
        sop = [i for i in pohon.urut(pohon.b) if pohon.b[i]["jenis"] == "sop"]

        def sigma(ids):
            hs = [h for h in (nilai(i, tahap) for i in ids) if h is not None]
            return _jumlah(hs) if hs else None
        j = r["jenis"]
        if j in ("kategori", "sub"):
            h = sigma(pohon.anak.get(lid, []))
        elif j == "kelompok":
            h = sigma(pohon.urut(r.get("anggota", [])))
        elif j == "ntb":
            h = sigma(akar)
        elif j in ("topsop", "pdrb", "pdrb_nonmigas"):
            n, tp, sp = sigma(akar), sigma(top), sigma(sop)
            if n is None and tp is None and sp is None:
                h = None
            else:
                ts = _kurang(tp or _kosong(), sp or _kosong())
                h = ts if j == "topsop" else _jumlah([n or _kosong(), ts])
                if j == "pdrb_nonmigas":
                    mg = [i for i in pohon.urut(pohon.b) if pohon.b[i].get("is_migas") and not _leluhur_migas(pohon, i)]
                    h = _kurang(h, sigma(mg) or _kosong())
        else:
            h = None
        if h is not None:
            hasil.setdefault(lid, {})[tahap] = h
        return h

    for lid in pohon.urut(pohon.b):
        for tahap in ("benc", "final"):
            nilai(lid, tahap)


def _leluhur_migas(pohon: Pohon, lid: int) -> bool:
    p = pohon.b[lid].get("induk")
    while p is not None:
        if pohon.b[p].get("is_migas"):
            return True
        p = pohon.b[p].get("induk")
    return False


# ------------------------------------------------------------------ tabel turunan (docs/02 §8.6)
def _bagi(a: float, b: float) -> Optional[float]:
    return None if b == 0 else a / b


def distribusi(x_cp: List[float], pdrb_cp: List[float]):
    return [None if (q := _bagi(x_cp[t], pdrb_cp[t])) is None else q * 100 for t in range(len(x_cp))]


def implisit(cp: List[float], k: List[float]):
    return [None if (q := _bagi(cp[t], k[t])) is None else q * 100 for t in range(len(cp))]


def laju(x: List[Optional[float]], lag: int):
    out: List[Optional[float]] = []
    for t in range(len(x)):
        if t - lag < 0 or x[t] is None or x[t - lag] is None:
            out.append(None)
            continue
        q = _bagi(x[t], x[t - lag])
        out.append(None if q is None else q * 100 - 100)
    return out


def _kum(x: List[float], t: int, awal_q: int) -> Optional[float]:
    """Σ T1..t dalam tahun t; awal_q = indeks triwulan (0..3) dari t=0."""
    q = (t + awal_q) % 4
    if t - q < 0:
        return None
    return sum(x[t - q + i] for i in range(q + 1))


def laju_ctc(x: List[float], awal_q: int = 0):
    out: List[Optional[float]] = []
    for t in range(len(x)):
        a, b = _kum(x, t, awal_q), (_kum(x, t - 4, awal_q) if t - 4 >= 0 else None)
        q = None if a is None or b is None else _bagi(a, b)
        out.append(None if q is None else q * 100 - 100)
    return out


def implisit_ctc(cp: List[float], k: List[float], awal_q: int = 0):
    out: List[Optional[float]] = []
    for t in range(len(cp)):
        a, b = _kum(cp, t, awal_q), _kum(k, t, awal_q)
        q = None if a is None or b is None else _bagi(a, b)
        out.append(None if q is None else q * 100)
    return out


def laju_implisit_ctc(cp: List[float], k: List[float], awal_q: int = 0):
    return laju(implisit_ctc(cp, k, awal_q), 4)


def sog(x_k: List[float], pdrb_k: List[float], lag: int):
    out: List[Optional[float]] = []
    for t in range(len(x_k)):
        if t - lag < 0:
            out.append(None)
            continue
        q = _bagi(x_k[t] - x_k[t - lag], pdrb_k[t - lag])
        out.append(None if q is None else q * 100)
    return out


def sog_ctc(x_k: List[float], pdrb_k: List[float], awal_q: int = 0):
    out: List[Optional[float]] = []
    for t in range(len(x_k)):
        a = _kum(x_k, t, awal_q)
        b = _kum(x_k, t - 4, awal_q) if t - 4 >= 0 else None
        p = _kum(pdrb_k, t - 4, awal_q) if t - 4 >= 0 else None
        q = None if a is None or b is None or p is None else _bagi(a - b, p)
        out.append(None if q is None else q * 100)
    return out
