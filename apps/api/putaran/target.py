"""Bantuan input penyesuaian: nilai dari target (keputusan 18 §11). Modul murni; rumus mesin TIDAK berubah.

Nilai yang disimpan tetap nilai penyesuaian; target hanya membantu menghitungnya dengan membalik rumus docs/02 §6
pada tahap yang sama. `hasil` = hasil tahap itu TANPA penyesuaian yang sedang diisi (kunci yang sama), `dasar` = basis
proporsi NTB:

| Jenis              | Tahap hasil      | Kenaikan NTB per 1 satuan adj | Target output          |
|--------------------|------------------|-------------------------------|------------------------|
| ADJ1, ADJ2, SC     | PRE metode       | r = NTB PR ÷ Output PR metode | adj = target − Output  |
| ADJ3               | POST (= PRE)     | r = NTB PRE ÷ Output PRE      | adj = target − Output  |
| ADJ4_NTB           | BENC             | 1                             | —                      |
| ADJ4_OUTPUT        | BENC             | 0 (hanya target output)       | adj = target − Output  |
| SIM_NTB            | FINAL            | 1                             | —                      |

- target NTB: adj = (target − NTB hasil) ÷ kenaikan; kenaikan 0 -> galat (isi nilai langsung).
- target laju y-on-y g%: target NTB = NTB tahap yang sama pada t−4 × (1 + g/100) (SIM_NTB = docs/02 §6).
- target implisit (hanya ADHB): target NTB ADHB = implisit × NTB ADHK tahap yang sama pada t ÷ 100 (docs/02 §6).
Penyesuaian yang diisi hanya memengaruhi (harga, t) miliknya, sehingga t−4 dan pasangan ADHK pada t tidak berubah.
"""
from __future__ import annotations

from dataclasses import dataclass

from ..engine.model import Empat, GalatMesin
from ..engine.umum import bagi

METODE = ("ADJ1", "ADJ2", "SC")
REKON = ("ADJ3", "ADJ4_OUTPUT", "ADJ4_NTB")
JENIS_NTB = ("ADJ1", "ADJ2", "SC", "ADJ3", "ADJ4_NTB", "SIM_NTB")  # target NTB/laju/implisit tersedia
JENIS_OUTPUT = ("ADJ1", "ADJ2", "SC", "ADJ3", "ADJ4_OUTPUT")  # target output tersedia
MODE = ("nilai", "target_ntb", "target_output", "target_laju", "target_implisit")


class GalatTarget(GalatMesin):
    """Target tidak dapat dibalik menjadi nilai penyesuaian (pesan aman, tanpa angka)."""


@dataclass(frozen=True)
class Rincian:
    nilai: float  # nilai penyesuaian yang disimpan
    target_ntb: float | None = None
    target_output: float | None = None
    ntb_sebelum: float | None = None
    output_sebelum: float | None = None


def mode_untuk(jenis: str, harga: str) -> list[str]:
    m = ["nilai"]
    if jenis in JENIS_NTB:
        m += ["target_ntb", "target_laju"] + (["target_implisit"] if harga == "CP" else [])
    if jenis in JENIS_OUTPUT:
        m.append("target_output")
    return m


def _ambil(e: Empat, harga: str, t: int) -> tuple[float, float]:
    """(output, NTB) pada indeks t untuk harga CP/K."""
    return (e.out_cp[t], e.gva_cp[t]) if harga == "CP" else (e.out_k[t], e.gva_k[t])


def nilai_penyesuaian(jenis: str, harga: str, mode: str, target: float, t: int, t4: int | None, hasil: Empat,
                      dasar: Empat | None = None) -> Rincian:
    """Nilai penyesuaian `jenis` (harga CP/K, indeks periode t) agar tahap hasilnya mencapai target."""
    if mode not in mode_untuk(jenis, harga):
        raise GalatTarget("Cara isi ini tidak tersedia untuk jenis penyesuaian tersebut.")
    out0, ntb0 = _ambil(hasil, harga, t)
    if mode == "nilai":
        return Rincian(target, ntb_sebelum=ntb0, output_sebelum=out0)
    if mode == "target_output":
        return Rincian(target - out0, target_output=target, ntb_sebelum=ntb0, output_sebelum=out0)
    if mode == "target_laju":
        if t4 is None:
            raise GalatTarget("Triwulan pembanding (t−4) tidak ada di cakupan putaran ini.")
        target_ntb = _ambil(hasil, harga, t4)[1] * (1 + target / 100)
    elif mode == "target_implisit":
        target_ntb = target * _ambil(hasil, "K", t)[1] / 100
    else:
        target_ntb = target
    if jenis in METODE or jenis == "ADJ3":
        if dasar is None:
            raise GalatTarget("Basis proporsi NTB tidak tersedia.")
        o, g = _ambil(dasar, harga, t)
        naik = bagi(g, o)
    else:
        naik = 1.0
    if naik == 0:
        raise GalatTarget("Rasio NTB terhadap output 0 pada triwulan ini; target NTB tidak dapat dicapai lewat"
                          " penyesuaian output. Isi nilai langsung.")
    return Rincian((target_ntb - ntb0) / naik, target_ntb=target_ntb, ntb_sebelum=ntb0, output_sebelum=out0)
