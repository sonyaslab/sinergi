# Format Templat Data Dasar dan Aturan Impor (v3)

Satu format untuk TD2010 dan TD2025. Templat dibangkitkan sistem dari master (`GET /ekspor/templat`), sehingga struktur selalu sesuai pohon lapus dan item yang berlaku. Pembaca rujukan: `tools/baca_templat.py`.

## 1. Sheet

| Sheet | Isi |
|---|---|
| PETUNJUK | cara isi singkat, daftar seri per metode, warna |
| A … U (TD2010) / A … V (TD2025) | satu sheet per kategori; M, N, R, S, T, U, (V) terpisah |
| SERI_REFERENSI | deflator/indeks bersama (kode REF_…) |
| PENYESUAIAN | ADJ1, ADJ2, SC (METODE) dan ADJ3, ADJ4_OUTPUT, ADJ4_NTB (REKON); opsional |
| REF_LAPUS, REF_SERI, REF_WILAYAH | acuan (terkunci) |
| KETERSEDIAAN, TEMUAN, DATA_DIKECUALIKAN, PARAMETER_LK_LAMA | hanya pada berkas terisi (informasi, tidak diimpor) |

## 2. Kolom sheet kategori (baris judul ke-4; data mulai baris 5)

| Kolom | Isi | Wajib |
|---|---|---|
| Kode Wilayah | 6500, 6501–6504, 6571 | ya |
| Kode Lapus | kode lapus daun pada kategori sheet itu | ya |
| Metode | REV, EKS, DEF, PDK | ya |
| No Item | 1–100 (REV), 1–50 (EKS/DEF), 1–200 (PDK); unik per wilayah × lapus × metode | ya |
| Komoditas / Rincian | nama baku (katalog) | ya |
| Kode Seri | lihat REF_SERI | ya |
| Satuan | satuan isian | ya |
| Jangkar Tahun Dasar | RKA_TD (baris RKA), H_TD (baris HARGA), IH_TD (baris IH) | RKA wajib untuk REV/EKS |
| 2019-T1 … 2026-T4 | angka; kosong = tidak tersedia | — |
| Seri, Jenis Indeks (EKS), Sumber Data, Tautan / Rumus, Lapus padanan / Kode LK BPS, Catatan, Lokasi Sumber | keterangan; Jenis Indeks wajib IP/IB untuk EKS | — |

**Baris rumus** (Tautan diawali `RUMUS:`) berwarna hijau dan berisi rumus Excel. Nilainya tidak diimpor; sistem menghitung ulang dari komponen. **Baris tautan** (`REF: kode`) mengambil seri dari SERI_REFERENSI.

## 3. Aturan impor

1. Impor selalu dimulai dengan **pratinjau**: jumlah item baru/berubah, sel berubah (lama → baru), dan pesan validasi. Penerapan baru terjadi setelah dikonfirmasi.
2. Item baru (kunci belum ada) dibuat dengan berlaku mulai triwulan pertama yang berisi angka. Alasan otomatis berbunyi "impor templat <nama berkas>".
3. Sel kosong pada berkas **tidak menghapus** nilai di sistem, kecuali opsi "kosongkan sel yang kosong di berkas" dicentang (khusus admin).
4. Teks di kolom angka, kode yang tidak dikenal, lapus di luar kategori sheet, atau seri yang tidak berlaku untuk metode akan ditolak per baris dengan pesan berisi sheet, baris, dan kolom.
5. Operator hanya dapat mengimpor lapus dan wilayah yang ditugaskan. Baris lain dilewati dengan pesan.
6. Putaran terkunci menolak seluruh impor.
7. Berkas mentah tidak disimpan; `audit.impor_berkas` menyimpan hash, ringkasan, dan pesan.
8. CSV bentuk panjang juga diterima dengan kolom: `tahun_dasar, kode_wilayah, kode_lapus, metode, no_item, komoditas, kode_seri, satuan, jangkar, periode, nilai, sumber, catatan`.

## 4. Berkas yang diserahkan bersama paket ini

| Berkas | Isi | Catatan |
|---|---|---|
| `Templat_Data_Dasar_TD2025_TERISI.xlsx` | 274 item, 18.924 angka 2019-T1 s.d. 2026-T3 dari LK 01 Put 0 (+ 2026-T3 untuk 6 seri dari data dasar Drive), 15 baris penyesuaian | Diuji: diimpor kembali dan dihitung = identik dengan LK untuk 72/72 lapus. RAHASIA |
| `Templat_Data_Dasar_TD2025_KOSONG.xlsx` | struktur sama, daftar item Put 0 tanpa angka | boleh di repo |
| `Templat_Data_Dasar_TD2010_TERISI.xlsx` | 361 item, 4.465 angka dari 19 berkas data dasar Drive (2019–2026 sesuai ketersediaan) | 4.298 angka dicek ulang ke sel sumber: semua sama. RAHASIA |
| `Templat_Data_Dasar_TD2010_KOSONG.xlsx` | struktur sama tanpa angka | boleh di repo |
