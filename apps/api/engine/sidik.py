"""Sidik (hash) masukan: SHA-256 atas JSON kanonik semua masukan yang dipakai satu baris hasil (temuan T3, V15)."""
from __future__ import annotations

import hashlib
import json
from typing import Any

from .model import VERSI_MESIN, ItemSiap, KonfigTD, Penyesuaian, Sumbu


def sidik(obj: Any) -> str:
    teks = json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(teks.encode()).hexdigest()


def _seri(s: dict[int, float] | None) -> list[list[float]] | None:
    return None if s is None else [[u, s[u]] for u in sorted(s)]


def sidik_lapus(lapus_id: int, jenis: str, konfig: KonfigTD, sumbu: Sumbu, item: list[ItemSiap],
                penyesuaian: list[Penyesuaian], mulai_selesai: dict[int, tuple[int | None, int | None]]) -> str:
    return sidik({
        "versi": VERSI_MESIN, "td": [konfig.tahun_baseline, konfig.jangkar_dari_data],
        "sumbu": [sumbu.awal, sumbu.akhir],
        "lapus": [lapus_id, jenis],
        "item": [[i.id, i.metode, i.jenis_indeks, list(mulai_selesai.get(i.id, (None, None))),
                  sorted(i.parameter.items()), {k: _seri(s) for k, s in i.seri.items()}, _seri(i.out_k)] for i in item],
        "penyesuaian": sorted([a.tahap, a.metode or "", a.jenis, a.harga, a.periode, a.nilai] for a in penyesuaian),
    })


def sidik_agregat(lapus_id: int, jenis: str, sumber: list[str]) -> str:
    return sidik({"versi": VERSI_MESIN, "lapus": [lapus_id, jenis], "sumber": sumber})
