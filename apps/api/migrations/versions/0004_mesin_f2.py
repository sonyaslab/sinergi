"""F2 Mesin hitung: rumus margin impor, rasio margin tahun dasar, seri kurs (docs/02 §7 dan §11).

- lk.tautan_seri.rumus menerima MARGIN_X_IMPOR (margin perdagangan barang impor, keputusan 4).
- lk.parameter_item.kode menerima R_MARGIN_TD (rasio margin tahun dasar untuk ADHK margin arus barang). Seperti
  RKA_TD, ini rasio tahun dasar (bukan jangkar pengganti), jadi tidak wajib beralasan.
- ref.jenis_seri DEF menerima KURS (seri komponen; boleh ditautkan ke seri referensi kurs).

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-05
"""
from __future__ import annotations

from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE lk.tautan_seri DROP CONSTRAINT tautan_seri_rumus_check")
    op.execute("ALTER TABLE lk.tautan_seri ADD CONSTRAINT tautan_seri_rumus_check CHECK (rumus IS NULL OR rumus IN"
               " ('TPK_X_KAMAR','JANGKAR_X_IH_100','KAPITA_X_PENDUDUK_X_3','MARGIN_X_OUTPUT','MARGIN_X_IMPOR'))")
    op.execute("ALTER TABLE lk.parameter_item DROP CONSTRAINT parameter_item_kode_check")
    op.execute("ALTER TABLE lk.parameter_item ADD CONSTRAINT parameter_item_kode_check"
               " CHECK (kode IN ('RKA_TD','H_TD','IH_TD','R_MARGIN_TD'))")
    op.execute("ALTER TABLE lk.parameter_item DROP CONSTRAINT parameter_item_check")
    op.execute("ALTER TABLE lk.parameter_item ADD CONSTRAINT parameter_item_check"
               " CHECK (kode IN ('RKA_TD','R_MARGIN_TD') OR alasan IS NOT NULL)")
    op.execute("INSERT INTO ref.jenis_seri (metode_kode, kode, nama, wajib, komponen, hanya_td, urutan) VALUES"
               " ('DEF','KURS','Kurs (Rp per US$) untuk nilai impor',false,true,false,10)")


def downgrade() -> None:
    raise NotImplementedError("Gunakan make db-reset untuk kembali ke versi sebelumnya.")
