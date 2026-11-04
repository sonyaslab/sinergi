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
