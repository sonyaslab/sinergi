"""Agregasi pohon (docs/02 §8, keputusan 1 dan 7 §11), tahap BENC dan FINAL.

- kategori/subkategori = Σ anak; kelompok publikasi = Σ anggota (tidak menambah total);
- NTB = Σ akar pohon (kategori/daun tanpa induk); TOP.SOP = Σ TOP − Σ SOP; PDRB = NTB + TOP.SOP
  (TD2010 tanpa TOP/SOP: PDRB = Σ kategori);
- PDRB tanpa migas = PDRB − Σ lapus is_migas (lapus berbendera yang tidak punya leluhur berbendera).
Baris tanpa satu pun sumber berdata tidak diberi hasil (tabel pokok menampilkannya kosong).
"""
from __future__ import annotations

from collections.abc import Callable

from .graf import Pohon
from .model import BERITEM, Empat


def agregasikan(pohon: Pohon, hasil: dict[int, dict[str, Empat]], n: int, tahap: tuple[str, ...] = ("BENC", "FINAL"),
                ) -> dict[int, dict[str, Empat]]:
    """hasil: lapus berdata -> {tahap: Empat}. Kembalikan baris non-data -> {tahap: Empat}."""
    akar = [r.id for r in pohon.baris if r.induk_id is None and r.jenis in ("kategori", "sub", "daun")]
    top = [r.id for r in pohon.baris if r.jenis == "top"]
    sop = [r.id for r in pohon.baris if r.jenis == "sop"]
    migas = [r.id for r in pohon.baris if r.is_migas and not pohon.leluhur_migas(r.id)]
    keluar: dict[int, dict[str, Empat]] = {}

    for th in tahap:
        memo: dict[int, Empat | None] = {}

        def nilai(lid: int, th: str = th, memo: dict[int, Empat | None] = memo) -> Empat | None:
            if lid in memo:
                return memo[lid]
            r = pohon.b[lid]
            h: Empat | None
            if r.jenis in BERITEM:
                h = hasil.get(lid, {}).get(th)
            elif r.jenis in ("kategori", "sub"):
                h = sigma(pohon.anak.get(lid, []))
            elif r.jenis == "kelompok":
                h = sigma(pohon.urut(r.anggota))
            elif r.jenis == "ntb":
                h = sigma(akar)
            elif r.jenis in ("topsop", "pdrb", "pdrb_nonmigas"):
                nt, tp, sp = sigma(akar), sigma(top), sigma(sop)
                if nt is None and tp is None and sp is None:
                    h = None
                else:
                    ts = (tp or Empat.nol(n)).kurang(sp or Empat.nol(n))
                    if r.jenis == "topsop":
                        h = ts
                    else:
                        h = Empat.nol(n)
                        h.tambah(nt or Empat.nol(n))
                        h.tambah(ts)
                        if r.jenis == "pdrb_nonmigas":
                            h = h.kurang(sigma(migas) or Empat.nol(n))
            else:
                h = None
            memo[lid] = h
            return h

        def sigma(ids: list[int], nilai: Callable[[int], Empat | None] = nilai) -> Empat | None:
            hs = [h for h in (nilai(i) for i in ids) if h is not None]
            if not hs:
                return None
            out = Empat.nol(n)
            for h in hs:
                out.tambah(h)
            return out

        for r in pohon.baris:
            if r.jenis not in BERITEM:
                h = nilai(r.id)
                if h is not None:
                    keluar.setdefault(r.id, {})[th] = h
    return keluar
