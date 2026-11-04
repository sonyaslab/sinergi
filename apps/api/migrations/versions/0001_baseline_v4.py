"""Baseline skema + seed master SINERGI versi 4 (salinan beku db/schema.sql dan db/seed_ref.sql pada v4).

Revision ID: 0001
Revises:
Create Date: 2026-11-04

Berkas di migrations/baseline/ TIDAK boleh diubah. Perubahan skema berikutnya = migrasi baru + sinkron db/schema.sql.
"""
from __future__ import annotations

import re
from pathlib import Path

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

BASE = Path(__file__).resolve().parents[1] / "baseline"


def _jalankan(sql: str) -> None:
    # Berkas seed memuat BEGIN;/COMMIT; sendiri; Alembic sudah membungkus migrasi dalam transaksi.
    sql = re.sub(r"(?m)^\s*(BEGIN|COMMIT)\s*;\s*$", "", sql)
    # Banyak pernyataan sekaligus (DO $$ ... $$) -> eksekusi langsung lewat driver (protokol query sederhana).
    op.get_bind().connection.driver_connection.execute(sql)


def upgrade() -> None:
    _jalankan((BASE / "schema_v4.sql").read_text(encoding="utf-8"))
    _jalankan((BASE / "seed_ref_v4.sql").read_text(encoding="utf-8"))


def downgrade() -> None:
    raise NotImplementedError("Baseline tidak dapat di-downgrade; buat ulang basis data (make db-reset).")
