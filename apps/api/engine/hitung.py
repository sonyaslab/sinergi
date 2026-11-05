"""Hitung satu wilayah satu putaran (docs/02 §1): data dasar → item → metode (PR, PRE) → rekonsiliasi
(PRE, POST, BENC) → simulasi (FINAL) → agregasi pohon, kelompok, total → sidik masukan.

Lapus dihitung menurut graf dependensi tautan (HASIL_LAPUS, MARGIN_X_OUTPUT memakai tahap BENC lapus sumber);
siklus ditolak (SiklusTautan).
"""
from __future__ import annotations

from collections.abc import Sequence

from . import deff, eks, rev
from .agregasi import agregasikan
from .graf import Pohon, urutkan
from .model import (
    BERITEM,
    METODE_HITUNG,
    TANPA_KA,
    DataLapus,
    Empat,
    GalatMesin,
    HasilLapus,
    HasilWilayah,
    ItemSiap,
    KonfigTD,
    MasukanWilayah,
    Seri,
    Sumbu,
)
from .penyesuaian import JENIS_METODE, pre_metode, simulasi
from .rekon import rekonsiliasi
from .sidik import sidik_agregat, sidik_lapus
from .turunan import PenyediaBenc, selesaikan, sumber_tautan

HITUNG_METODE = {"REV": rev.hitung, "EKS": eks.hitung, "DEF": deff.hitung}
JENIS_REKON = ("ADJ3", "ADJ4_OUTPUT", "ADJ4_NTB")


def hitung_wilayah(m: MasukanWilayah) -> HasilWilayah:
    konfig = m.konfig
    sb = m.sumbu.mencakup(*konfig.t0)
    pohon = Pohon(m.pohon)
    data = {lid: d for lid, d in m.data.items() if lid in pohon.b and pohon.b[lid].jenis in BERITEM and d.berdata()}
    gantung = {lid: {s for it in d.item for s in pohon.urai(sumber_tautan(it))} for lid, d in data.items()}
    urutan = urutkan(pohon, list(data), gantung)

    hasil: dict[int, HasilLapus] = {}
    n = len(sb)
    nol = Empat.nol(n)

    def benc(ids: Sequence[int]) -> list[Empat]:
        return [hasil[i].tahap["BENC"] if i in hasil else nol for i in ids]

    for lid in urutan:
        hasil[lid] = hitung_lapus(lid, pohon.b[lid].jenis, data[lid], konfig, sb, m.referensi, pohon, benc)

    agregat = agregasikan(pohon, {lid: h.tahap for lid, h in hasil.items()}, n)
    for r in pohon.baris:  # sidik agregat = gabungan sidik sumber berdata
        if r.id in agregat:
            sumber = [hasil[i].hash_input for i in _sumber_agregat(pohon, r.id) if i in hasil]
            hasil[r.id] = HasilLapus(tahap=agregat[r.id], hash_input=sidik_agregat(r.id, r.jenis, sumber))
    return HasilWilayah(sumbu=sb, lapus=hasil, urutan_hitung=urutan)


def _sumber_agregat(pohon: Pohon, lid: int) -> list[int]:
    r = pohon.b[lid]
    if r.jenis in ("kategori", "sub", "kelompok"):
        return pohon.urai([lid])
    return [x.id for x in pohon.baris if x.jenis in BERITEM]  # total: semua lapus berdata


def _seri_adj(d: DataLapus, tahap: str, metode: str | None, jenis: Sequence[str]) -> dict[tuple[str, str], Seri]:
    out: dict[tuple[str, str], Seri] = {}
    for a in d.penyesuaian:
        if a.tahap == tahap and a.jenis in jenis and (metode is None or a.metode == metode):
            if a.harga not in ("CP", "K"):
                raise GalatMesin("Harga penyesuaian harus CP atau K.")
            out.setdefault((a.jenis, a.harga), {})[a.periode] = a.nilai
    return out


def hitung_lapus(lid: int, jenis: str, d: DataLapus, konfig: KonfigTD, sb: Sumbu, referensi: dict[str, Seri],
                 pohon: Pohon, benc: PenyediaBenc) -> HasilLapus:
    tanpa_ka = jenis in TANPA_KA
    per: dict[str, list[ItemSiap]] = {k: [] for k in METODE_HITUNG}
    h = HasilLapus()
    for it in d.item:
        if it.metode not in METODE_HITUNG:
            continue
        siap = selesaikan(it, sb, konfig, referensi, pohon.urai, benc)
        per[it.metode].append(siap)
        h.item[it.id] = HITUNG_METODE[it.metode](siap, sb, konfig.t0, konfig.jangkar_dari_data, tanpa_ka)
    pres = []
    for mt in METODE_HITUNG:
        pr = Empat.nol(len(sb))
        for siap in per[mt]:
            pr.tambah(h.item[siap.id])
        pre = pre_metode(pr, _seri_adj(d, "METODE", mt, JENIS_METODE), sb.periode)
        h.metode[mt] = (pr, pre)
        pres.append(pre)
    pre, post, bn = rekonsiliasi(pres, _seri_adj(d, "REKON", None, JENIS_REKON), sb.periode)
    sim = _seri_adj(d, "SIMULASI", None, ("SIM_NTB",))
    fin = simulasi(bn, sim.get(("SIM_NTB", "CP"), {}), sim.get(("SIM_NTB", "K"), {}), sb.periode)
    h.tahap = {"PRE": pre, "POST": post, "BENC": bn, "FINAL": fin}
    semua = [s for mt in METODE_HITUNG for s in per[mt]]
    masa = {it.id: (it.mulai, it.selesai) for it in d.item}
    h.hash_input = sidik_lapus(lid, jenis, konfig, sb, semua, d.penyesuaian, masa)
    return h
