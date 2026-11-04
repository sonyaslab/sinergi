# Paket kerja SINERGI — Sistem Neraca Ekonomi Regional Terintegrasi (versi 4)

SINERGI adalah sistem web BPS Provinsi Kalimantan Utara untuk menghitung PDRB triwulanan menurut lapangan usaha. Sistem ini menggantikan LK Excel yang terpisah per kategori. Nama lama selama perancangan: SIKALTARA LK.

Paket ini siap dipakai di Claude Code untuk membangun sistem LK PDRB terintegrasi BPS Provinsi Kalimantan Utara.

## Isi

| Folder/berkas | Isi |
|---|---|
| `CLAUDE.md` | aturan kerja yang otomatis dibaca Claude Code |
| `prompts/PROMPT_AGENT_SINERGI_v2.md` | prompt induk + prompt fase F0–F7 |
| `docs/` | 00 temuan proses bisnis, 01 rancangan, 02 rumus mesin, 03 arsitektur, 04 rebasing, 05 templat & impor |
| `db/` | `schema.sql`, `seed_ref.sql` (pohon lapus TD2010 & TD2025, kelompok, konkordansi, metode, seri, validasi, peran), `test_schema.sql` |
| `engine_ref/` | mesin hitung rujukan (oracle) + uji unit |
| `tools/` | pembaca LK 01 xlsm, pembaca templat, validasi mesin vs LK |
| `templates/` | templat data dasar KOSONG TD2010 dan TD2025 |
| `apps/api/` | paket `sinergi_api` (FastAPI, Alembic, auth, mesin hitung mulai F2) |
| `apps/web/` | `sinergi-web` (React 18 + TypeScript + Vite + Tailwind) |
| `deploy/` | skrip peran DB untuk Compose, konfigurasi Nginx (TLS, CSP, batas laju) |

## Langkah

1. Salin folder ini menjadi repo baru bernama `sinergi` (`git init`).
2. Uji cepat basis data dengan PostgreSQL 16:
   ```
   createdb sinergi_test
   psql -d sinergi_test -f db/schema.sql
   psql -d sinergi_test -f db/seed_ref.sql
   psql -d sinergi_test -f db/test_schema.sql
   ```
   Uji dianggap lulus bila muncul 10 baris berawalan "OK".
3. Uji mesin rujukan: `python -m pytest engine_ref`.
4. Buka Claude Code di folder repo. Tempel PROMPT INDUK, lalu jalankan fase F0 sampai F7 berurutan.

Templat TERISI dan berkas LK (.xlsm) bersifat rahasia dan tidak boleh di-commit.

## Menjalankan (status: F0 Fondasi)

Dengan Docker (server internal):

```bash
cp .env.example .env          # lalu ganti semua rahasia
make tls-dev                  # sertifikat swatanda (atau pasang sertifikat resmi di deploy/tls/)
make up                       # db -> migrate (Alembic) -> api, worker, web (https://host/)
docker compose run --rm api python -m sinergi_api.cli buat-pengguna --username admin.sinergi --nama "Admin" --peran admin
```

Tanpa Docker (pengembangan; butuh PostgreSQL 16, Python 3.12, Node 22):

```bash
python -m venv .venv && . .venv/bin/activate
make install
make db-reset                 # DB `sinergi` dari baseline Alembic (db/schema.sql + db/seed_ref.sql)
make admin U=admin.sinergi N="Admin SINERGI"
make dev-api                  # http://localhost:8000
make dev-web                  # http://localhost:5173 (proksi /api)
```

Untuk pengembangan lewat `http://localhost` tanpa TLS, setel `SINERGI_COOKIE_SECURE=false` di `.env`.

Uji: `make test` (oracle `engine_ref`, `db/test_schema.sql` 10 OK pada DB hasil Alembic, pytest unit/API/RLS/sinkron skema, Vitest) dan `make lint`.
