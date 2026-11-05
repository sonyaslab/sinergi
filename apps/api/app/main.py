"""Aplikasi FastAPI SINERGI. Jalankan: uvicorn --factory sinergi_api.app.main:buat_app"""
from __future__ import annotations

import logging

from fastapi import FastAPI
from sqlalchemy import text

from .. import VERSI
from ..auth.router import router as auth_router
from ..data_dasar.router import router as data_dasar_router
from ..impor.router import router as impor_router
from ..master.router import router as master_router
from ..putaran.biaya_antara import router as biaya_antara_router
from ..putaran.hasil import router as hasil_router
from ..putaran.penyesuaian import router as penyesuaian_router
from ..putaran.router import router as putaran_router
from ..putaran.status import router as status_router
from . import db, galat, keamanan_http
from .config import pengaturan


def buat_app() -> FastAPI:
    pengaturan()  # validasi konfigurasi sejak awal (gagal cepat bila rahasia produksi kosong)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    app = FastAPI(title="SINERGI API", version=VERSI, docs_url=None, redoc_url=None, openapi_url=None)
    galat.pasang(app)
    keamanan_http.pasang(app)
    app.include_router(auth_router)
    app.include_router(master_router)
    app.include_router(impor_router)
    app.include_router(data_dasar_router)
    for r in (putaran_router, status_router, penyesuaian_router, hasil_router, biaya_antara_router):
        app.include_router(r)

    @app.get("/api/kesehatan", include_in_schema=False)
    def kesehatan() -> dict:
        with db.engine_rw().connect() as conn:
            conn.execute(text("SELECT 1"))
        return {"status": "ok", "versi": VERSI}

    return app

