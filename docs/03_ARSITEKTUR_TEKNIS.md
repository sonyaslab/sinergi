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
| Master (F1) | `GET/POST/PATCH/DELETE /tahun-dasar` (opsi `salin_pohon_dari`); `GET/POST /tahun-dasar/{td}/lapus`, `PATCH/DELETE /lapus/{id}`, `PUT /tahun-dasar/{td}/lapus/urutan` (urutan saudara), `PUT /lapus/{id}/anggota` (kelompok); `/konkordansi`, `/katalog?q=`, `/satuan`, `/sumber-data`, `/wilayah` |
| Akses (F1) | `/pengguna` (+ `/reset-sandi`, `/reset-totp`, `/buka-kunci`), `/peran`, `/izin`, `/penugasan` (kategori diperluas ke lapus daun), `GET /audit`, `GET /audit/verifikasi` |
| Putaran | `GET /putaran?tahun_dasar_id=` (F3); `POST /putaran`, `POST /putaran/{id}/kunci`, `/buka-kunci`, `GET /putaran/{a}/banding/{b}` (F4) |
| Data dasar (F3) | `GET /data-dasar/grid?putaran_id=&wilayah=&lapus_id=` (item × seri, nilai, `tidak_tersedia`, nilai seri tertaut/rumus, jangkar, kontribusi item per triwulan, temuan validasi, status antrean); `PUT /data-dasar/nilai` (batch sel; kosong = hapus, `tidak_tersedia`); `PUT /data-dasar/parameter` (jangkar); `POST /data-dasar/item` (+ Komoditas); `PATCH /data-dasar/item/{id}` (nonaktif/berlaku/jenis indeks, alasan wajib); `POST /data-dasar/item/{id}/sambung`, `GET …/usulan-jangkar` (keputusan 14); `PUT /data-dasar/item/{id}/seri`, `PATCH …/seri/{seri}`, `PUT …/tautan`; `GET/POST /seri-referensi`, `PUT /seri-referensi/nilai` |
| Impor/ekspor (F3) | `POST /impor/templat?putaran_id=&nama=&kosongkan=&setujui_penyesuaian=` (badan = berkas xlsx/csv) → pratinjau; `POST /impor/{id}/terapkan` (berkas yang sama); `GET /ekspor/templat?putaran_id=&tahun_dasar_id=&wilayah=&kosong=`; `GET /ekspor/csv`; `GET /ekspor/seri-referensi`; `POST /impor/lk01`, `POST /impor/rilis` (F6) |
| Hitung & validasi (F3) | `POST /hitung` (masuk antrean), `GET /hitung/status`; `GET /validasi?putaran_id=&wilayah=&lapus_id=&tingkat=`, `POST /validasi/konfirmasi` (V05), `GET /validasi/kunci` (V13–V15), `GET/PATCH /validasi/aturan[/{kode}]` (admin); `GET /hasil/lapus/{l}` (F4, layar LK Hitung) |
| Biaya antara | `GET/PUT /struktur-biaya`, `POST /struktur-biaya/terapkan` |
| Penyesuaian | `GET/POST /penyesuaian`, `POST /penyesuaian/{id}/putus` |
| Alur | `POST /status/{lapus}/ajukan`, `/setujui`, `/kembalikan`, `/nihil` |
| Laporan | `GET /tabel-pokok?putaran=&wilayah=&tabel=adhb|adhk|distribusi|qtq|yoy|ctc|implisit|sog&kelompok=tampil|sembunyi`, `GET /dashboard`, `GET /ekspor/tabel-pokok.xlsx`, `GET /ekspor/lk02.xlsx` |

Semua endpoint tulis:
- memeriksa izin;
- menyetel `SET LOCAL app.user_id`, `app.ip`, dan `app.alasan`;
- memetakan SQLSTATE `P0423` ke HTTP 423 dan `42501` (RLS) ke HTTP 403.

## 4. Hitung otomatis

1. Simpan data/item/adjustment akan memasukkan job ke `lk.antrean_hitung` (putaran, wilayah, lapus) lewat
   `sinergi_api.worker.antrean.antrekan()`; job menunggu yang sama tidak digandakan (endpoint simpan: F3/F4).
2. Worker (`python -m sinergi_api.worker`, pengguna `sistem.worker`) mengambil job dengan
   `SELECT … FOR UPDATE SKIP LOCKED`, mengunci (putaran, wilayah) dengan advisory lock, lalu menghitung ulang
   **satu wilayah penuh**: muat → graf dependensi (tautan HASIL_LAPUS/MARGIN, induk, kelompok, NTB/PDRB) → mesin →
   tulis. Hitung penuh dipilih karena cepat dan menjamin semua baris agregat konsisten; job menunggu lain untuk
   (putaran, wilayah) yang sama ikut ditandai selesai ("digabung ke job N").
3. Hasil ditulis dalam satu transaksi (hapus lalu COPY `lk.hasil_item`, `lk.hasil_metode`, `lk.hasil_lapus`) beserta
   `hash_input` (SHA-256 masukan terselesaikan per lapus; agregat = gabungan sidik sumber) dan `versi_mesin`. Hanya
   periode putaran yang ditulis; hanya penyesuaian `disetujui` yang masuk (keputusan 8a). Putaran terkunci → job
   `gagal` "Putaran terkunci; hasil tidak diubah." (P0423); siklus tautan → `gagal` dengan kode lapus. Pesan tidak
   memuat angka. Job `proses` lebih dari 15 menit diambil ulang. `--sekali` menguras antrean lalu keluar.
4. Pratinjau penyesuaian draf/diajukan: `antrean.pratinjau()` menghitung tanpa menyimpan (layar LK Hitung, F4).
5. Target: satu lapus < 1 detik; satu wilayah penuh (2019–2026) < 30 detik. Terukur: 73 lapus, 274 item, 32 triwulan
   ≈ 0,03 detik hitung.

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
| Golden sintetis | `tests/golden/test_sintetis.py`: 60 wilayah acak (semua metode, jangkar TD2010/TD2025, tautan, rumus turunan, masa berlaku, penyesuaian, TOP/SOP, kelompok, migas) — mesin vs oracle `engine_ref/kompilasi.py`, relatif ≤ 1e-9, semua tahap dan item. Selalu jalan |
| Golden data rahasia | `tests/golden/test_golden.py` pada `golden/` (atau `SINERGI_GOLDEN`): LK 01 .xlsm + templat TD2025 TERISI + `manifest.json` (contoh di `tests/golden/periksa.py`). Mesin = `engine_ref` (1e-9) untuk semua lapus; = hasil simpan LK (1e-6) kecuali `tersimpan_usang` (B.3); templat = LK untuk 72 lapus. Alur ini diuji dengan data palsu di `test_golden_alur.py` |
| Worker | `tests/worker/test_worker.py`: DB → worker → `lk.hasil_*` identik dengan oracle; draf tidak tersimpan; hash berubah hanya bila masukan berubah; terkunci/siklus gagal rapi; job digabung |
| Templat & round-trip (F3) | `tests/impor/test_impor_templat.py`: templat KOSONG TD2010/TD2025 diimpor tanpa galat lalu diekspor sama persis per sel; templat sintetis terisi (semua sel kuning, jangkar, REF/RUMUS/MARGIN/"ikut item", penyesuaian) lewat importer → DB → worker = oracle atas pembaca rujukan (1e-9); ekspor → impor ke putaran sama = tanpa perubahan; ekspor → impor ke tahun dasar baru → hitung = sama (selisih 0) untuk semua tahap dan item. Golden: templat TERISI lewat importer = LK untuk 72 lapus (`test_golden.py`, data rahasia; alurnya diuji data palsu di `test_golden_alur.py`) |
| Validasi (F3) | `tests/unit/test_validasi.py` (aturan V01–V17, ambang/P95, konfirmasi, nonaktif) dan `tests/api/test_data_dasar.py` (grid, simpan sel, + Komoditas, nonaktif, sambung, tautan, seri referensi, hak tulis, 423, konfirmasi V05, V15) |
| API & e2e | alur putaran lengkap; operator lain ditolak; putaran terkunci 423 |
| Kinerja | 6 wilayah × 140 lapus × 32 triwulan |
| Sinkron skema | `tests/rls/test_skema_sinkron.py`: `db/schema.sql` + `db/seed_ref.sql` identik dengan hasil migrasi Alembic (pg_dump) |

## 7. Migrasi basis data (Alembic)

- Paket Python `sinergi_api` dipetakan ke folder `apps/api/` (jalur `apps/api/engine/` = modul `sinergi_api.engine`).
- Migrasi `0001` menjalankan salinan **beku** skema dan seed v4 (`apps/api/migrations/baseline/*.sql`). Berkas beku tidak boleh diubah.
- Setiap perubahan skema berikutnya = migrasi baru **dan** sinkronisasi `db/schema.sql` (serta `db/seed_ref.sql` bila seed berubah). Uji sinkron skema menggagalkan CI bila keduanya berbeda.
- Migrasi `0002`: kolom `sec.pengguna.totp_langkah_terakhir` (kode TOTP tidak boleh dipakai ulang, ASVS 2.8.4).
- Migrasi `0004` (F2): rumus `MARGIN_X_IMPOR`, parameter `R_MARGIN_TD` (tanpa wajib alasan, seperti `RKA_TD`), seri
  komponen DEF `KURS`.
- Migrasi `0005` (F3): `lk.seri_item` (metadata baris templat per seri), `lk.item.padanan_teks`, `lk.seri_referensi.jenis`
  `harga` + `lapus_pemilik_id` + fungsi `lk.boleh_tulis_seri_ref`, `lk.hasil_validasi` (`jenis_seri`, `tingkat`, `kunci`),
  `lk.konfirmasi_validasi`, parameter `ref.validasi` (V05/V06/V08/V11), RLS + audit untuk tabel baru dan `lk.tautan_seri`.
  Kebijakan RLS tulis `lk.*` dipecah per perintah (INSERT/UPDATE/DELETE): kebijakan `FOR ALL` juga berlaku saat SELECT
  sehingga fungsi izin dievaluasi per baris pada setiap baca (pemuat worker macet pada puluhan ribu nilai). Hak baca tidak
  berubah (kebijakan `baca_*`).
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

## 9. Master data (F1)

- **Urutan tabel pokok.** `ref.lapus.urutan` selalu hasil penelusuran *depth-first* pohon: anak tepat di bawah induknya, urutan antarsaudara diatur admin (seret atau ▲▼). Setiap tambah/pindah/hapus menyusun ulang `urutan` dan `level` seluruh pohon, sehingga `lk.v_tabel_pokok` langsung mengikuti tanpa mengubah kode.
- **Aturan pohon.** Kategori, kelompok, dan baris total (NTB, TOP, SOP, TOP.SOP, PDRB, PDRB.NM) tidak berinduk; induk harus kategori/subkategori aktif; kedalaman maksimal 4; lapus berisi item tidak dapat dijadikan induk; anggota kelompok tidak boleh induk dan turunannya sekaligus (hitung ganda). Lapus berdata (boleh punya item dan penugasan): daun, TOP, SOP.
- **Hapus = nonaktifkan bila dipakai data.** Penghapusan dicoba dalam *savepoint*; bila ditolak *foreign key* (atau dirujuk tautan/riwayat/antrean), baris dinonaktifkan. Tahun dasar dipakai → `arsip`. Pengguna tidak pernah dihapus (nonaktif + semua sesi dicabut). Penugasan diakhiri (`berlaku_sampai` = kemarin). Peran dipakai → nonaktif (tidak memberi izin).
- **Penjaga hak akses.** Minimal satu pengguna aktif tetap memegang `pengguna.kelola`; admin tidak dapat menonaktifkan akunnya sendiri. Akun sistem (`sistem.worker`) tidak dapat diubah dari UI.
- **Keamanan DB (migrasi 0003).** RLS tulis `ref.*` hanya dengan izin `master.kelola`; tulis `sec.peran`, `sec.peran_izin`, `sec.pengguna_peran`, `lk.penugasan` hanya dengan `pengguna.kelola`. Semua tabel master diaudit; `sec.pengguna` diaudit tanpa hash sandi/rahasia TOTP dan tanpa pembukuan login. CLI `buat-pengguna` (bootstrap admin pertama) memakai koneksi pemilik; di Docker jalankan lewat layanan `migrate`.

## 10. Mesin hitung (F2)

| Modul `apps/api/engine` | Isi | Oracle |
|---|---|---|
| `model.py` | masukan/hasil (urut = `ref.periode.urut`), `VERSI_MESIN`, galat | — |
| `rev.py`, `eks.py`, `deff.py` | metode per item, jangkar menurut `jangkar_dari_data`, TOP/SOP tanpa KA | `engine_ref/lk_engine.py` |
| `turunan.py` | masa berlaku, SERI_REFERENSI, HASIL_LAPUS (BENC), rumus baku termasuk margin arus barang | `engine_ref/turunan.py` |
| `penyesuaian.py`, `rekon.py` | METODE (PR → PRE), REKON (PRE → POST → BENC), SIMULASI (FINAL), bantuan target laju/implisit | `lk_engine.tahap_rekon`, `kompilasi.simulasi` |
| `graf.py`, `agregasi.py` | pohon, urutan topologis + deteksi siklus, agregasi kategori/kelompok/NTB/TOP.SOP/PDRB/PDRB.NM | `engine_ref/kompilasi.py` |
| `turunan_tabel.py` | distribusi, laju q/y/c, implisit dan lajunya, SoG (pembagi PDRB ADHK) | `kompilasi.py` (fungsi tabel) |
| `sidik.py`, `hitung.py` | sidik masukan; orkestrasi satu wilayah | — |

Worker: `apps/api/worker/muat.py` (DB → masukan), `tulis.py` (COPY ke `lk.hasil_*`), `antrean.py` (ambil, proses,
gabung, pratinjau, `antrekan`).

## 11. Data dasar, templat, validasi (F3)

| Modul | Isi |
|---|---|
| `apps/api/impor/templat.py` | pembaca templat (modul murni): sheet A..V + TOP_SOP, SERI_REFERENSI, PENYESUAIAN; pesan per sheet/baris/kolom tanpa angka; tolak data mikro |
| `impor/tautan.py` | tata bahasa kolom Tautan / Rumus ↔ `lk.tautan_seri` (docs/05 §2a) |
| `impor/csv_panjang.py`, `impor/konteks.py` | CSV panjang dan seri referensi; master untuk pembaca |
| `impor/terapkan.py` | rencana impor (selisih terhadap DB putaran, izin per lapus/wilayah, "ikut item lain" → seri referensi, IH 2010=100) dan penerapan satu transaksi + antrean hitung |
| `impor/ekspor.py`, `impor/router.py` | pembangkit templat (format = `templates/*_KOSONG.xlsx`, tanda air) dan endpoint impor/ekspor |
| `data_dasar/router.py` | grid, simpan sel, + Komoditas, ubah/nonaktif/sambung (usulan jangkar), seri dan tautan item, seri referensi, hitung, validasi |
| `data_dasar/validasi.py`, `validasi_db.py` | V01–V17 (modul murni) dan penulisannya ke `lk.hasil_validasi` oleh worker setiap hitung; V15 saat kunci |
| `apps/web/src/pages/DataDasar.tsx`, `pages/data-dasar/*`, `components/grid/GridDataDasar.tsx` | layar Data Dasar: kategori → tab subkategori → AG Grid Community (sel kuning, tempel dari Excel, ikon validasi, kontribusi), + Komoditas, panel item, impor/ekspor, seri referensi, validasi |

- **Berkas mentah tidak disimpan.** Pratinjau mencatat sha256, ringkasan, dan pesan (tanpa angka) di `audit.impor_berkas`;
  terapkan mengirim ulang berkas yang sama dan ditolak bila berbeda, kedaluwarsa (6 jam), sudah diterapkan, atau data sistem
  berubah sejak pratinjau.
- **Tempel dari Excel** (AG Grid Community tidak punya modul papan klip): peristiwa `paste` pada sel fokus, TSV diurai
  `lib/tempel.ts` (format angka Indonesia/Inggris; "-" = tidak tersedia; kosong = hapus); sel rumus/tautan/di luar cakupan
  dilewati dengan pesan.
- **Hitung otomatis**: setiap simpan memanggil `antrekan()`; layar memantau `GET /hitung/status` lalu menyegarkan hasil,
  kontribusi, dan ikon validasi.
