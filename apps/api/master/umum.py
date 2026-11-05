"""Utilitas bersama master data: hapus-atau-nonaktifkan, normalisasi teks, galat standar."""
from __future__ import annotations

import re
from collections.abc import Callable
from typing import Literal

from sqlalchemy import Connection, text
from sqlalchemy.exc import IntegrityError

from ..app.galat import GalatSinergi

HasilHapus = Literal["dihapus", "dinonaktifkan"]


def rapikan(teks: str | None) -> str:
    """Trim dan satukan spasi ganda (temuan S11: nama tidak baku)."""
    return re.sub(r"\s+", " ", (teks or "").strip())


def tidak_ada(apa: str) -> GalatSinergi:
    return GalatSinergi(404, "TIDAK_ADA", f"{apa} tidak ditemukan.")


def tidak_valid(pesan: str) -> GalatSinergi:
    return GalatSinergi(422, "TIDAK_VALID", pesan)


def hapus_atau_nonaktifkan(
    conn: Connection,
    hapus: Callable[[Connection], int],
    nonaktifkan: Callable[[Connection], int],
    apa: str,
) -> HasilHapus:
    """Hapus = nonaktifkan bila sudah dipakai data.

    `hapus` dijalankan dalam savepoint; bila ditolak foreign key (SQLSTATE 23503 = masih dirujuk data), savepoint
    dibatalkan dan `nonaktifkan` dijalankan. Kedua fungsi mengembalikan jumlah baris terdampak.
    """
    try:
        with conn.begin_nested():
            n = hapus(conn)
        if n == 0:
            raise tidak_ada(apa)
        return "dihapus"
    except IntegrityError as e:
        if getattr(e.orig, "sqlstate", None) != "23503":
            raise
    if nonaktifkan(conn) == 0:
        raise tidak_ada(apa)
    return "dinonaktifkan"


def sql_hapus(sql: str, **param: object) -> Callable[[Connection], int]:
    return lambda c: c.execute(text(sql), param).rowcount


def pesan_hapus(apa: str, hasil: HasilHapus) -> dict:
    if hasil == "dihapus":
        return {"hasil": hasil, "pesan": f"{apa} dihapus."}
    return {"hasil": hasil, "pesan": f"{apa} sudah dipakai data, jadi dinonaktifkan (riwayat tetap utuh)."}
