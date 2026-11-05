"""Aturan perilaku Excel (docs/02 §0): kosong = 0 dalam hitung, bagi 0 = 0, rata-rata mengabaikan kosong."""
from __future__ import annotations

from collections.abc import Iterable

from .model import Seri


def v(s: Seri | None, u: int) -> float:
    if not s:
        return 0.0
    x = s.get(u)
    return 0.0 if x is None else x


def bagi(a: float, b: float) -> float:
    """IFERROR(a/b, 0)."""
    return a / b if b else 0.0


def rata_isi(s: Seri | None, us: Iterable[int]) -> float:
    """AVERAGE yang mengabaikan sel kosong; semua kosong = 0."""
    xs = [s[u] for u in us if s and s.get(u) is not None]
    return sum(xs) / len(xs) if xs else 0.0
