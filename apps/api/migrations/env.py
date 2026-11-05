"""Lingkungan Alembic. Migrasi dijalankan sebagai app_owner (pemilik tabel), bukan app_rw."""
from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

from sinergi_api.app.config import Pengaturan

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

url = context.get_x_argument(as_dictionary=True).get("url") or Pengaturan().db_url_owner


def run_migrations_online() -> None:
    engine = create_engine(url, poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=None, transaction_per_migration=True)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    raise SystemExit("Mode offline tidak didukung; jalankan terhadap basis data.")
run_migrations_online()
