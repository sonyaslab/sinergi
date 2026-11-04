# Rancangan Sistem SINERGI (versi 4)

**SINERGI (Sistem Neraca Ekonomi Regional Terintegrasi)** adalah sistem web untuk menghitung PDRB triwulanan menurut lapangan usaha Provinsi Kalimantan Utara dan 5 kab/kota. Sistem ini menggantikan LK Excel yang terpisah per kategori: angka diinput atau diunggah sekali, lalu output, NTB, tabel pokok, laju, dan dashboard terhitung otomatis.

Dokumen terkait:
- `02_RUMUS_ENGINE.md` (rumus)
- `03_ARSITEKTUR_TEKNIS.md`
- `04_REBASING_TD2010_TD2025.md`
- `05_TEMPLAT_DAN_IMPOR.md`
- `00_TEMUAN_PROSES_BISNIS.md`

## 1. Ruang lingkup

| Termasuk | Tidak termasuk (tahap ini) |
|---|---|
| Dua tahun dasar sekaligus: TD2010 (KBLI 2020, produksi berjalan) dan TD2025 (KBLI 2025, rebasing) | PDRB pengeluaran |
| Seri 2019Q1 ke depan; riwayat rilis TD2010 sebagai pembanding | Data mikro perusahaan (tidak boleh masuk) |
| 6 wilayah (6500, 6501–6504, 6571), struktur LK sama | Integrasi otomatis ke sistem BPS RI (ekspor berkas saja) |
| Data dasar → LK hitung NTB → Biaya Antara → Adjustment → Kompilasi → Simulasi → Tabel Pokok → Dashboard | |
| Putaran (Put 0/backcast, reguler, revisi, rilis), penguncian, persetujuan berjenjang | |
| Peran admin, operator, supervisor (+ auditor), izin dapat ditambah | |

## 2. Klasifikasi lapangan usaha

- **TD2010 / KBLI 2020:** 21 kategori A–U, 59 lapus daun. M dan N terpisah; R, S, T, U terpisah.
  - Baris kelompok "M,N Jasa Perusahaan" dan "R,S,T,U Jasa Lainnya" tersedia untuk format publikasi 17 kategori.
- **TD2025 / KBLI 2025:** 22 kategori A–V, 76 lapus daun, mengikuti LK 02 Kompilasi TD2025, ditambah pemisahan:
  - T.1 = TUV.1, T.2 = TUV.2, U = TUV.3, V = badan internasional.
  - Baris kelompok "TUV" dipakai untuk ekspor format LK 02.
  - Ada baris NTB, TOP, SOP, TOP.SOP, PDRB.
- Pohon lapus, urutan baris tabel pokok, dan konkordansi TD2010 → TD2025 disimpan di master (`ref.lapus`, `ref.lapus_kelompok`, `ref.konkordansi_lapus`). Admin dapat mengubahnya tanpa mengubah kode.

## 3. Peran dan izin

| Peran | Tugas utama | Izin awal |
|---|---|---|
| Admin | Master (tahun dasar, lapus, katalog komoditas, metode, wilayah), pengguna, penugasan, buka/kunci putaran, impor rilis | semua |
| Operator | Isi/unggah data dasar lapus yang ditugaskan, tambah atau nonaktifkan komoditas, pilih metode, isi biaya antara, usul adjustment METODE/REKON, ajukan | `data_dasar.isi`, `data_dasar.impor`, `item.tambah`, `metode.pilih`, `biaya_antara.isi`, `penyesuaian.usul`, `lk.ajukan` |
| Supervisor (pimpinan) | Periksa, setujui/kembalikan per lapus, putus adjustment, simulasi akhir, kunci putaran, dashboard, ekspor | `lk.setujui`, `penyesuaian.putus`, `simulasi.edit`, `putaran.kunci`, `ekspor.tabel_pokok`, `dashboard.lihat`, `audit.lihat` |
| Auditor | Baca tabel pokok dan jejak audit | `tabel_pokok.lihat`, `dashboard.lihat`, `audit.lihat` |

Izin disimpan sebagai kode, sehingga peran baru cukup dibuat dari UI. Penugasan operator berlaku per (tahun dasar, wilayah, lapus) dan ditegakkan di basis data dengan RLS.

## 4. Alur kerja satu putaran

```
Admin buka putaran (tahun dasar, triwulan, jenis, cut-off; salin dari putaran sumber)
 → Operator: isi/unggah data dasar + tambah komoditas baru bila ada → hitung otomatis tiap simpan
 → Operator: cek validasi (V01–V17), isi Biaya Antara (TD2025: RKA tahun dasar), usul adjustment → AJUKAN per lapus
 → Supervisor: periksa (bandingkan dengan putaran lalu dan rilis), SETUJUI / KEMBALIKAN, putus adjustment
 → Supervisor/analis: Kompilasi + Simulasi (rekonsiliasi laju & implisit) → SETUJUI simulasi
 → Supervisor: KUNCI putaran (V13–V15 harus lolos) → tabel pokok final, ekspor (format sistem dan format LK 02 BPS)
 → Putaran berikutnya disalin dari putaran terkunci (data, item, adjustment)
```

- Jenis putaran: `BACKCAST` (Put 0 TD2025, 2019Q1–berjalan), `REGULER`, `REVISI` (boleh mengubah triwulan lalu sesuai cakupan), `RILIS`.
- Putaran terkunci menolak semua penulisan (HTTP 423). Buka kunci hanya oleh admin, wajib beralasan, dan tercatat di audit.
- Fitur bandingkan dua putaran menampilkan selisih data dasar, NTB, adjustment, dan laju per lapus.

## 5. Data dasar dan komoditas dinamis

- **Item** = satu komoditas/rincian di satu wilayah × lapus × metode. Operator dapat:
  - menambah item kapan saja dengan alasan (katalog komoditas baku membantu penamaan);
  - menetapkan berlaku mulai/sampai triwulan tertentu, sehingga komoditas boleh berbeda antartriwulan;
  - menonaktifkan item tanpa menghapus riwayat;
  - menyambung item lama ke item penerus (overlap) untuk rebasing.
- Data dasar berpengaruh langsung ke NTB lapus daun, lalu naik ke subkategori dan kategori. **Format tabel pokok tetap**, karena baris tabel pokok adalah lapus, bukan item.
- Dua cara input dengan validasi yang sama:
  1. Isi langsung di grid (seperti Excel, bisa tempel dari Excel).
  2. Unggah templat (`05_TEMPLAT_DAN_IMPOR.md`), dengan pratinjau selisih sebelum diterapkan.
- Seri referensi bersama (IHK, IHPB, indeks upah, implisit PMTB, indeks IBS/IMK agregat) diisi sekali lalu ditautkan ke banyak item.

## 6. Layar (mockup yang sudah disetujui + penyesuaian)

| No | Layar | Isi utama | Penyesuaian v4 |
|---|---|---|---|
| 1 | Login | sandi + TOTP | — |
| 2 | Beranda | putaran aktif, heatmap status per lapus × wilayah, tugas saya | pemilih tahun dasar (TD2010/TD2025) di header |
| 3 | Data Dasar | kategori → tab subkategori → grid item × seri; kolom triwulan 2019–sekarang (tahun lama dapat dilipat) | tombol **+ Komoditas** (nama dari katalog, metode, satuan, berlaku mulai/sampai, alasan); filter "aktif di triwulan ini"; tombol Nonaktifkan/Sambungkan |
| 4 | LK Hitung NTB | per lapus: item, metode, output, NTB ADHB/ADHK, laju; panel "data kurang" | ringkasan PR → PRE → POST → BENC; kontribusi per item |
| 5 | Biaya Antara | output, rincian BA, rasio KA tahun dasar per lapus/item; tombol Terapkan ke RKA tahun dasar | — |
| 6 | Putaran & Adjustment | ADJ1/ADJ2/SC per metode, ADJ3/ADJ4/CT rekonsiliasi; dialog 3 cara input + alasan | status draf/diajukan/disetujui |
| 7 | Kompilasi & Simulasi | tabel lapus × triwulan; input SIM ADHK (target laju) dan ADHB (target implisit) | — |
| 8 | **Tabel Pokok** | tab ADHB, ADHK, distribusi, q-to-q, y-on-y, c-to-c, implisit, laju implisit, SoG, output | **semua tingkat seperti Excel**: kategori (tebal), subkategori, sub-subkategori (menjorok), kelompok publikasi (dapat ditampilkan/disembunyikan), NTB, TOP, SOP, PDRB, PDRB tanpa migas; baris dapat dilipat per kategori; ekspor xlsx |
| 9 | Dashboard Pimpinan | KPI, grafik PDRB ADHK per triwulan, laju per kategori, sumber pertumbuhan, perbandingan putaran dan rilis | — |
| 10 | Master Data | tahun dasar, pohon lapus, kelompok, konkordansi, katalog komoditas, seri referensi | — |
| 11 | Pengguna & Hak Akses, Jejak Audit | — | — |

## 7. Keamanan (data rahasia sebelum rilis)

- Hanya jaringan internal/VPN; TLS; sandi Argon2id + TOTP wajib; sesi singkat dan token refresh berotasi.
- RBAC + RLS PostgreSQL (operator hanya menulis lapus yang ditugaskan). Peran DB terpisah (owner, rw, ro).
- Audit append-only berantai hash; ekspor diberi tanda air dan dicatat.
- Berkas unggahan tidak disimpan (hanya hash dan ringkasan). Data mikro perusahaan ditolak.
- Cadangan terenkripsi harian dan uji pemulihan bulanan.

## 8. Rencana kerja (fase; satu fase = satu sesi Claude Code dengan prompt di `prompts/`)

| Fase | Hasil | Kriteria selesai |
|---|---|---|
| F0 Fondasi | repo, Docker Compose, CI, skema + seed, auth (sandi + TOTP), RBAC/RLS, audit | `make test` lulus (uji skema, uji auth) |
| F1 Master | CRUD tahun dasar, pohon lapus, kelompok, konkordansi, katalog, wilayah, pengguna/penugasan | admin dapat mengubah pohon tanpa kode |
| F2 Mesin hitung | `apps/api/engine` (REV/EKS/DEF, jangkar, rumus turunan, tautan, adjustment, rekon, agregasi, kelompok, turunan) | uji unit + **golden test**: identik dengan `engine_ref` dan LK Put 0 (72/72 lapus) |
| F3 Data dasar | grid input, + Komoditas, impor/ekspor templat, seri referensi, validasi V01–V17 | templat TD2010 & TD2025 terisi diimpor tanpa galat; ekspor = impor (round-trip) |
| F4 Putaran & alur | putaran, penugasan, ajukan/setujui, adjustment, simulasi, kunci (423), bandingkan putaran | skenario ujung-ke-ujung lulus |
| F5 Tabel pokok & dashboard | tabel pokok lengkap sampai subkategori, turunan, ekspor (sistem + LK 02), dashboard | angka dashboard = tabel pokok; ekspor LK 02 cocok dengan Excel |
| F6 Rebasing | impor Put 0 TD2025 dari LK 01, impor rilis TD2010, jalur paralel, laporan jembatan TD2010↔TD2025 | Put 0 terimpor; laporan selisih konkordansi tersedia |
| F7 Pengerasan | uji keamanan, beban, cadangan/pemulihan, dokumentasi pengguna, pelatihan | checklist rilis lengkap |
