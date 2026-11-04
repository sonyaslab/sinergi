# CLAUDE.md — SINERGI (Sistem Neraca Ekonomi Regional Terintegrasi)

Sistem web pengganti LK Excel PDRB triwulanan lapangan usaha BPS Provinsi Kalimantan Utara (6500, 6501–6504, 6571).
Baca berurutan sebelum mengubah kode: `docs/01_RANCANGAN_SISTEM.md` → `docs/02_RUMUS_ENGINE.md` → `docs/03_ARSITEKTUR_TEKNIS.md` →
`docs/04_REBASING_TD2010_TD2025.md` → `docs/05_TEMPLAT_DAN_IMPOR.md` → `docs/00_TEMUAN_PROSES_BISNIS.md`.

## Nama dan branding

- Nama produk di UI, judul halaman, email notifikasi, ekspor, dan dokumen: **SINERGI**.
- Kepanjangan (di halaman login, footer, dan sampul ekspor): **Sistem Neraca Ekonomi Regional Terintegrasi**.
- Baris institusi: BPS Provinsi Kalimantan Utara.
- Pengenal teknis memakai `sinergi`: nama repo, proyek Docker Compose, nama basis data (`sinergi`, uji: `sinergi_test`), paket Python `sinergi_api`, paket web `sinergi-web`, prefiks variabel lingkungan `SINERGI_`, dan nama cookie `sinergi_*`.
- Jangan memakai nama lama "SIKALTARA LK" di kode atau UI.

## Aturan tak boleh dilanggar

1. **Rumus = `docs/02_RUMUS_ENGINE.md` + `engine_ref/lk_engine.py`.** Jangan mengarang atau "menyederhanakan" rumus. Bila ada kasus di luar spesifikasi, berhenti dan tanyakan.
2. **Golden test wajib hijau**: `apps/api/engine` harus identik (relatif ≤ 1e-9) dengan `engine_ref` untuk semua kasus uji. Perilaku Excel: kosong = 0 dalam hitung, bagi 0 = 0, AVERAGE abaikan kosong.
3. **Kosong ≠ nol** untuk validasi dan tampilan (`status_sel`), walau 0 di mesin.
4. **Format tabel pokok tetap**: baris = pohon `ref.lapus` (kategori → subkategori → sub-subkategori, kelompok publikasi, NTB/TOP/SOP/PDRB) urut `urutan`. Item/komoditas tidak pernah menambah baris tabel pokok.
5. **Dua tahun dasar**: TD2010 = KBLI 2020 (A–U; M, N, R, S, T, U terpisah; kelompok "M,N", "R,S,T,U"); TD2025 = KBLI 2025 (A–V; T, U, V terpisah; kelompok "TUV" untuk ekspor LK 02). Semua kueri disaring `tahun_dasar_id`.
6. **Konfigurasi, bukan kode**: lapus, kelompok, konkordansi, metode bawaan, satuan, katalog, izin peran diatur dari master/seed, bukan *hardcode*.
7. **Keamanan**: aplikasi konek sebagai `app_rw` (RLS aktif); setiap transaksi tulis `SET LOCAL app.user_id/app.ip/app.alasan`; SQLSTATE `P0423` → HTTP 423, `42501` → 403. Jangan pernah menonaktifkan RLS, trigger audit, atau trigger kunci.
8. **Data rahasia**: jangan commit `*TERISI*.xlsx`, `*.xlsm`, `golden/`, `.env`, dump DB. Jangan menulis angka PDRB nyata ke log, fixture publik, atau pesan galat. Data mikro perusahaan (nama, NIB, KIP) ditolak di impor.
9. Bahasa UI dan pesan: Indonesia, singkat, ramah pengguna. Kode dan identifier: Inggris/Indonesia konsisten dengan skema (nama tabel/kolom skema dipertahankan).

## Perintah

```
make up            # docker compose up (db, api, worker, web)
make db-reset      # buat ulang DB: db/schema.sql + db/seed_ref.sql (via Alembic baseline)
make test          # pytest (unit, golden, api, rls) + psql -f db/test_schema.sql + vitest
make golden        # golden test vs engine_ref (butuh golden/ di mesin internal)
make lint          # ruff, mypy, eslint
```

## Peta kode

- `db/` skema + seed + uji skema (sumber migrasi awal; perubahan berikutnya lewat Alembic, sinkronkan `db/schema.sql`).
- `engine_ref/` oracle (jangan diubah tanpa memperbarui `docs/02` dan uji). `tools/` pembaca LK 01 xlsm, pembaca templat, validasi.
- `apps/api/engine/` mesin produksi (modul murni). `apps/api/impor/` templat/CSV/LK01/rilis. `apps/web/` React.

## Definisi selesai (setiap PR)

Uji baru untuk perilaku baru; `make test` hijau; tidak ada penurunan cakupan mesin hitung; dokumen di `docs/` diperbarui bila perilaku berubah; tidak ada rahasia di diff.
