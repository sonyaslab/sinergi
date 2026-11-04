"""Penulisan jejak audit aplikasi (login, logout, ekspor, dsb.).

Perubahan data tabel dicatat otomatis oleh trigger `audit.catat()`. Fungsi di sini untuk peristiwa yang tidak
mengubah tabel data. `audit.log` append-only dan berantai hash (trigger `audit.rantai_hash`).
Jangan menaruh sandi, token, rahasia TOTP, atau angka PDRB di `nilai_baru`.
"""
from __future__ import annotations

import json
from datetime import UTC, datetime

from sqlalchemy import Connection, text


def catat(
    conn: Connection,
    aksi: str,
    entitas: str,
    entitas_id: str | None = None,
    pengguna_id: int | None = None,
    ip: str | None = None,
    nilai_baru: dict | None = None,
    alasan: str | None = None,
    putaran_id: int | None = None,
) -> None:
    conn.execute(
        text(
            "INSERT INTO audit.log (pengguna_id, ip, aksi, entitas, entitas_id, putaran_id, nilai_baru, alasan, hash)"
            " VALUES (:u, CAST(NULLIF(:ip, '') AS inet), :aksi, :ent, :eid, :put, CAST(:baru AS jsonb), :alasan, 'x')"
        ),
        {
            "u": pengguna_id,
            "ip": ip or "",
            "aksi": aksi,
            "ent": entitas,
            "eid": entitas_id,
            "put": putaran_id,
            "baru": json.dumps(nilai_baru, ensure_ascii=False) if nilai_baru is not None else None,
            "alasan": alasan,
        },
    )


def tanda_air(username: str, ekspor_id: int, waktu: datetime | None = None) -> str:
    w = (waktu or datetime.now(UTC)).astimezone(UTC).strftime("%Y-%m-%d %H:%M UTC")
    return f"SINERGI - RAHASIA - {username} - {w} - ekspor #{ekspor_id}"


def catat_ekspor(conn: Connection, pengguna_id: int, username: str, jenis: str, parameter: dict,
                 ip: str | None = None) -> str:
    """Catat ekspor ke audit.ekspor + audit.log dan kembalikan teks tanda air untuk berkas ekspor."""
    eid = conn.execute(text("SELECT nextval(pg_get_serial_sequence('audit.ekspor', 'id')), now()")).one()
    ta = tanda_air(username, eid[0], eid[1])
    conn.execute(
        text("INSERT INTO audit.ekspor (id, pengguna_id, waktu, jenis, parameter, tanda_air) "
             "VALUES (:id, :u, :w, :j, CAST(:p AS jsonb), :ta)"),
        {"id": eid[0], "u": pengguna_id, "w": eid[1], "j": jenis,
         "p": json.dumps(parameter, ensure_ascii=False), "ta": ta},
    )
    catat(conn, "EKSPOR", "audit.ekspor", str(eid[0]), pengguna_id, ip, {"jenis": jenis, "parameter": parameter})
    return ta
