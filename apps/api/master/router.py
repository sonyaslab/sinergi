"""Router master data (F1)."""
from __future__ import annotations

from fastapi import APIRouter

from . import lapus, pengguna, referensi, tahun_dasar

router = APIRouter()
for _m in (tahun_dasar, lapus, referensi, pengguna):
    router.include_router(_m.router)
