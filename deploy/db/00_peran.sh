#!/bin/bash
# Dijalankan sekali oleh image postgres saat volume data masih kosong (superuser).
# Membuat peran login aplikasi dan DB `sinergi` milik app_owner. Skema dibuat oleh layanan `migrate` (Alembic).
set -euo pipefail
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname postgres \
  -v pw_owner="$SINERGI_DB_PASS_OWNER" -v pw_rw="$SINERGI_DB_PASS_RW" -v pw_ro="$SINERGI_DB_PASS_RO" <<'EOSQL'
CREATE ROLE app_owner LOGIN PASSWORD :'pw_owner';
CREATE ROLE app_rw LOGIN PASSWORD :'pw_rw';
CREATE ROLE app_ro LOGIN PASSWORD :'pw_ro';
CREATE DATABASE sinergi OWNER app_owner ENCODING 'UTF8' TEMPLATE template0;
REVOKE ALL ON DATABASE sinergi FROM PUBLIC;
GRANT CONNECT ON DATABASE sinergi TO app_rw, app_ro;
EOSQL
