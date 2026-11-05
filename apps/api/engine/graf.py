"""Pohon lapus dan graf dependensi antarlapus (tautan HASIL_LAPUS / MARGIN_X_OUTPUT), dengan deteksi siklus."""
from __future__ import annotations

from collections.abc import Iterable, Sequence

from .model import BERITEM, GalatMesin, Lapus, SiklusTautan


class Pohon:
    def __init__(self, baris: Sequence[Lapus]):
        self.baris = sorted(baris, key=lambda r: r.urutan)
        self.b = {r.id: r for r in self.baris}
        self.anak: dict[int, list[int]] = {}
        for r in self.baris:
            if r.induk_id is not None:
                self.anak.setdefault(r.induk_id, []).append(r.id)

    def urut(self, ids: Iterable[int]) -> list[int]:
        return sorted(set(ids), key=lambda i: self.b[i].urutan)

    def daun_data(self, lid: int) -> list[int]:
        """Lapus berdata di bawah (atau sama dengan) lid; kelompok diurai ke anggota."""
        r = self.b.get(lid)
        if r is None:
            raise GalatMesin(f"Lapus sumber tautan (id {lid}) tidak ada atau tidak aktif.")
        if r.jenis in BERITEM:
            return [lid]
        if r.jenis in ("kategori", "sub"):
            return [d for a in self.anak.get(lid, []) for d in self.daun_data(a)]
        if r.jenis == "kelompok":
            return [d for a in r.anggota for d in self.daun_data(a)]
        raise GalatMesin(f"Lapus sumber tautan {r.kode} adalah baris total, tidak boleh dipakai.")

    def urai(self, ids: Iterable[int]) -> list[int]:
        return self.urut(d for x in ids for d in self.daun_data(x))

    def leluhur_migas(self, lid: int) -> bool:
        p = self.b[lid].induk_id
        while p is not None:
            if self.b[p].is_migas:
                return True
            p = self.b[p].induk_id
        return False


def urutkan(pohon: Pohon, simpul: Sequence[int], gantung: dict[int, set[int]]) -> list[int]:
    """Urutan hitung topologis (stabil menurut urutan pohon). Sumber tanpa data diabaikan (bernilai 0)."""
    simpul_set = set(simpul)
    for i in simpul:
        if i in gantung.get(i, set()):
            raise SiklusTautan(f"Tautan lapus {pohon.b[i].kode} merujuk dirinya sendiri.")
    masuk = {i: {s for s in gantung.get(i, set()) if s in simpul_set} for i in simpul}
    hasil: list[int] = []
    selesai: set[int] = set()
    sisa = list(pohon.urut(simpul))
    while sisa:
        siap = next((i for i in sisa if masuk[i] <= selesai), None)
        if siap is None:
            kode = ", ".join(pohon.b[i].kode for i in sisa if masuk[i] - selesai)
            raise SiklusTautan(f"Tautan antarlapus membentuk siklus: {kode}.")
        hasil.append(siap)
        selesai.add(siap)
        sisa.remove(siap)
    return hasil
