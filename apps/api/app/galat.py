"""Pemetaan galat ke HTTP dengan pesan singkat berbahasa Indonesia.

- SQLSTATE P0423 (putaran terkunci)      -> 423
- SQLSTATE 42501 (RLS / hak akses)       -> 403
- SQLSTATE 23514 (aturan data / trigger) -> 422
- SQLSTATE 23505 (duplikat)              -> 409
- SQLSTATE 23503 (rujukan)               -> 422

Pesan galat tidak pernah memuat nilai baris (angka PDRB) — hanya pesan utama trigger buatan sistem.
"""
from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import DBAPIError
from starlette.exceptions import HTTPException

log = logging.getLogger("sinergi.galat")

PESAN_SQLSTATE: dict[str, tuple[int, str, str]] = {
    "P0423": (423, "PUTARAN_TERKUNCI", "Putaran sudah dikunci. Perubahan tidak dapat disimpan."),
    "42501": (403, "TIDAK_BERHAK", "Anda tidak berhak mengubah data ini."),
    "23505": (409, "DUPLIKAT", "Data yang sama sudah ada."),
    "23503": (422, "RUJUKAN", "Data rujukan tidak ditemukan atau masih dipakai."),
    "23502": (422, "WAJIB_ISI", "Ada isian wajib yang kosong."),
    "23514": (422, "ATURAN_DATA", "Data tidak memenuhi aturan."),
}


class GalatSinergi(Exception):
    """Galat aplikasi dengan status HTTP, kode mesin, dan pesan untuk pengguna."""

    def __init__(self, status: int, kode: str, pesan: str, rincian: object | None = None):
        super().__init__(pesan)
        self.status, self.kode, self.pesan, self.rincian = status, kode, pesan, rincian


def petakan_db(exc: DBAPIError) -> GalatSinergi:
    orig = getattr(exc, "orig", None)
    sqlstate = getattr(orig, "sqlstate", None) or ""
    if sqlstate in PESAN_SQLSTATE:
        status, kode, pesan = PESAN_SQLSTATE[sqlstate]
        diag = getattr(orig, "diag", None)
        # Pesan dari RAISE EXCEPTION trigger sistem (tanpa nama constraint) sudah berbahasa Indonesia dan aman.
        if sqlstate == "23514" and diag is not None and not getattr(diag, "constraint_name", None):
            pesan = getattr(diag, "message_primary", None) or pesan
        return GalatSinergi(status, kode, pesan)
    log.error("Galat basis data SQLSTATE=%s (%s)", sqlstate or "-", type(orig).__name__)
    return GalatSinergi(500, "GALAT_SERVER", "Terjadi kesalahan pada server. Silakan coba lagi atau hubungi admin.")


def _json(g: GalatSinergi) -> JSONResponse:
    isi: dict[str, object] = {"kode": g.kode, "pesan": g.pesan}
    if g.rincian is not None:
        isi["rincian"] = g.rincian
    return JSONResponse(status_code=g.status, content=isi)


def pasang(app: FastAPI) -> None:
    @app.exception_handler(GalatSinergi)
    async def _galat_sinergi(_: Request, exc: GalatSinergi) -> JSONResponse:
        return _json(exc)

    @app.exception_handler(DBAPIError)
    async def _galat_db(_: Request, exc: DBAPIError) -> JSONResponse:
        return _json(petakan_db(exc))

    @app.exception_handler(HTTPException)
    async def _galat_http(_: Request, exc: HTTPException) -> JSONResponse:
        pesan = exc.detail if isinstance(exc.detail, str) else "Permintaan tidak dapat diproses."
        if exc.status_code == 404 and pesan == "Not Found":
            pesan = "Halaman atau data tidak ditemukan."
        elif exc.status_code == 405:
            pesan = "Metode tidak diizinkan."
        return JSONResponse(status_code=exc.status_code, content={"kode": "HTTP", "pesan": pesan},
                            headers=getattr(exc, "headers", None))

    @app.exception_handler(RequestValidationError)
    async def _galat_validasi(_: Request, exc: RequestValidationError) -> JSONResponse:
        kolom = [".".join(str(x) for x in e.get("loc", ())[1:]) for e in exc.errors()]
        return JSONResponse(
            status_code=422,
            content={"kode": "ISIAN_TIDAK_VALID", "pesan": "Isian tidak valid. Periksa kembali isian Anda.",
                     "rincian": [k for k in kolom if k]},
        )
