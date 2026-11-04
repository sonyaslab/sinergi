"""Koneksi basis data.

Aplikasi terhubung sebagai `app_rw` (bukan pemilik tabel) sehingga RLS berlaku. Setiap transaksi menyetel
konteks `app.user_id`, `app.ip`, `app.alasan` dengan `set_config(..., true)` (setara SET LOCAL) agar RLS dan
trigger audit mengenali pengguna.
"""
from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from functools import lru_cache

from sqlalchemy import Connection, Engine, create_engine, text

from .config import pengaturan


@lru_cache
def engine_rw() -> Engine:
    return create_engine(pengaturan().db_url, pool_pre_ping=True, pool_size=10, max_overflow=10)


@lru_cache
def engine_ro() -> Engine:
    return create_engine(pengaturan().db_url_ro, pool_pre_ping=True, pool_size=5, max_overflow=5)


def setel_konteks(conn: Connection, user_id: int | None, ip: str | None, alasan: str | None = None) -> None:
    """SET LOCAL app.user_id / app.ip / app.alasan untuk transaksi berjalan."""
    conn.execute(
        text(
            "SELECT set_config('app.user_id', :u, true), set_config('app.ip', :ip, true),"
            " set_config('app.alasan', :a, true)"
        ),
        {"u": "" if user_id is None else str(user_id), "ip": ip or "", "a": alasan or ""},
    )


@contextmanager
def transaksi(
    user_id: int | None, ip: str | None = None, alasan: str | None = None, engine: Engine | None = None
) -> Iterator[Connection]:
    """Satu transaksi dengan konteks pengguna. Commit bila sukses, rollback bila galat."""
    eng = engine or engine_rw()
    with eng.begin() as conn:
        setel_konteks(conn, user_id, ip, alasan)
        yield conn
