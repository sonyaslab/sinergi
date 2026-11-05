"""Muat master untuk pembaca templat dari basis data (ref.*)."""
from __future__ import annotations

from collections import defaultdict

from sqlalchemy import Connection, text

from .templat import InfoLapus, KonteksTemplat


def muat_konteks(conn: Connection, tahun_dasar_id: int) -> KonteksTemplat:
    q = {"td": tahun_dasar_id}
    baris = conn.execute(text(
        "SELECT id, kode, jenis, induk_id FROM ref.lapus WHERE tahun_dasar_id = :td AND aktif"), q).all()
    induk = {r.id: r.induk_id for r in baris}
    kode = {r.id: r.kode for r in baris}

    def akar(i: int) -> int:
        while induk.get(i) is not None:
            i = induk[i]
        return i

    lapus = {r.kode: InfoLapus(r.kode, r.jenis, None if r.jenis in ("top", "sop") else kode[akar(r.id)])
             for r in baris}
    seri: dict[str, list[str]] = defaultdict(list)
    wajib: dict[str, set[str]] = defaultdict(set)
    for m, k, w in conn.execute(text("SELECT metode_kode, kode, wajib FROM ref.jenis_seri ORDER BY metode_kode,"
                                     " urutan")):
        seri[m].append(k)
        if w:
            wajib[m].add(k)
    maks = {str(r[0]): int(r[1]) for r in conn.execute(text("SELECT kode, maks_item FROM ref.metode"))}
    jp = {r.kode: (r.tahap, r.wajib_alasan) for r in conn.execute(text(
        "SELECT kode, tahap, wajib_alasan FROM ref.jenis_penyesuaian"))}
    wil = {r[0].strip() for r in conn.execute(text("SELECT kode FROM ref.wilayah WHERE aktif"))}
    return KonteksTemplat(wil, lapus, dict(seri), dict(wajib), maks, jp)
