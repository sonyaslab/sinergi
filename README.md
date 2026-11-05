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
   Uji dianggap lulus bila muncul 16 baris berawalan "OK".
3. Uji mesin rujukan: `python -m pytest engine_ref`.
4. Buka Claude Code di folder repo. Tempel PROMPT INDUK, lalu jalankan fase F0 sampai F7 berurutan.

Templat TERISI dan berkas LK (.xlsm) bersifat rahasia dan tidak boleh di-commit.

## Menjalankan (status: F4 Putaran, biaya antara, adjustment, persetujuan, simulasi)

Dengan Docker (server internal):

```bash
cp .env.example .env          # lalu ganti semua rahasia
make tls-dev                  # sertifikat swatanda (atau pasang sertifikat resmi di deploy/tls/)
make up                       # db -> migrate (Alembic) -> api, worker, web (https://host/)
docker compose run --rm migrate python -m sinergi_api.cli buat-pengguna --username admin.sinergi --nama "Admin" --peran admin
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

Uji: `make test` (oracle `engine_ref`, `db/test_schema.sql` 16 OK pada DB hasil Alembic, pytest unit/API/RLS/sinkron skema/impor-ekspor
templat, Vitest) dan `make lint`.

Layar F3: menu **Data Dasar** (pilih tahun dasar di header, putaran, wilayah) berisi tab Isian data (grid AG Grid, tempel dari Excel,
+ Komoditas, nonaktif/sambungkan, tautan seri, ikon validasi, kontribusi item), Seri referensi, Impor & ekspor (templat docs/05,
CSV panjang; pratinjau selisih → terapkan), dan Validasi (V01–V17).

Layar F4: **Putaran & Adjustment** (buka putaran + salin dari putaran sumber, cakupan, cut-off, kunci/buka kunci beralasan,
status lapus belum → draf → diajukan → disetujui/dikembalikan, NIHIL, DIKECUALIKAN, daftar dan putusan adjustment,
bandingkan dua putaran), **LK Hitung NTB** (PR → PRE → POST → BENC → FINAL per metode/item, sakelar pratinjau draf, ajukan),
**Biaya Antara** (rasio KA SE2026/SUT, setujui, terapkan ke RKA_TD), **Kompilasi & Simulasi** (lapus × triwulan, simulasi
target laju/implisit, setujui simulasi), dan **Beranda** (putaran aktif, heatmap status lapus × wilayah, tugas saya).
Skenario ujung-ke-ujung: `apps/api/tests/e2e/test_alur_putaran.py`.

## Golden test (mesin internal)

Data LK Put 0 bersifat rahasia dan hanya ada di mesin internal (folder `golden/` di akar repo, tidak di-commit):

```
golden/manifest.json                        # wilayah, periode, peta lapus -> berkas LK 01 (rekap LK 02), tersimpan_usang, harap_identik
golden/lk01/*.xlsm                          # LK 01 TD2025 Put 0 per berkas operator
golden/Templat_Data_Dasar_TD2025_TERISI.xlsx
```

Contoh isi `manifest.json` ada di `apps/api/tests/golden/periksa.py` (`MANIFEST_CONTOH`). Jalankan `make golden`
(atau `SINERGI_GOLDEN=/jalur/golden make golden`; butuh PostgreSQL seperti `make test`). Laporan hanya memuat kode lapus dan
selisih relatif. Sejak F3 templat TERISI juga diuji lewat importer sungguhan (pratinjau tanpa galat format → terapkan → worker →
`lk.hasil_lapus`) dan harus identik dengan LK untuk 72 lapus (`test_templat_terisi_lewat_importer_identik_lk01`).
