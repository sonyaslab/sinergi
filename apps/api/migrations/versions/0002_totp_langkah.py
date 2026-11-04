"""Kode TOTP tidak boleh dipakai ulang: simpan langkah waktu terakhir yang diterima (ASVS 2.8.4).

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-04
"""
from __future__ import annotations

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE sec.pengguna ADD COLUMN totp_langkah_terakhir bigint")
    op.execute("COMMENT ON COLUMN sec.pengguna.totp_langkah_terakhir IS "
               "'Langkah waktu (unix/30) kode TOTP terakhir yang diterima; kode dengan langkah <= ini ditolak'")


def downgrade() -> None:
    op.execute("ALTER TABLE sec.pengguna DROP COLUMN totp_langkah_terakhir")
