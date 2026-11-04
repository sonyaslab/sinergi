"""Lapisan HTTP: CSRF double-submit bertanda tangan, header keamanan, dan cookie `sinergi_*`."""
from __future__ import annotations

import hashlib

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from ..auth import token as tok
from .config import Pengaturan, pengaturan

COOKIE_AKSES = "sinergi_akses"
COOKIE_REFRESH = "sinergi_refresh"
COOKIE_PRA = "sinergi_pra"
COOKIE_CSRF = "sinergi_csrf"
HEADER_CSRF = "X-CSRF-Token"
METODE_AMAN = {"GET", "HEAD", "OPTIONS"}


def kunci_csrf(p: Pengaturan | None = None) -> str:
    p = p or pengaturan()
    return hashlib.sha256(("csrf:" + p.jwt_secret).encode()).hexdigest()


def setel_cookie(resp: Response, nama: str, nilai: str, umur_detik: int, path: str, http_only: bool = True) -> None:
    resp.set_cookie(nama, nilai, max_age=umur_detik, path=path, httponly=http_only,
                    secure=pengaturan().cookie_secure, samesite="strict")


def hapus_cookie(resp: Response, nama: str, path: str) -> None:
    resp.delete_cookie(nama, path=path, secure=pengaturan().cookie_secure, httponly=True, samesite="strict")


class CsrfMiddleware(BaseHTTPMiddleware):
    """Semua metode yang mengubah data (POST/PUT/PATCH/DELETE) wajib membawa header X-CSRF-Token == cookie."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if request.method not in METODE_AMAN and request.url.path.startswith("/api/"):
            if not tok.csrf_sah(kunci_csrf(), request.cookies.get(COOKIE_CSRF), request.headers.get(HEADER_CSRF)):
                return JSONResponse(status_code=403, content={
                    "kode": "CSRF", "pesan": "Sesi formulir tidak sah. Muat ulang halaman lalu coba lagi."})
        return await call_next(request)


class HeaderKeamananMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        resp = await call_next(request)
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("X-Frame-Options", "DENY")
        resp.headers.setdefault("Referrer-Policy", "no-referrer")
        resp.headers.setdefault("Content-Security-Policy", "default-src 'none'; frame-ancestors 'none'")
        if request.url.path.startswith("/api/"):
            resp.headers.setdefault("Cache-Control", "no-store")
        return resp


def pasang(app: FastAPI) -> None:
    app.add_middleware(CsrfMiddleware)
    app.add_middleware(HeaderKeamananMiddleware)
