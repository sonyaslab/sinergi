# Format Templat Data Dasar dan Aturan Impor (v3, diterapkan F3)

Satu format untuk TD2010 dan TD2025. Templat dibangkitkan sistem dari master (`GET /api/ekspor/templat`), sehingga struktur selalu sesuai pohon lapus dan item yang berlaku. Importer: `apps/api/impor/templat.py` (baca), `tautan.py` (kolom Tautan / Rumus), `terapkan.py` (pratinjau selisih dan penerapan), `ekspor.py` (pembangkit). Pembaca rujukan untuk uji: `tools/baca_templat.py`.

## 1. Sheet

| Sheet | Isi |
|---|---|
| PETUNJUK | cara isi singkat, daftar seri per metode, warna |
| A … U (TD2010) / A … V (TD2025) | satu sheet per kategori; M, N, R, S, T, U, (V) terpisah |
| TOP_SOP | item pajak dan subsidi atas produk (keputusan 1); kolom sama dengan sheet kategori; dibangkitkan hanya bila ada item TOP/SOP |
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

Kolom padanan: TD2025 = "Kode LK BPS" (kode LK 02, mis. TUV.1); TD2010 = "Lapus TD2025 (konkordansi)" (bila satu kode dan
dikenal, menjadi `lk.item.lapus_padanan_id`). Teks asli setiap baris (Satuan, Seri, Catatan, Lokasi Sumber, Tautan) disimpan
di `lk.seri_item` sehingga ekspor sama dengan berkas yang diimpor.

### 2a. Kolom Tautan / Rumus (tata bahasa)

| Teks (huruf besar/kecil bebas) | Arti | Nilai baris |
|---|---|---|
| `REF: REF_UPAH` | seri baris ini = seri referensi (wilayah yang sama) | tidak diimpor |
| `RUMUS: …` | rumus baku menurut seri sasaran: KUANTUM (REV) → `TPK_X_KAMAR`; HARGA (REV) → `JANGKAR_X_IH_100`; OUT_ADHB (DEF, teks memuat "kapita") → `KAPITA_X_PENDUDUK_X_3`; atau tulis kode baku | tidak diimpor |
| `MARGIN: output barang lapus A.1.a[, A.1.b]` | `MARGIN_X_OUTPUT` pada OUT_ADHB (boleh di baris R_MARGIN atau OUT_ADHB) | — |
| `MARGIN: nilai impor` | `MARGIN_X_IMPOR` pada OUT_ADHB | — |
| `HASIL: OUT_CP lapus A.1.a, A.1.b` | `HASIL_LAPUS` (besaran OUT_CP, OUT_K, GVA_CP, GVA_K, IMPLISIT_OUT) | tidak diimpor |
| `Dihitung sistem: …` | baris hasil rumus margin | tidak diimpor |
| `Ikut IH item C201`, `Harga mengikuti item Sapi` | "ikut item lain" → seri referensi `REF_<SERI>_<LAPUS>_<METODE><NO>` milik lapus sumber; item sumber dan pengikut ditautkan (keputusan 5). Kode item = kode lapus tanpa titik + nomor 2 digit; nama dicari pada lapus yang sama | tidak diimpor |
| teks lain | keterangan biasa | diimpor |

Faktor opsional: `faktor 0,8865` atau persen (`88,65%`). Ekspor menulis teks asli bila masih setara dengan tautan tersimpan;
bila tidak, teks baku di atas.

## 3. Aturan impor

1. Impor selalu dimulai dengan **pratinjau** (`POST /api/impor/templat?putaran_id=&nama=`, badan = berkas mentah): jumlah item baru/berubah, sel berubah (lama → baru), jangkar, tautan, seri referensi, penyesuaian, dan pesan validasi. Penerapan (`POST /api/impor/{id}/terapkan`) mengirim ulang **berkas yang sama** (sha256 dicocokkan) dalam 6 jam; ditolak bila data sistem berubah sejak pratinjau (sidik rencana) atau masih ada galat format. Ukuran maksimal 25 MB.
2. Item baru (kunci belum ada) dibuat dengan berlaku mulai triwulan pertama yang berisi angka. Alasan otomatis berbunyi "impor templat <nama berkas>".
3. Sel kosong pada berkas **tidak menghapus** nilai di sistem, kecuali opsi "kosongkan sel yang kosong di berkas" dicentang (khusus admin).
4. Teks di kolom angka, kode yang tidak dikenal, lapus di luar kategori sheet, atau seri yang tidak berlaku untuk metode akan ditolak per baris dengan pesan berisi sheet, baris, dan kolom.
5. Operator hanya dapat mengimpor lapus dan wilayah yang ditugaskan. Baris lain dilewati dengan pesan. Seri referensi hanya dapat dibuat/diubah oleh pemegang `data.tulis_semua`/`master.kelola`, atau operator lapus pemiliknya (seri hasil konversi "ikut item lain").
6. Putaran terkunci menolak seluruh impor. Lapus yang data, item, jangkar, tautan, atau penyesuaiannya berubah karena impor
   kembali berstatus draf (F4, keputusan 19); sesudah *cut-off* alasan otomatis "impor templat <berkas>" dicatat di audit.
7. Berkas mentah tidak disimpan; `audit.impor_berkas` menyimpan hash, ringkasan, dan pesan.
8. CSV bentuk panjang juga diterima dengan kolom: `tahun_dasar, kode_wilayah, kode_lapus, metode, no_item, komoditas, kode_seri, satuan, jangkar, periode, nilai, sumber, catatan` (UTF-8; pemisah `,` atau `;`; satu baris = satu nilai; CSV tidak membawa tautan). Seri referensi: CSV `kode_wilayah, kode_referensi, nama, satuan, periode, nilai` atau xlsx yang hanya berisi sheet SERI_REFERENSI.
9. **Jangkar**: baris RKA → `RKA_TD`, HARGA → `H_TD`, IH → `IH_TD`, R_MARGIN → `R_MARGIN_TD` (`lk.parameter_item`); H_TD/IH_TD diberi alasan "impor templat <berkas>". Tahun dasar tanpa `jangkar_dari_data` (TD2010): baris IH bersatuan "2010=100" yang jangkarnya kosong diberi IH_TD = 100 (keputusan 3), kecuali parameter sudah ada. Templat kosong (ekspor) tidak memuat angka apa pun, termasuk jangkar.
10. **Penyesuaian** (sheet PENYESUAIAN, tahap METODE/REKON; simulasi tidak diimpor) masuk sebagai draf; pemegang `penyesuaian.putus` boleh memilih "setujui penyesuaian dari berkas" (keputusan 15). Alasan wajib min. 10 karakter (kecuali CT).
11. Nama komoditas dirapikan (spasi ganda, S11) dan dicocokkan ke katalog baku (`katalog_id`); satuan baris pertama yang dikenal menjadi satuan item. Satuan berkas yang berbeda dari tersimpan diberi peringatan V16.
12. **Data mikro perusahaan ditolak**: baris dengan nama berawalan badan usaha (PT, CV, UD, PD, Koperasi, Tbk) atau memuat NIB/KIP/angka 13 digit ditolak dengan pesan tanpa isi sel.
13. Ekspor (`GET /api/ekspor/templat?putaran_id=&wilayah=&kosong=`, `GET /api/ekspor/csv`, `GET /api/ekspor/seri-referensi`) bertanda air dan tercatat di `audit.ekspor`. Nilai diekspor hanya dalam masa berlaku item (nilai di luar masa tidak dipakai mesin), sehingga **ekspor → impor → hitung = sama** (diuji: impor ulang ke putaran yang sama tanpa perubahan; ke tahun dasar baru, selisih hasil 0).

## 4. Berkas yang diserahkan bersama paket ini

| Berkas | Isi | Catatan |
|---|---|---|
| `Templat_Data_Dasar_TD2025_TERISI.xlsx` | 274 item, 18.924 angka 2019-T1 s.d. 2026-T3 dari LK 01 Put 0 (+ 2026-T3 untuk 6 seri dari data dasar Drive), 15 baris penyesuaian | Diuji: diimpor kembali dan dihitung = identik dengan LK untuk 72/72 lapus. RAHASIA |
| `Templat_Data_Dasar_TD2025_KOSONG.xlsx` | struktur sama, daftar item Put 0 tanpa angka | boleh di repo; diuji F3: impor tanpa galat → ekspor kosong sama persis per sel (spasi ganda dirapikan; "ikut item lain" menjadi `REF:`) |
| `Templat_Data_Dasar_TD2010_TERISI.xlsx` | 361 item, 4.465 angka dari 19 berkas data dasar Drive (2019–2026 sesuai ketersediaan) | 4.298 angka dicek ulang ke sel sumber: semua sama. RAHASIA |
| `Templat_Data_Dasar_TD2010_KOSONG.xlsx` | struktur sama tanpa angka | boleh di repo |
