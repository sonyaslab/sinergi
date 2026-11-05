"""Mesin hitung SINERGI (modul murni, tanpa I/O).

Rumus wajib: docs/02_RUMUS_ENGINE.md. Oracle: engine_ref/ (golden test: identik relatif ≤ 1e-9).
Pemakaian: `hitung_wilayah(MasukanWilayah(...)) -> HasilWilayah` (worker antrean hitung menulis ke lk.hasil_*).
"""
from .hitung import hitung_wilayah
from .model import (
    VERSI_MESIN,
    DataLapus,
    Empat,
    GalatMesin,
    HasilLapus,
    HasilWilayah,
    Item,
    KonfigTD,
    Lapus,
    MasukanWilayah,
    Penyesuaian,
    SiklusTautan,
    Sumbu,
    Tautan,
    label,
    urut,
)

__all__ = [
    "VERSI_MESIN", "DataLapus", "Empat", "GalatMesin", "HasilLapus", "HasilWilayah", "Item", "KonfigTD", "Lapus",
    "MasukanWilayah", "Penyesuaian", "SiklusTautan", "Sumbu", "Tautan", "hitung_wilayah", "label", "urut",
]
