# Prompt Agent SINERGI — Sistem Neraca Ekonomi Regional Terintegrasi — versi 2 (untuk Claude Code)

Versi ini menggantikan `PROMPT_AGENT_SIKALTARA_LK.md` versi 1. Nama sistem kini **SINERGI** (sebelumnya SIKALTARA LK). Perubahannya:

- rumus mengikuti LK TD2025 resmi (REV/EKS/DEF + jangkar);
- dua tahun dasar (TD2010/KBLI 2020, TD2025/KBLI 2025) dengan M, N, R, S, T, U, (V) terpisah;
- seri data 2019+;
- komoditas dinamis per triwulan;
- tabel pokok lengkap sampai subkategori;
- adjustment tiga tahap;
- LK Biaya Antara mengisi RKA tahun dasar.

**Cara pakai**
1. Salin folder `sinergi/` ke repo baru bernama `sinergi`, lalu jalankan `git init`.
2. Buka Claude Code di folder itu. `CLAUDE.md` terbaca otomatis.
3. Tempel **PROMPT INDUK** sekali.
4. Tempel prompt fase satu per satu (F0 → F7). Mulai fase berikutnya hanya bila kriteria selesai fase sebelumnya terpenuhi.

---

## PROMPT INDUK

Anda adalah *senior full-stack engineer* yang membangun **SINERGI (Sistem Neraca Ekonomi Regional Terintegrasi)**: sistem web pengganti LK Excel untuk menghitung PDRB triwulanan menurut lapangan usaha BPS Provinsi Kalimantan Utara (provinsi 6500 dan kab/kota 6501–6504, 6571). Pengguna mengisi atau mengunggah data dasar, memilih metode, lalu sistem menghitung otomatis output, NTB ADHB/ADHK, rekonsiliasi, kompilasi, simulasi, tabel pokok lengkap, laju, dan dashboard pimpinan.

Sumber kebenaran ada di repo ini. Baca semuanya sebelum menulis kode:
- `CLAUDE.md` (aturan wajib)
- `docs/01_RANCANGAN_SISTEM.md` (ruang lingkup, peran, alur putaran, layar, fase)
- `docs/02_RUMUS_ENGINE.md` (rumus wajib) dan `engine_ref/lk_engine.py` (oracle) beserta `engine_ref/test_engine.py`
- `docs/03_ARSITEKTUR_TEKNIS.md` (stack, struktur repo, API, keamanan, pengujian)
- `docs/04_REBASING_TD2010_TD2025.md` (dua tahun dasar, backcast 2019+, konkordansi, cut-over)
- `docs/05_TEMPLAT_DAN_IMPOR.md` dan `tools/baca_templat.py` (format templat dan aturan impor); contoh templat KOSONG di `templates/`
- `db/schema.sql`, `db/seed_ref.sql`, `db/test_schema.sql` (sudah diuji di PostgreSQL 16; seluruh uji lulus)
- `docs/00_TEMUAN_PROSES_BISNIS.md` (temuan K/T/S/E). Setiap temuan yang berlabel "Di sistem" wajib diwujudkan sebagai validasi atau fitur.

Prinsip kerja:
1. Ikuti rumus persis. Kasus yang tidak tercakup: berhenti, jelaskan, dan tanyakan. Jangan menebak.
2. Bekerja per fase. Di akhir setiap fase, laporkan apa yang dibuat, hasil `make test`, dan apa yang belum.
3. Utamakan UI sederhana dan ramah operator: grid mirip Excel (bisa tempel dari Excel), sedikit teks, pesan galat jelas dalam bahasa Indonesia, dan tindakan penting satu klik.
4. Keamanan sejak awal: RLS, audit append-only, TOTP, ekspor bertanda air, dan tanpa data rahasia di repo.
5. Konfigurasi lewat master/seed, bukan *hardcode*: pohon lapus dua tahun dasar, kelompok publikasi, konkordansi, metode, seri, validasi, dan izin.

Hal yang harus terlihat di produk:
- **Komoditas dinamis.** Operator dapat menambah komoditas/rincian (+ Komoditas) di lapus yang ditugaskan, menetapkan berlaku mulai/sampai triwulan, menonaktifkan, atau menyambung ke item penerus. Data dasar memengaruhi NTB lapus daun, lalu subkategori, lalu kategori. Format tabel pokok **tidak berubah**.
- **Tabel pokok lengkap seperti Excel.** Semua baris pohon ditampilkan: kategori (tebal), subkategori dan sub-subkategori (menjorok), kelompok publikasi (dapat ditampilkan atau disembunyikan), NTB, TOP, SOP, TOP.SOP, PDRB, dan PDRB tanpa migas. Tabnya: ADHB, ADHK, distribusi, q-to-q, y-on-y, c-to-c, implisit, laju implisit, SoG, dan output. Baris dapat dilipat per kategori; ekspor xlsx tersedia dalam format sistem dan format LK 02 BPS (T+U+V = TUV).
- **Dua tahun dasar.** Pemilih TD2010/TD2025 ada di header. Laporan jembatan TD2010↔TD2025 tersedia. Riwayat rilis TD2010 dapat diimpor.

---

## F0 — Fondasi

1. Buat struktur repo sesuai `docs/03` §2, beserta Docker Compose (db, api, worker, web), `Makefile`, `.env.example`, dan `.gitignore`. `.gitignore` wajib menolak `*TERISI*.xlsx`, `*.xlsm`, `golden/`, dan `.env`.
2. Jadikan `db/schema.sql` + `db/seed_ref.sql` baseline Alembic. `make db-reset` membuat DB baru, lalu `make test` menjalankan `db/test_schema.sql` (10 uji harus OK).
3. Auth: login sandi Argon2id + TOTP wajib, refresh berotasi, kunci akun setelah 5 gagal, CSRF, dan cookie aman. RBAC dari `sec.*`. Middleware menyetel `SET LOCAL app.user_id/app.ip/app.alasan`.
4. Pemetaan galat: `P0423` → 423, `42501` → 403. Audit login/logout/ekspor ke `audit.log`.
5. Frontend: login, layout dengan sidebar sesuai izin, dan pemilih tahun dasar.
6. Branding SINERGI sesuai `CLAUDE.md` bagian "Nama dan branding":
   - halaman login menampilkan "SINERGI" + "Sistem Neraca Ekonomi Regional Terintegrasi" + "BPS Provinsi Kalimantan Utara";
   - judul tab browser "SINERGI", favicon dan logo teks sederhana (placeholder SVG yang mudah diganti);
   - pengenal teknis `sinergi` untuk repo, proyek Compose, DB, paket, prefiks env `SINERGI_`, dan cookie.

Selesai bila: `make test` hijau; login + TOTP berfungsi; operator tanpa penugasan ditolak menulis (uji RLS).

## F1 — Master data

1. CRUD tahun dasar dan pohon lapus (drag urutan, induk, jenis, migas, `kode_lk_bps`), beserta kelompok publikasi dan konkordansi (bobot).
2. CRUD katalog komoditas (sinonim, satuan), satuan, sumber data, wilayah, pengguna, peran-izin, dan penugasan (tahun dasar × wilayah × lapus).
3. Hapus = nonaktifkan bila sudah dipakai data. Semua perubahan diaudit.

Selesai bila: admin dapat menambah subkategori atau kelompok tanpa mengubah kode, dan tabel pokok langsung mengikuti urutan baru.

## F2 — Mesin hitung

1. `apps/api/engine` sebagai modul murni, sesuai `docs/02`:
   - REV, EKS (IP/IB, rantai maju/mundur), DEF (NTB input atau RKA);
   - jangkar `H_TD`/`IH_TD`/`RKA_TD` dan tahun baseline per tahun dasar;
   - rumus turunan baku (`TPK_X_KAMAR`, `JANGKAR_X_IH_100`, `KAPITA_X_PENDUDUK_X_3`, `MARGIN_X_OUTPUT`) dan tautan (`SERI_REFERENSI`, `HASIL_LAPUS`);
   - adjustment METODE/REKON/SIMULASI;
   - agregasi pohon, kelompok, NTB/TOP/SOP/PDRB, PDRB tanpa migas;
   - tabel turunan (SoG dibagi PDRB ADHK).
2. Graf dependensi antarlapus dari tautan, dengan deteksi siklus. Worker antrean hitung menulis `lk.hasil_*` beserta `hash_input` dan `versi_mesin`.
3. Uji:
   - port `engine_ref/test_engine.py`, lalu tambah kasus kecil untuk setiap aturan (min. 40 kasus);
   - **golden test** dibandingkan dengan `engine_ref` (toleransi 1e-9);
   - target golden: 72 lapus Put 0 identik (dataset golden disiapkan pengguna di folder `golden/` pada mesin internal; jangan di-commit).

Selesai bila: semua uji hijau dan golden identik.

## F3 — Data dasar, templat, seri referensi

1. Layar Data Dasar: kategori → tab subkategori → grid AG Grid. Baris = item × seri; kolom = triwulan 2019–berjalan, dengan tahun lama dapat dilipat.
   - Sel kuning dapat diedit; tempel dari Excel didukung.
   - Ikon validasi per sel/baris.
   - Kontribusi item ke output lapus ditampilkan.
2. **+ Komoditas** (katalog, metode, satuan, jenis indeks, berlaku mulai/sampai, alasan), Nonaktifkan, dan Sambungkan ke item penerus.
3. Impor/ekspor templat persis `docs/05` (pratinjau selisih → terapkan), CSV panjang, dan seri referensi. Uji dengan `templates/*_KOSONG.xlsx`. Pada mesin internal, uji juga dengan berkas TERISI: TD2025 harus identik dengan LK untuk 72 lapus.
4. Validasi V01–V17 (`ref.validasi`) dengan tingkat info/peringatan/blokir.

Selesai bila: round-trip ekspor → impor → hitung sama; templat terisi masuk tanpa galat format.

## F4 — Putaran, biaya antara, adjustment, persetujuan, simulasi

1. Putaran: buka (salin dari putaran sumber), cakupan periode, cut-off, kunci/buka kunci (beralasan), dan bandingkan dua putaran.
2. LK Biaya Antara (`lk.struktur_biaya`): input output dan rincian BA dari SE2026/SUT, rasio otomatis, lalu Terapkan ke `RKA_TD` item (urutan cari: item → lapus → induk).
3. Adjustment tiga tahap dengan dialog nilai / target NTB / target laju y-on-y / target implisit, alasan wajib, dan status draf/diajukan/disetujui/ditolak.
4. Status lapus: belum → draf → diajukan → disetujui/dikembalikan; NIHIL tersedia. Pengajuan diblokir bila validasi blokir belum lolos.
5. Kompilasi dan Simulasi (izin `simulasi.edit`), lalu tahap FINAL.

Selesai bila skenario e2e lulus: buka Put → isi → adjustment → ajukan → setujui → simulasi → kunci (423 untuk semua tulis) → putaran baru tersalin.

## F5 — Tabel pokok, dashboard, ekspor

1. Tabel pokok dari `lk.v_tabel_pokok` sesuai bagian "Tabel pokok lengkap" di prompt induk. Kelompok publikasi dapat ditampilkan atau disembunyikan. Baris tanpa hasil tetap tampil (kosong).
2. Dashboard: KPI (PDRB ADHB/ADHK, laju q/y/c), grafik PDRB ADHK per triwulan, laju per kategori, SoG, perbandingan putaran dan rilis, serta status persetujuan.
3. Ekspor xlsx bertanda air (format sistem dan format LK 02 BPS dengan TUV), tercatat di `audit.ekspor`.

Selesai bila: angka dashboard sama dengan tabel pokok, dan ekspor LK 02 cocok dengan Excel kompilasi.

## F6 — Rebasing dan riwayat

1. Impor LK 01 TD2025 (.xlsm) per berkas operator memakai `tools/lk_xlsm_reader.py`:
   - baris contoh templat ditolak (K1);
   - kode TUV.1/TUV.2/TUV.3 dipetakan ke T.1/T.2/U.
2. Impor rilis TD2010 ke `lk.tabel_pokok_rilis`.
3. Fitur "Salin item ke TD2025" memakai konkordansi.
4. Laporan jembatan TD2010↔TD2025 per kategori (level, laju, implisit, selisih).

Selesai bila: Put 0 terimpor dan hasilnya identik dengan LK.

## F7 — Pengerasan dan serah terima

Uji keamanan (OWASP ASVS L2 ringkas), uji beban, cadangan terenkripsi dan uji pulih, panduan pengguna per peran (bahasa sederhana), dan materi pelatihan.

Selesai bila checklist rilis lengkap.
