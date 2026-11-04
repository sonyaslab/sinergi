"""Master data (F0: daftar tahun dasar untuk pemilih di header; CRUD lengkap di F1)."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import Connection, text

from ..app.deps import koneksi

router = APIRouter(prefix="/api", tags=["master"])

# Urutan bawaan pemilih: produksi -> paralel -> rencana -> arsip (dari kolom status master, bukan kode TD).
_URUT_STATUS = "CASE status WHEN 'produksi' THEN 0 WHEN 'paralel' THEN 1 WHEN 'rencana' THEN 2 ELSE 3 END"


@router.get("/tahun-dasar")
def daftar_tahun_dasar(conn: Connection = Depends(koneksi)) -> list[dict]:
    rows = conn.execute(text(
        "SELECT id, kode, tahun_dasar, status, klasifikasi, tahun_awal_seri, tahun_baseline_eks, keterangan"
        f"  FROM ref.tahun_dasar ORDER BY {_URUT_STATUS}, tahun_dasar DESC"
    )).mappings().all()
    return [dict(r) for r in rows]
