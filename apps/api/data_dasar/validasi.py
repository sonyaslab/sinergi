"""Validasi data dasar dan hasil hitung V01–V17 (docs/00 bagian C; ref.validasi). Modul murni (tanpa I/O).

Masukan: masukan mesin (MasukanWilayah: item, seri mentah, parameter, tautan), hasil mesin (HasilWilayah), dan
metadata validasi (status item, nama, satuan, sel `tidak_tersedia`, semua penyesuaian termasuk draf dan CT, status
lapus, parameter ref.validasi). Keluaran: daftar Temuan dengan kunci stabil (untuk konfirmasi beralasan, mis. V05).

Kosong != nol: sel bertanda `tidak_tersedia` tidak ditandai V01. Pesan tidak memuat angka PDRB (hanya kode, periode,
dan ambang). Ambang V06/V08/V11 dibaca dari ref.validasi.parameter, termasuk kalibrasi P95 per lapus (keputusan 9/16).
V15 (hasil tersimpan vs hitung ulang) diperiksa saat kunci putaran, bukan di sini (hasil worker selalu konsisten).
"""
from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from ..engine.model import TANPA_KA, Empat, HasilWilayah, Item, MasukanWilayah, label
from ..engine.umum import bagi

BERDATA = ("daun", "top", "sop")
JANGKAR_SERI = {"H_TD": "HARGA", "IH_TD": "IH", "RKA_TD": "RKA", "R_MARGIN_TD": "R_MARGIN"}
KOMPONEN = {"TPK_X_KAMAR": ("TPK", "KAMAR"), "JANGKAR_X_IH_100": ("IH",),
            "KAPITA_X_PENDUDUK_X_3": ("NILAI_KAPITA", "PENDUDUK"), "MARGIN_X_OUTPUT": ("R_MARGIN",),
            "MARGIN_X_IMPOR": ("R_MARGIN", "V_IMPOR")}
MARGIN = ("MARGIN_X_OUTPUT", "MARGIN_X_IMPOR")
UKURAN_V08 = ("qtq_volume", "yoy_volume", "qtq_implisit", "yoy_implisit")
NAMA_UKURAN = {"qtq_volume": "q-to-q volume (NTB ADHK)", "yoy_volume": "y-on-y volume (NTB ADHK)",
               "qtq_implisit": "q-to-q implisit NTB", "yoy_implisit": "y-on-y implisit NTB"}


@dataclass
class InfoItem:
    id: int
    lapus_id: int
    metode: str
    nama: str
    nomor: int = 0
    status: str = "aktif"
    katalog_id: int | None = None
    satuan_kode: str | None = None
    satuan_seri: dict[str, str | None] = field(default_factory=dict)
    tidak_tersedia: set[tuple[str, int]] = field(default_factory=set)  # (seri, urut)


@dataclass
class AdjInfo:
    lapus_id: int
    tahap: str
    metode: str | None
    jenis: str
    harga: str
    periode: int
    nilai: float
    status: str


@dataclass
class AturanValidasi:
    tingkat: str
    parameter: dict[str, Any]
    aktif: bool = True


@dataclass
class KonteksValidasi:
    td_kode: str
    tahun_dasar: int
    awal: int  # periode putaran (urut)
    akhir: int
    item: dict[int, InfoItem]
    lapus: dict[int, tuple[str, str]]  # id -> (kode, jenis)
    aturan: dict[str, AturanValidasi]
    wajib: dict[str, set[str]]
    penyesuaian: list[AdjInfo] = field(default_factory=list)
    status_lapus: dict[int, str] = field(default_factory=dict)
    konfirmasi: dict[tuple[str, int, str], tuple[int | None, str]] = field(default_factory=dict)


@dataclass
class Temuan:
    kode: str
    tingkat: str
    lapus_id: int
    pesan: str
    kunci: str
    item_id: int | None = None
    jenis_seri: str | None = None
    periode: int | None = None
    dikonfirmasi_oleh: int | None = None
    alasan_konfirmasi: str | None = None


class _Kumpul:
    def __init__(self, k: KonteksValidasi):
        self.k = k
        self.hasil: list[Temuan] = []

    def aktif(self, kode: str) -> bool:
        a = self.k.aturan.get(kode)
        return a is not None and a.aktif

    def tambah(self, kode: str, lapus_id: int, pesan: str, item_id: int | None = None, seri: str | None = None,
               periode: int | None = None, kunci: str | None = None) -> None:
        if not self.aktif(kode):
            return
        kunci = kunci or f"{item_id or '-'}:{seri or '-'}:{periode if periode is not None else '-'}"
        t = Temuan(kode, self.k.aturan[kode].tingkat, lapus_id, pesan, kunci, item_id, seri, periode)
        kf = self.k.konfirmasi.get((kode, lapus_id, kunci))
        if kf is not None:
            t.dikonfirmasi_oleh, t.alasan_konfirmasi = kf
        self.hasil.append(t)


def _dalam_masa(it: Item, u: int) -> bool:
    return (it.mulai is None or u >= it.mulai) and (it.selesai is None or u <= it.selesai)


def _ringkas_periode(us: list[int]) -> str:
    return label(us[0]) if len(us) == 1 else f"{len(us)} triwulan ({label(us[0])} s.d. {label(us[-1])})"


def _seri_input(it: Item, wajib: set[str]) -> set[str]:
    """Seri yang wajib diketik operator untuk item ini (seri tertaut diganti komponennya; RKA diperiksa V02)."""
    rumus = {t.jenis_seri: t.rumus for t in it.tautan if t.sumber == "RUMUS"}
    tertaut = {t.jenis_seri for t in it.tautan}
    hasil = set()
    margin = any(r in MARGIN for r in rumus.values())
    for s in wajib - {"RKA"}:
        if s in tertaut:
            hasil |= set(KOMPONEN.get(rumus.get(s) or "", ()))
        elif not (margin and s == "IH" and "MARGIN_X_IMPOR" not in rumus.values()):
            hasil.add(s)
    for s, r in rumus.items():
        if s in wajib:
            continue
        hasil |= set(KOMPONEN.get(r or "", ()))
    return hasil - tertaut


def _p95(xs: list[float]) -> float:
    """Persentil 95 interpolasi linear (setara PERCENTILE.INC Excel)."""
    ys = sorted(xs)
    if not ys:
        return 0.0
    h = (len(ys) - 1) * 0.95
    lo = int(h)
    hi = min(lo + 1, len(ys) - 1)
    return ys[lo] + (ys[hi] - ys[lo]) * (h - lo)


def ambang_v08(param: dict[str, Any], td_kode: str, kode_lapus: str,
               riwayat: dict[str, list[float]]) -> dict[str, float]:
    """Ambang (%) per ukuran V08: tetap, override per lapus, atau kalibrasi P95 (tidak di bawah batas bawah)."""
    dasar = dict(param.get("ambang_persen") or {})
    over = (param.get("per_lapus") or {}).get(f"{td_kode}:{kode_lapus}", {})
    dasar.update(over.get("ambang_persen") or {})
    kalibrasi = over.get("kalibrasi", param.get("kalibrasi", "tetap"))
    p95 = param.get("p95") or {}
    out: dict[str, float] = {}
    for u in UKURAN_V08:
        tetap = float(dasar.get(u, 30))
        a = tetap
        xs = riwayat.get(u, [])
        if kalibrasi == "p95" and len(xs) >= int(p95.get("min_titik", 8)):
            bawah = p95.get("batas_bawah_persen")
            a = max(_p95(xs), tetap if bawah is None else float(bawah))
        out[u] = a
    return out


def _laju(a: float, b: float) -> float | None:
    return None if b == 0 else (a / b - 1) * 100


def validasi(m: MasukanWilayah, h: HasilWilayah, k: KonteksValidasi) -> list[Temuan]:
    v = _Kumpul(k)
    sb = h.sumbu
    t0 = m.konfig.t0
    jdd = m.konfig.jangkar_dari_data
    periode = range(k.awal, k.akhir + 1)
    per_lapus: dict[int, list[Item]] = defaultdict(list)
    for lid, d in m.data.items():
        per_lapus[lid].extend(d.item)

    for lid, items in per_lapus.items():
        kode_l, jenis_l = k.lapus.get(lid, ("?", "daun"))
        if jenis_l not in BERDATA:
            continue
        tanpa_ka = jenis_l in TANPA_KA
        hl = h.lapus.get(lid)
        for it in items:
            info = k.item.get(it.id)
            if info is None:
                continue
            aktif = info.status == "aktif"
            rumus = {t.jenis_seri: t.rumus for t in it.tautan if t.sumber == "RUMUS"}
            margin = next((r for r in rumus.values() if r in MARGIN), None)
            berlaku = any(_dalam_masa(it, u) for u in periode)
            seri = it.seri

            def isi(s: str, u: int, seri: dict = seri) -> bool:
                return u in seri.get(s, {})

            # V01 / V17 — sel wajib periode berjalan
            perlu = _seri_input(it, k.wajib.get(it.metode, set()))
            if aktif and _dalam_masa(it, k.akhir) and perlu:
                kosong = [s for s in sorted(perlu) if not isi(s, k.akhir) and (s, k.akhir) not in info.tidak_tersedia]
                for s in kosong:
                    v.tambah("V01", lid, f"Seri {s} periode berjalan ({label(k.akhir)}) belum diisi.", it.id, s,
                             k.akhir)
                if len(kosong) == len(perlu):
                    v.tambah("V17", lid, f"Item berlaku tetapi semua seri wajib kosong pada {label(k.akhir)}.",
                             it.id, None, k.akhir)
            if it.metode == "PDK" or not berlaku:
                continue
            e = hl.item.get(it.id) if hl else None
            # V02 — rasio KA
            if not tanpa_ka and aktif:
                if it.metode in ("REV", "EKS") and "RKA_TD" not in it.parameter:
                    v.tambah("V02", lid, "Rasio KA tahun dasar (jangkar RKA) kosong.", it.id, "RKA")
                if e is not None:
                    kurang = []
                    for u in periode:
                        if not _dalam_masa(it, u) or e.out_cp[sb.i(u)] <= 0:
                            continue
                        if it.metode in ("REV", "EKS") and not isi("RKA", u):
                            kurang.append(u)
                        elif (it.metode == "DEF" and not isi("NTB_ADHB", u) and not isi("RKA", u)
                              and "RKA_TD" not in it.parameter):
                            kurang.append(u)
                    if kurang:
                        apa = "RKA triwulanan" if it.metode != "DEF" else "NTB_ADHB dan RKA"
                        v.tambah("V02", lid, f"{apa} kosong saat output > 0 di {_ringkas_periode(kurang)}.", it.id,
                                 "RKA", kurang[0])
                if it.metode == "DEF" and jdd and not margin:
                    out_t0 = [u for u in t0 if seri.get("OUT_ADHB", {}).get(u)]
                    if out_t0 and not any(isi("NTB_ADHB", u) for u in t0) and (seri.get("RKA") or "RKA_TD" in
                                                                               it.parameter):
                        v.tambah("V02", lid, "NTB_ADHB tahun dasar kosong: rasio KA tahun dasar terhitung 1 sehingga "
                                 "NTB ADHK = 0. Isi NTB_ADHB tahun dasar atau ubah metode (keputusan 17).", it.id,
                                 "NTB_ADHB", kunci=f"{it.id}:NTB_ADHB:T0")
            # V03 — jangkar tahun dasar
            if aktif:
                for kode_p, alasan in _jangkar_kurang(it, jdd, t0, tanpa_ka, margin):
                    v.tambah("V03", lid, f"Jangkar {kode_p} kosong: {alasan}", it.id, JANGKAR_SERI[kode_p],
                             kunci=f"{it.id}:{kode_p}")
            # V04 / V12 — EKS
            if it.metode == "EKS":
                b_cp = any(isi("BASE_ADHB", u) for u in t0)
                b_k = any(isi("BASE_ADHK", u) for u in t0)
                if not b_cp and not b_k:
                    v.tambah("V04", lid, "Baseline ADHB dan ADHK tahun dasar keduanya kosong.", it.id, "BASE_ADHB",
                             kunci=f"{it.id}:BASE")
                relevan = "BASE_ADHB" if (it.jenis_indeks or "").upper() == "IB" else "BASE_ADHK"
                if not (b_cp if relevan == "BASE_ADHB" else b_k):
                    v.tambah("V12", lid, f"Item EKS tanpa {relevan} tahun dasar: tidak berkontribusi.", it.id, relevan,
                             kunci=f"{it.id}:{relevan}")
                if b_cp or b_k:
                    for arah, putus in _rantai_putus(it, sb.awal, sb.akhir, t0, periode):
                        v.tambah("V04", lid, f"Rantai indeks {arah} putus mulai {label(putus)}: periode "
                                 f"{'sesudah' if arah == 'maju' else 'sebelum'}nya bernilai 0.", it.id, "INDEKS",
                                 putus, kunci=f"{it.id}:INDEKS:{arah}")
            # V10 — ADHK = 0 sementara ADHB > 0 (item)
            if e is not None:
                salah = [u for u in periode if _dalam_masa(it, u) and _satu_nol(e.out_cp[sb.i(u)], e.out_k[sb.i(u)])]
                if salah:
                    v.tambah("V10", lid, f"Output ADHB dan ADHK tidak berpasangan (salah satu 0) di "
                             f"{_ringkas_periode(salah)}.", it.id, None, salah[0], kunci=f"{it.id}:OUT")
            # V16 — satuan
            sk = info.satuan_kode
            s_kuantum = info.satuan_seri.get("KUANTUM") or info.satuan_seri.get("OUT_ADHB")
            if sk and s_kuantum and sk.lower() != s_kuantum.lower() and it.metode == "REV":
                v.tambah("V16", lid, f"Satuan item ({sk}) berbeda dengan satuan baris KUANTUM ({s_kuantum}).", it.id,
                         "KUANTUM", kunci=f"{it.id}:SATUAN")
        # V05 — komoditas sama di dua metode
        aktif_items = [it for it in items if k.item.get(it.id) and k.item[it.id].status == "aktif"]
        for i, a in enumerate(aktif_items):
            for b in aktif_items[i + 1:]:
                ia, ib = k.item[a.id], k.item[b.id]
                if a.metode == b.metode or "PDK" in (a.metode, b.metode):
                    continue
                sama = (ia.katalog_id is not None and ia.katalog_id == ib.katalog_id) or \
                    " ".join(ia.nama.lower().split()) == " ".join(ib.nama.lower().split())
                if sama and _tumpang(a, b):
                    kunci = f"{min(a.id, b.id)}-{max(a.id, b.id)}"
                    for x, y in ((a, b), (b, a)):
                        v.tambah("V05", lid, f"Komoditas sama dengan item {y.metode} no. {k.item[y.id].nomor} pada"
                                 " lapus ini (potensi hitung ganda).", x.id, kunci=kunci)
        if hl is None:
            continue
        bn = hl.tahap.get("BENC")
        if bn is None:
            continue
        _cek_lapus(v, k, lid, kode_l, tanpa_ka, bn, sb, periode)

    _cek_penyesuaian(v, k, h)
    _cek_kunci(v, k, per_lapus)
    return v.hasil


def _tumpang(a: Item, b: Item) -> bool:
    lo = max(a.mulai if a.mulai is not None else -10**9, b.mulai if b.mulai is not None else -10**9)
    hi = min(a.selesai if a.selesai is not None else 10**9, b.selesai if b.selesai is not None else 10**9)
    return lo <= hi


def _satu_nol(cp: float, k: float) -> bool:
    return (cp > 0 and k == 0) or (k > 0 and cp == 0)


def _jangkar_kurang(it: Item, jdd: bool, t0: list[int], tanpa_ka: bool, margin: str | None) -> list[tuple[str, str]]:
    """Parameter jangkar yang kosong dan membuat ADHK/NTB ADHK item 0 (docs/02 §2)."""
    p, s = it.parameter, it.seri
    taut = {t.jenis_seri: t for t in it.tautan}

    def ada_t0(kode: str, bukan_nol: bool = False) -> bool:
        """Seri punya nilai pada T₀ (dalam masa berlaku). Seri tertaut: komponen rumus; referensi/hasil dianggap ada."""
        t = taut.get(kode)
        if t is not None:
            if t.sumber != "RUMUS":
                return True
            return all(ada_t0(c, bukan_nol) for c in KOMPONEN.get(t.rumus or "", ()))
        return any(u in s.get(kode, {}) and _dalam_masa(it, u) and (not bukan_nol or s[kode][u] != 0) for u in t0)

    out: list[tuple[str, str]] = []
    alasan = "tahun dasar ini mewajibkan jangkar diisi." if not jdd else "tidak ada data tahun dasar."
    if it.metode == "REV" and "H_TD" not in p and (not jdd or not ada_t0("KUANTUM", True)):
        out.append(("H_TD", alasan))
    if it.metode in ("EKS", "DEF") and "IH_TD" not in p and margin != "MARGIN_X_OUTPUT" and (
            not jdd or not ada_t0("IH")):
        out.append(("IH_TD", alasan))
    if it.metode == "DEF" and not tanpa_ka and "RKA_TD" not in p and (not jdd or not ada_t0("OUT_ADHB", True)):
        out.append(("RKA_TD", alasan))
    if margin and "R_MARGIN_TD" not in p and (not jdd or not ada_t0("R_MARGIN")):
        out.append(("R_MARGIN_TD", alasan))
    return out


def _rantai_putus(it: Item, awal: int, akhir: int, t0: list[int], periode: Iterable[int]) -> list[tuple[str, int]]:
    ind = it.seri.get("INDEKS", {})
    pr = [u for u in periode if _dalam_masa(it, u)]
    out = []
    maju = [u for u in pr if u > t0[-1]]
    for u in maju:
        if u not in ind or (u - 1) not in ind:
            out.append(("maju", u))
            break
    mundur = sorted((u for u in pr if u < t0[0]), reverse=True)
    for u in mundur:
        if u not in ind or (u + 1) not in ind:
            out.append(("mundur", u))
            break
    return out


def _cek_lapus(v: _Kumpul, k: KonteksValidasi, lid: int, kode_l: str, tanpa_ka: bool, bn: Empat, sb: Any,
               periode: range) -> None:
    def x(seri: list[float], u: int) -> float:
        return seri[sb.i(u)]

    # V06 — implisit tahunan tahun dasar
    th = [u for u in range(k.tahun_dasar * 4, k.tahun_dasar * 4 + 4)]
    if all(sb.awal <= u <= sb.akhir for u in th) and v.aktif("V06"):
        tol = float(k.aturan["V06"].parameter.get("toleransi", 0.5))
        for nama, cp, kk in (("NTB", bn.gva_cp, bn.gva_k), ("output", bn.out_cp, bn.out_k)):
            s_cp, s_k = sum(x(cp, u) for u in th), sum(x(kk, u) for u in th)
            if s_k != 0 and abs(s_cp / s_k * 100 - 100) > tol:
                v.tambah("V06", lid, f"Implisit tahunan {nama} {k.tahun_dasar} tidak dalam 100 ± {tol}.",
                         kunci=f"-:{nama}:{k.tahun_dasar}")
    # V08 — lonjakan
    if v.aktif("V08"):
        par = k.aturan["V08"].parameter
        p95 = par.get("p95") or {}
        ta, tz = int(p95.get("tahun_awal", 2019)), int(p95.get("tahun_akhir", 2025))

        def ukur(u: int) -> dict[str, float | None]:
            out: dict[str, float | None] = {}
            for lag, nm in ((1, "qtq"), (4, "yoy")):
                if u - lag < sb.awal:
                    out[f"{nm}_volume"] = out[f"{nm}_implisit"] = None
                    continue
                out[f"{nm}_volume"] = _laju(x(bn.gva_k, u), x(bn.gva_k, u - lag))
                i1 = bagi(x(bn.gva_cp, u), x(bn.gva_k, u))
                i0 = bagi(x(bn.gva_cp, u - lag), x(bn.gva_k, u - lag))
                out[f"{nm}_implisit"] = None if i1 == 0 or i0 == 0 else _laju(i1, i0)
            return out

        semua = {u: ukur(u) for u in range(sb.awal, sb.akhir + 1)}
        riwayat: dict[str, list[float]] = defaultdict(list)
        for u, g in semua.items():
            if ta <= u // 4 <= tz:
                for nm, val in g.items():
                    if val is not None:
                        riwayat[nm].append(abs(val))
        ambang = ambang_v08(par, k.td_kode, kode_l, riwayat)
        for u in periode:
            for nm, val in semua.get(u, {}).items():
                if val is not None and abs(val) > ambang[nm]:
                    v.tambah("V08", lid, f"Lonjakan {NAMA_UKURAN[nm]} melewati ambang {ambang[nm]:.1f}%.", None,
                             nm, u, kunci=f"-:{nm}:{u}")
    # V09 — NTB >= output atau NTB < 0
    if not tanpa_ka:
        for nama, out, gva in (("ADHB", bn.out_cp, bn.gva_cp), ("ADHK", bn.out_k, bn.gva_k)):
            salah = [u for u in periode if (x(out, u) > 0 and x(gva, u) >= x(out, u)) or x(gva, u) < 0]
            if salah:
                v.tambah("V09", lid, f"NTB {nama} >= output atau negatif di {_ringkas_periode(salah)}.", None, nama,
                         salah[0], kunci=f"-:{nama}")
    # V10 — lapus (setelah penyesuaian)
    for nama, cp, kk in (("Output", bn.out_cp, bn.out_k), ("NTB", bn.gva_cp, bn.gva_k)):
        salah = [u for u in periode if _satu_nol(x(cp, u), x(kk, u))]
        if salah:
            v.tambah("V10", lid, f"{nama} lapus: ADHB dan ADHK tidak berpasangan (salah satu 0) di "
                     f"{_ringkas_periode(salah)}.", None, nama, salah[0], kunci=f"-:{nama}")


def _cek_penyesuaian(v: _Kumpul, k: KonteksValidasi, h: HasilWilayah) -> None:
    sb = h.sumbu
    # V07 — ADJ metode tanpa pasangan harga
    pasang: dict[tuple, dict[str, float]] = defaultdict(dict)
    for a in k.penyesuaian:
        if a.tahap == "METODE" and a.jenis in ("ADJ1", "ADJ2", "SC") and a.status != "ditolak":
            pasang[(a.lapus_id, a.metode, a.jenis, a.periode)][a.harga] = a.nilai
    for (lid, met, jenis, u), d in sorted(pasang.items(), key=lambda kv: (kv[0][0], kv[0][1] or "", kv[0][2],
                                                                          kv[0][3])):
        if bool(d.get("CP")) != bool(d.get("K")):
            ada = "ADHB" if d.get("CP") else "ADHK"
            v.tambah("V07", lid, f"{jenis} {met} {label(u)}: hanya {ada}, pasangannya kosong.", None, None, u,
                     kunci=f"-:{met}:{jenis}:{u}")
    # V11 — selisih terhadap control total
    if v.aktif("V11"):
        ambang = float(k.aturan["V11"].parameter.get("ambang_persen", 1))
        for a in k.penyesuaian:
            if a.jenis not in ("CT_OUTPUT", "CT_NTB") or a.status == "ditolak" or a.nilai == 0:
                continue
            hl = h.lapus.get(a.lapus_id)
            if hl is None or "BENC" not in hl.tahap or not sb.awal <= a.periode <= sb.akhir:
                continue
            bn = hl.tahap["BENC"]
            seri = {("CT_OUTPUT", "CP"): bn.out_cp, ("CT_OUTPUT", "K"): bn.out_k, ("CT_NTB", "CP"): bn.gva_cp,
                    ("CT_NTB", "K"): bn.gva_k}[(a.jenis, a.harga)]
            if abs(seri[sb.i(a.periode)] - a.nilai) / abs(a.nilai) * 100 > ambang:
                v.tambah("V11", a.lapus_id, f"Selisih terhadap {a.jenis} ({'ADHB' if a.harga == 'CP' else 'ADHK'}) "
                         f"{label(a.periode)} melewati ambang {ambang:g}%.", None, a.jenis, a.periode,
                         kunci=f"-:{a.jenis}:{a.harga}:{a.periode}")


def _cek_kunci(v: _Kumpul, k: KonteksValidasi, per_lapus: dict[int, list[Item]]) -> None:
    """V13 (daun tanpa item dan bukan NIHIL), V14 (TOP/SOP kosong dan tidak DIKECUALIKAN admin; keputusan 2) —
    memblokir kunci putaran. NIHIL tidak membebaskan TOP/SOP: pengecualian V14 hanya oleh admin (dikecualikan)."""
    for lid, (kode, jenis) in k.lapus.items():
        if any(it.metode in ("REV", "EKS", "DEF") for it in per_lapus.get(lid, [])):
            continue
        st = k.status_lapus.get(lid)
        if jenis == "daun" and st != "nihil":
            v.tambah("V13", lid, f"Lapus {kode} belum punya item dan belum ditandai NIHIL.", kunci="-")
        elif jenis in ("top", "sop") and st != "dikecualikan":
            v.tambah("V14", lid, f"{kode} belum diisi (pajak/subsidi atas produk) dan belum dikecualikan admin.",
                     kunci="-")
