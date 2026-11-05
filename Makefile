# SINERGI — perintah kerja. Variabel dari .env (bila ada) diekspor ke semua perintah.
SHELL := /bin/bash
-include .env
export

PY  ?= python
API := apps/api
WEB := apps/web
SINERGI_DB_ADMIN_URL ?= postgresql://postgres:postgres@localhost:5432/postgres
export SINERGI_DB_ADMIN_URL

.PHONY: up down logs db-reset migrate admin dev-api dev-web test test-oracle test-skema test-api test-web \
        golden lint tls-dev install

up:            ## docker compose up (db, migrate, api, worker, web)
	docker compose up -d --build

down:
	docker compose down

logs:
	docker compose logs -f --tail=100

install:       ## pasang dependensi pengembangan (Python 3.12 venv aktif + Node 22)
	$(PY) -m pip install -e "$(API)[dev]"
	cd $(WEB) && npm ci --no-audit --no-fund

db-reset:      ## buat ulang DB `sinergi`: peran + alembic baseline (db/schema.sql + db/seed_ref.sql) + migrasi
	$(PY) -m sinergi_api.dbadmin reset

migrate:
	$(PY) -m sinergi_api.dbadmin migrasi

admin:         ## make admin U=nama.admin N="Nama Lengkap"  (sandi sementara dicetak sekali)
	$(PY) -m sinergi_api.cli buat-pengguna --username "$(U)" --nama "$(N)" --peran admin

dev-api:
	cd $(API) && uvicorn --factory sinergi_api.app.main:buat_app --reload --port 8000

dev-web:
	cd $(WEB) && npm run dev

test: test-oracle test-skema test-api test-web   ## pytest (unit, api, rls) + db/test_schema.sql + vitest

test-oracle:   ## uji mesin rujukan engine_ref
	$(PY) -m pytest -q engine_ref

test-skema:    ## DB sinergi_test_skema lewat Alembic, lalu db/test_schema.sql (harus 16 OK)
	$(PY) -m sinergi_api.dbadmin uji-skema

test-api:      ## pytest apps/api (unit, api, rls, sinkron skema) pada DB sinergi_test
	cd $(API) && $(PY) -m pytest

test-web:
	cd $(WEB) && npx vitest run

golden:        ## golden test: sintetis (selalu) + data LK Put 0 di golden/ atau SINERGI_GOLDEN (mesin internal)
	cd $(API) && $(PY) -m pytest -m golden tests/golden

lint:
	cd $(API) && ruff check . && mypy .
	cd $(WEB) && npx eslint . && npx tsc -b --noEmit

tls-dev:       ## sertifikat swatanda untuk pengembangan (deploy/tls/, tidak di-commit)
	mkdir -p deploy/tls && openssl req -x509 -nodes -newkey rsa:2048 -days 365 -subj "/CN=sinergi.local" \
	  -keyout deploy/tls/sinergi.key -out deploy/tls/sinergi.crt
