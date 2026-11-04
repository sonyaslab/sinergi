# Arsitektur Teknis SINERGI (Sistem Neraca Ekonomi Regional Terintegrasi)

## 1. Tumpukan teknologi

| Lapisan | Pilihan | Alasan |
|---|---|---|
| Basis data | PostgreSQL 16 (skema `ref`, `lk`, `sec`, `audit`, `ext`) | RLS, NUMERIC presisi penuh, trigger audit |
| API | Python 3.12, FastAPI, SQLAlchemy 2 (Core untuk kueri berat), Pydantic v2, Alembic | Mesin hitung sama bahasa dengan `engine_ref` (golden test mudah) |
| Mesin hitung | modul murni `apps/api/engine` (tanpa I/O), NumPy opsional | dapat diuji unit; deterministik |
| Antrean hitung | tabel `lk.antrean_hitung` + worker (`SELECT … FOR UPDATE SKIP LOCKED`) | tanpa Redis; cukup untuk 6 wilayah × ~140 lapus |
| Frontend | React 18 + TypeScript + Vite, TanStack Query, AG Grid Community (grid isian), ECharts (grafik), Tailwind | grid mirip Excel, tempel dari Excel |
| Berkas | openpyxl (impor/ekspor xlsx), tanpa makro | — |
| Deploy | Docker Compose: `db`, `api`, `worker`, `web` (Nginx + TLS) di server internal | sederhana, bisa VM tunggal |
| Mutu | pytest, Vitest, Playwright (e2e), Ruff, mypy, ESLint; GitHub Actions/GitLab CI | — |

## 2. Struktur repo

```
sinergi/
├─ CLAUDE.md                 # aturan kerja untuk Claude Code (baca dulu)
├─ docs/                     # 00 temuan, 01 rancangan, 02 rumus, 03 arsitektur, 04 rebasing, 05 templat
├─ db/                       # schema.sql, seed_ref.sql, test_schema.sql  (sumber migrasi Alembic awal)
├─ engine_ref/               # mesin rujukan (oracle) + test_engine.py
├─ tools/                    # baca_templat.py, lk_xlsm_reader.py, validasi_engine_vs_lk.py
├─ templates/                # templat data dasar KOSONG TD2010 & TD2025 (jangan commit yang TERISI)
├─ prompts/                  # prompt induk + prompt per fase
├─ apps/
│  ├─ api/
│  │  ├─ app/ (main.py, deps.py, config.py)
│  │  ├─ auth/ (login, totp, sesi, rbac)
│  │  ├─ master/ (tahun_dasar, lapus, katalog, wilayah, pengguna, penugasan)
│  │  ├─ data_dasar/ (item, nilai, seri_referensi, validasi)
│  │  ├─ impor/ (templat xlsx, csv panjang, lk01 xlsm, rilis)
│  │  ├─ engine/ (rev.py, eks.py, deff.py, turunan.py, penyesuaian.py, rekon.py, agregasi.py, turunan_tabel.py)
│  │  ├─ putaran/ (putaran, status, persetujuan, simulasi, bandingkan)
│  │  ├─ laporan/ (tabel_pokok, dashboard, ekspor)
│  │  ├─ worker/ (antrean hitung)
│  │  └─ tests/ (unit, golden, api, rls)
│  └─ web/ (src/pages, src/components/grid, src/components/charts)
├─ docker-compose.yml, Makefile, .env.example
└─ golden/                   # TIDAK di-commit: angka LK Put 0 untuk golden test (rahasia, hanya mesin internal)
```

Penamaan teknis:
- repo dan proyek Docker Compose: `sinergi`;
- layanan: `sinergi-db`, `sinergi-api`, `sinergi-worker`, `sinergi-web`;
- basis data: `sinergi`;
- paket: `sinergi_api` dan `sinergi-web`;
- variabel lingkungan: `SINERGI_*`.

## 3. API (ringkas)

| Kelompok | Endpoint utama |
|---|---|
| Auth | `POST /auth/login`, `POST /auth/totp`, `POST /auth/refresh`, `POST /auth/logout` |
| Master | `GET/POST/PATCH /tahun-dasar`, `/lapus` (pohon), `/lapus/{id}/kelompok`, `/konkordansi`, `/katalog`, `/wilayah`, `/pengguna`, `/penugasan` |
| Putaran | `GET/POST /putaran`, `POST /putaran/{id}/kunci`, `/buka-kunci`, `GET /putaran/{a}/banding/{b}` |
| Data dasar | `GET /putaran/{p}/lapus/{l}/item?wilayah=`, `POST /item` (+ Komoditas), `PATCH /item/{id}` (berlaku/nonaktif/sambung), `PUT /nilai` (batch sel), `GET/PUT /seri-referensi` |
| Impor/ekspor | `POST /impor/templat` → pratinjau; `POST /impor/{id}/terapkan`; `GET /ekspor/templat?td=&wilayah=&kosong=`; `POST /impor/lk01`; `POST /impor/rilis` |
| Hitung | `POST /hitung` (masuk antrean), `GET /hasil/lapus/{l}` (PR/PRE/POST/BENC/FINAL + kontribusi item) |
| Biaya antara | `GET/PUT /struktur-biaya`, `POST /struktur-biaya/terapkan` |
| Penyesuaian | `GET/POST /penyesuaian`, `POST /penyesuaian/{id}/putus` |
| Alur | `POST /status/{lapus}/ajukan`, `/setujui`, `/kembalikan`, `/nihil` |
| Laporan | `GET /tabel-pokok?putaran=&wilayah=&tabel=adhb|adhk|distribusi|qtq|yoy|ctc|implisit|sog&kelompok=tampil|sembunyi`, `GET /dashboard`, `GET /ekspor/tabel-pokok.xlsx`, `GET /ekspor/lk02.xlsx` |

Semua endpoint tulis:
- memeriksa izin;
- menyetel `SET LOCAL app.user_id`, `app.ip`, dan `app.alasan`;
- memetakan SQLSTATE `P0423` ke HTTP 423 dan `42501` (RLS) ke HTTP 403.

## 4. Hitung otomatis

1. Simpan data/item/adjustment akan memasukkan job ke `lk.antrean_hitung` (putaran, wilayah, lapus).
2. Worker menyusun graf dependensi: tautan HASIL_LAPUS/MARGIN, induk, kelompok, NTB/PDRB. Lapus terdampak dihitung ulang bersama turunannya.
3. Hasil ditulis dalam satu transaksi beserta `hash_input` dan `versi_mesin`. Klien mendapat notifikasi lewat polling ringan atau SSE.
4. Target: satu lapus < 1 detik; satu wilayah penuh (2019–2026) < 30 detik.

## 5. Keamanan

- Nginx dengan TLS 1.2+, HSTS, CSP ketat, dan tanpa akses publik (IP allowlist/VPN).
- Login dibatasi 5 percobaan sebelum kunci 15 menit. TOTP wajib untuk semua peran.
- Token akses 15 menit di cookie `HttpOnly; Secure; SameSite=Strict`; refresh token berotasi (hash di `sec.sesi`); CSRF *double-submit*.
- Aplikasi terhubung sebagai `app_rw` (bukan pemilik tabel) sehingga RLS berlaku. Laporan memakai `app_ro`. Migrasi memakai `app_owner`.
- Audit: semua perubahan data dan master tercatat append-only dengan rantai hash. Sistem memeriksa rantai setiap malam.
- Rahasia di `.env` (tidak di-commit). Cadangan `pg_dump` terenkripsi (age/GPG) harian, disimpan 30 hari, diuji pulih bulanan.
- Templat TERISI dan berkas LK tidak boleh masuk repo. `.gitignore` menolak `*TERISI*.xlsx`, `*.xlsm`, `golden/`.

## 6. Pengujian

| Jenis | Isi |
|---|---|
| Uji skema | `db/test_schema.sql`: RLS, batas item, alasan wajib, kunci 423, audit, tabel pokok lengkap, rumus baku |
| Uji unit mesin | kasus kecil per metode, jangkar, rumus turunan, adjustment, rekon, kelompok, turunan tabel (contoh di `engine_ref/test_engine.py`) |
| Golden test | `engine` vs `engine_ref` pada data Put 0 (dari `tools/lk_xlsm_reader.py`); toleransi relatif 1e-9; 72 lapus |
| Round-trip templat | ekspor → impor → hitung = sama; templat kosong dan terisi |
| API & e2e | alur putaran lengkap; operator lain ditolak; putaran terkunci 423 |
| Kinerja | 6 wilayah × 140 lapus × 32 triwulan |
| Sinkron skema | `tests/rls/test_skema_sinkron.py`: `db/schema.sql` + `db/seed_ref.sql` identik dengan hasil migrasi Alembic (pg_dump) |

## 7. Migrasi basis data (Alembic)

- Paket Python `sinergi_api` dipetakan ke folder `apps/api/` (jalur `apps/api/engine/` = modul `sinergi_api.engine`).
- Migrasi `0001` menjalankan salinan **beku** skema dan seed v4 (`apps/api/migrations/baseline/*.sql`). Berkas beku tidak boleh diubah.
- Setiap perubahan skema berikutnya = migrasi baru **dan** sinkronisasi `db/schema.sql` (serta `db/seed_ref.sql` bila seed berubah). Uji sinkron skema menggagalkan CI bila keduanya berbeda.
- Migrasi `0002`: kolom `sec.pengguna.totp_langkah_terakhir` (kode TOTP tidak boleh dipakai ulang, ASVS 2.8.4).
- Peran login: `app_owner` (migrasi, pemilik tabel), `app_rw` (API/worker, RLS berlaku), `app_ro` (laporan). Hanya `app_rw`/`app_ro` yang diberi `CONNECT` selain pemilik. Compose menjalankan migrasi lewat layanan sekali jalan `migrate`, sehingga kredensial pemilik tidak ada di kontainer `api`/`worker`.

## 8. Autentikasi (F0)

| Langkah | Endpoint | Catatan |
|---|---|---|
| Token CSRF | `GET /api/auth/csrf` | cookie `sinergi_csrf` (bertanda tangan HMAC, dibaca JS) + header `X-CSRF-Token` wajib untuk semua POST/PUT/PATCH/DELETE |
| Sandi | `POST /api/auth/login` | Argon2id; pesan galat sama untuk pengguna tidak ada/sandi salah; 5 gagal → kunci 15 menit (HTTP 429) |
| TOTP | `POST /api/auth/totp` | wajib semua peran; pendaftaran pertama menampilkan QR (dibuat di server); kode tidak boleh dipakai ulang |
| Sesi | cookie `sinergi_akses` (15 menit, path `/api`), `sinergi_refresh` (berotasi, path `/api/auth`) | `HttpOnly; Secure; SameSite=Strict`; refresh lama yang dipakai ulang mencabut sesi; idle 60 menit |
| Profil | `GET /api/auth/saya` | peran, izin, penugasan aktif |
| Lainnya | `POST /api/auth/refresh`, `/logout`, `/ganti-sandi` | sandi awal wajib diganti (min. 12 karakter) sebelum endpoint lain dapat dipakai |

Alasan perubahan dikirim lewat header `X-Alasan` (UTF-8, *percent-encoded*) dan disimpan ke `app.alasan` untuk trigger audit.
