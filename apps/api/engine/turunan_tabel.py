"""Tabel turunan per baris pohon (docs/02 §8.6). Sel kosong (None) bila pembagi 0 atau periode pembanding tidak ada.

Semua fungsi menerima seri sepanjang sumbu yang sama (indeks 0 = sumbu.awal).
- distribusi = ADHB ÷ PDRB ADHB × 100
- laju q-to-q / y-on-y = X(t) ÷ X(t−1|t−4) × 100 − 100; c-to-c = Σ T1..t ÷ Σ T1..t tahun lalu × 100 − 100
- implisit = ADHB ÷ ADHK × 100, beserta lajunya (c-to-c memakai implisit kumulatif)
- SoG = (X(t) − X(pembanding)) ÷ PDRB ADHK(pembanding) × 100 (pembagi PDRB ADHK, temuan T6)
"""
from __future__ import annotations

from collections.abc import Sequence

from .model import Sumbu

Nilai = float | None


def _bagi(a: float, b: float) -> Nilai:
    return None if b == 0 else a / b


def distribusi(x_cp: Sequence[float], pdrb_cp: Sequence[float]) -> list[Nilai]:
    return [None if (q := _bagi(a, b)) is None else q * 100 for a, b in zip(x_cp, pdrb_cp, strict=True)]


def implisit(cp: Sequence[float], k: Sequence[float]) -> list[Nilai]:
    return [None if (q := _bagi(a, b)) is None else q * 100 for a, b in zip(cp, k, strict=True)]


def laju(x: Sequence[Nilai], lag: int) -> list[Nilai]:
    out: list[Nilai] = []
    for t in range(len(x)):
        a, b = x[t], (x[t - lag] if t >= lag else None)
        q = None if a is None or b is None else _bagi(a, b)
        out.append(None if q is None else q * 100 - 100)
    return out


def laju_qtq(x: Sequence[Nilai]) -> list[Nilai]:
    return laju(x, 1)


def laju_yoy(x: Sequence[Nilai]) -> list[Nilai]:
    return laju(x, 4)


def _kumulatif(x: Sequence[float], sb: Sumbu, t: int) -> float | None:
    """Σ triwulan I s.d. triwulan t pada tahun yang sama; None bila awal tahun di luar sumbu."""
    if t < 0:
        return None
    q = (sb.awal + t) % 4
    if t - q < 0:
        return None
    return sum(x[t - q + i] for i in range(q + 1))


def laju_ctc(x: Sequence[float], sb: Sumbu) -> list[Nilai]:
    out: list[Nilai] = []
    for t in range(len(x)):
        a, b = _kumulatif(x, sb, t), _kumulatif(x, sb, t - 4)
        q = None if a is None or b is None else _bagi(a, b)
        out.append(None if q is None else q * 100 - 100)
    return out


def implisit_ctc(cp: Sequence[float], k: Sequence[float], sb: Sumbu) -> list[Nilai]:
    out: list[Nilai] = []
    for t in range(len(cp)):
        a, b = _kumulatif(cp, sb, t), _kumulatif(k, sb, t)
        q = None if a is None or b is None else _bagi(a, b)
        out.append(None if q is None else q * 100)
    return out


def laju_implisit_ctc(cp: Sequence[float], k: Sequence[float], sb: Sumbu) -> list[Nilai]:
    return laju(implisit_ctc(cp, k, sb), 4)


def sog(x_k: Sequence[float], pdrb_k: Sequence[float], lag: int) -> list[Nilai]:
    out: list[Nilai] = []
    for t in range(len(x_k)):
        q = None if t < lag else _bagi(x_k[t] - x_k[t - lag], pdrb_k[t - lag])
        out.append(None if q is None else q * 100)
    return out


def sog_ctc(x_k: Sequence[float], pdrb_k: Sequence[float], sb: Sumbu) -> list[Nilai]:
    out: list[Nilai] = []
    for t in range(len(x_k)):
        a, b, p = _kumulatif(x_k, sb, t), _kumulatif(x_k, sb, t - 4), _kumulatif(pdrb_k, sb, t - 4)
        q = None if a is None or b is None or p is None else _bagi(a - b, p)
        out.append(None if q is None else q * 100)
    return out
