# Eksekusi Rebasing TD2010 → TD2025 dan Data Historis 2019+

## 1. Prinsip

1. **Dua jalur dalam satu sistem.**
   - TD2010 (KBLI 2020) tetap jalur produksi triwulan berjalan sampai *cut-over*.
   - TD2025 (KBLI 2025) berjalan paralel mulai Put 0.
   - Keduanya memakai mesin, layar, dan alur yang sama. Yang berbeda hanya master (`ref.tahun_dasar`, pohon lapus) dan jangkar tahun dasar.
2. **Data dasar diinput sekali.**
   - Kuantum, harga, nilai, dan indeks dari sumber yang sama dipakai kedua jalur lewat item di masing-masing tahun dasar.
   - Item TD2010 menyimpan `lapus_padanan_id` (lapus TD2025). Item TD2025 dapat dibuat dari item TD2010 dengan tombol "Salin ke TD2025".
3. **Seri mulai 2019Q1.**
   - TD2025 dihitung mundur (*backcast*) 2019Q1–2024Q4 dari jangkar 2025 (EKS dirantai mundur; REV/DEF memakai data riil 2019+).
   - TD2010 2019–sekarang memakai angka rilis resmi sebagai riwayat dan pembanding.

## 2. Langkah eksekusi

| No | Langkah | Siapa | Alat di sistem | Hasil |
|---|---|---|---|---|
| 1 | Siapkan master TD2025: pohon 76 lapus daun + T/U/V terpisah, kelompok TUV, konkordansi | Admin | seed `db/seed_ref.sql` | Master siap |
| 2 | Impor angka rilis TD2010 2019–triwulan terakhir per wilayah | Admin | `POST /impor/rilis` → `lk.tabel_pokok_rilis` | Riwayat TD2010 tersedia untuk laju y-on-y dan pembanding |
| 3 | Buka putaran TD2025 Put 0 (`BACKCAST`, 2019Q1–2026Q2) | Admin | Putaran | Putaran terbuka |
| 4 | Impor data Put 0 dari LK 01 TD2025 (per berkas operator sesuai rekap LK 02) **atau** dari templat TD2025 terisi | Admin/operator | `POST /impor/lk01` / `POST /impor/templat` | Item dan data 2019–2026 masuk; baris contoh templat ditolak (K1) |
| 5 | Isi RKA tahun dasar (Biaya Antara) dari SE2026/SUT; isi jangkar untuk item tanpa data 2025 | Operator | Biaya Antara → Terapkan; dialog jangkar | V02/V03 lolos |
| 6 | Hitung, validasi, ajukan, setujui per lapus; kompilasi + simulasi | Semua | alur standar | Put 0 final |
| 7 | **Laporan jembatan** TD2010 ↔ TD2025 per kategori TD2010 (konkordansi): level, laju y-on-y, implisit, selisih | Supervisor | `GET /laporan/jembatan` | Penjelasan perbedaan (cakupan, klasifikasi, metode, jangkar) |
| 8 | Jalankan paralel tiap triwulan: TD2010 (rilis berjalan) dan TD2025 (putaran reguler) | Semua | putaran per tahun dasar | Dua seri sinkron |
| 9 | *Cut-over* sesuai jadwal BPS RI: TD2025 menjadi `produksi`, TD2010 menjadi `arsip` (read-only) | Admin | `ref.tahun_dasar.status` | Rilis memakai TD2025 |

## 3. Aturan teknis rebasing

- **Item tanpa nilai 2025** (berhenti sebelum 2025 atau baru muncul sesudahnya). Wajib salah satu dari:
  - jangkar pengganti (`H_TD`/`IH_TD` dengan alasan);
  - sambungan ke item penerus (`item_asal_id`, overlap minimal satu tahun);
  - ganti metode.

  Contoh: spesies ikan 2019–2021 disambung ke agregat DKP 2022+; emas 2019–2022 diberi harga 2025 hasil deflasi; aluminium 2026 diberi harga tahun dasar pengganti.
- **EKS backcast:** baseline 2025 dirantai mundur memakai indeks 2019–2024. Rantai putus (indeks kosong) memutus seluruh periode sebelumnya. Validasi V04 menandainya.
- **Konkordansi 1:N** (mis. TD2010 J → TD2025 J.1, J.2, K; G.1 → G.1, G.2, T.1): bobot diisi dari SUT/SE2026. Selama bobot belum ada, laporan jembatan memakai jumlah kategori.
- **Kategori terpisah:**
  - TD2010 M/N dan R/S/T/U dihitung terpisah. Publikasi 17 kategori memakai kelompok "M,N" dan "R,S,T,U".
  - TD2025 T/U/V dihitung terpisah. Ekspor LK 02 memakai kelompok "TUV".
- **Penomoran item tetap stabil antarputaran.** Item yang berhenti dinonaktifkan, tidak dihapus, sehingga riwayat 2019+ tetap utuh.

## 4. Kebutuhan data yang masih kosong (Kaltara)

- TD2025:
  - RKA tahun dasar 17 lapus;
  - TOP/SOP;
  - data C.1.1, C.2.3, H.1 (atau status nihil);
  - harga D.1 2026;
  - data 2026-T3 (kecuali 6 seri yang sudah dilengkapi dari data dasar Drive).
- TD2010:
  - riwayat 2019–2021 untuk sebagian besar data dasar;
  - angka rilis 2019–2025;
  - data N, T, U;
  - indeks IBS/IMK 2025-T3 dan sesudahnya.
