# Temuan Proses Bisnis LK PDRB Triwulanan TD2025 — Kalimantan Utara

**Status dokumen:** RAHASIA (memuat indikasi angka PDRB sebelum rilis). Jangan diunggah ke repositori publik.
**Dasar pemeriksaan:** LK 01 TD2025 v.1.0 (berkas operator Ayu/shared-6500, Dewi, sonya), LK 02 Kompilasi Put 0 (dua versi), hasil ekspor `6500 Kaltara TD 2025.xlsx`, `C. Indeks IBS Triwulanan.xls`, makro VBA kedua LK, serta rancangan dan rumus yang saya serahkan sebelumnya.

## Ringkasan

1. **Rumus LK TD2025 sudah dipetakan 1:1 dan terverifikasi.** Mesin rujukan `engine_ref/lk_engine.py` menghitung ulang setiap lapangan usaha dari lembar `DATA_REV`, `DATA_EKS`, dan `DATA_DEF`. Hasilnya dibandingkan dengan lembar hasil simpan `6500_<lapus>` pada 4 seri (Output dan NTB, ADHB dan ADHK) untuk 30 triwulan (2019Q1–2026Q2).
   - Untuk berkas operator yang dikompilasi ke LK 02, **71 dari 72 lapus identik** (selisih relatif < 10⁻⁶).
   - Satu lapus, B.3, berbeda karena hasil simpannya sudah usang, bukan karena rumusnya berbeda (lihat T3).
   - Templat data dasar TD2025 terisi yang diimpor kembali menghasilkan angka identik untuk 72/72 lapus.
2. **Sebagian rumus dalam rancangan saya sebelumnya tidak sesuai dengan LK TD2025 resmi**, terutama untuk EKS, DEF, rasio NTB, adjustment, klasifikasi, dan rentang periode. Semuanya sudah dikoreksi di paket ini (Bagian A).
3. **Ada 3 temuan kritis pada LK Put 0** yang membuat angka saat ini belum layak dipakai: data contoh templat ikut terjumlah, rasio konsumsi antara tahun dasar kosong, dan item tanpa nilai tahun dasar. Ketiganya dirinci di Bagian B dan diubah menjadi validasi otomatis di sistem (Bagian C).

---

## A. Koreksi atas rancangan dan rumus sebelumnya

Bagian ini menggantikan Bagian 4–5 `PROMPT_AGENT_SIKALTARA_LK.md` versi 1 (nama lama sistem; kini SINERGI) dan `Ringkasan_Rumus_LK_PDRB_per_Kategori.txt` versi 2. Rumus lengkap ada di `02_RUMUS_ENGINE.md`.

| No | Aspek | Rancangan lama | Yang benar (LK TD2025 resmi) | Tindakan di paket ini |
|---|---|---|---|---|
| A1 | Klasifikasi | 17 kategori TD2010 (A.1.a–A.1.g, C.1–C.16, MN, RSTU) | 75 lapus daun TD2025 (76 setelah TUV dipecah menjadi T.1, T.2, U, V) ditambah TOP (pajak atas produk) dan SOP (subsidi atas produk). PDRB = NTB atas harga dasar + TOP − SOP | Master `ref.lapus` per tahun dasar dan tabel konkordansi TD2010↔TD2025 (`db/seed_ref.sql`) |
| A2 | Rentang periode | 2025T1–2026T4 | Seri 2019Q1–2045Q4 (LK sudah berisi 2019Q1–2026Q2). Tahun 2019–2024 dihitung mundur (*backcasting*) | Tabel `ref.periode` 2010–2045; putaran jenis `BACKCAST` |
| A3 | Pustaka metode | REV, EKS, DEF, DD, PEN, MRG, IMP | Hanya **REV, EKS, DEF** (+ PDK pendukung). Satu lapus boleh memakai ketiganya sekaligus karena REKONSILIASI menjumlahkan REV + EKS + DEF. Pola TD2010 (PEN, MRG, harga dari IH) menjadi DEF/REV + jangkar + rumus turunan | Satu mesin untuk TD2010 dan TD2025 (`02_RUMUS_ENGINE.md` §2, §7) |
| A4 | EKS (ekstrapolasi) | ADHK = B·I/ΣI dengan B tahunan; ADHB = ADHK·IH·k | *Baseline* triwulanan 2025 per item (ADHB **dan** ADHK diisi). Dirantai q-to-q ke depan dan ke belakang. Dua jenis: Indeks Produksi (IP) menggerakkan ADHK, Indeks Berlaku (IB) menggerakkan ADHB. Tidak ada faktor k | `docs/02_RUMUS_ENGINE.md` §4 |
| A5 | DEF (deflasi) | ADHK = V·k/IH, k menormalkan 2025 | ADHK = V ÷ IH_t × rata-rata IH 2025 (tanpa k). NTB ADHB **diinput langsung**. Rasio KA tahun dasar = 1 − ΣNTB2025/ΣOutput2025 per item | `docs/02_RUMUS_ENGINE.md` §5 |
| A6 | NTB / biaya antara | Rasio NTB per lapus dari tabel biaya antara | **Rasio KA per item per triwulan** untuk ADHB, dan **rasio KA tahunan 2025 per item** (input) untuk ADHK. Hasil SE/SUT 2025 mengisi rasio KA tahun dasar | Seri `RKA` dan parameter `RKA_TD` per item |
| A7 | Adjustment | Satu jenis (nilai / target NTB / target laju) | Tiga tingkat: (i) per metode: ADJ1 *coverage*, ADJ2 *conceptual*, SC output sekunder — pada output, ADHB dan ADHK terpisah, NTB ikut proporsional. (ii) Rekonsiliasi: ADJ3 (output, NTB proporsional), ADJ4 *benchmarking* (output dan NTB terpisah), CT *control total* sebagai pembanding. (iii) Simulasi di kompilasi: adjustment NTB ADHK (rekonsiliasi growth) dan ADHB (rekonsiliasi implisit) per lapus per triwulan | Tabel `lk.penyesuaian` dengan tahap METODE/REKON/SIMULASI |
| A8 | ADHK | Implisit "CVM" | Tabel kompilasi memakai **FBY** (harga tetap 2025, aditif). Lembar CVM (OLAH_*) tidak aktif | FBY sebagai bawaan; modul CVM-QOM opsional (S4) |
| A9 | Wilayah | Provinsi = jumlah kab/kota | Setiap wilayah (6500, 6501–6504, 6571) punya LK sendiri. Tidak ada penjumlahan otomatis | Hitung per wilayah. Laporan selisih provinsi vs Σ kab/kota hanya sebagai pembanding |
| A10 | Alur kerja | Satu operator per kategori | Banyak operator memegang salinan LK masing-masing, lalu impor per subkategori ke LK 02 dengan tabel "Rekapitulasi Status Update" | `lk.penugasan` dan `lk.status_lapus` menggantikan salinan berkas |
| A11 | Templat data dasar v2 (sesi lalu) | Diberi label TD2025, kategori MN dan RSTU digabung | Isinya berstruktur **TD2010**. KBLI 2020 memisahkan M, N, R, S, T, U; KBLI 2025 memisahkan M, N, R, S, T, U, V | Templat v3: satu format untuk dua tahun dasar (TD2010 = KBLI 2020 A–U, TD2025 = KBLI 2025 A–V), berbasis item REV/EKS/DEF seperti LK resmi |
| A12 | Kelompok publikasi | — | Publikasi TD2010 17 kategori memakai "M,N" dan "R,S,T,U"; LK 02 TD2025 memakai "TUV" | Kategori disimpan terpisah; kelompok = baris jumlah (`ref.lapus_kelompok`) yang bisa ditampilkan atau disembunyikan |
| A13 | Tabel pokok | Hanya kategori | Excel menampilkan semua tingkat (kategori, subkategori, sub-subkategori, NTB, TOP/SOP, PDRB) | `lk.v_tabel_pokok` mengembalikan seluruh pohon untuk setiap periode, termasuk baris tanpa hasil |
| A14 | Komoditas per triwulan | Daftar komoditas tetap | Komoditas berganti sesuai ketersediaan data (mis. spesies ikan 2019–2021 lalu agregat DKP 2022+) | Operator menambah atau menonaktifkan item per triwulan (`periode_mulai`/`periode_selesai`); tabel pokok tidak berubah |

---

## B. Temuan pada LK TD2025 Put 0

Tingkat: **K** = kritis (angka salah), **T** = tinggi (berisiko salah atau kurang), **S** = sedang/rendah (perlu konfirmasi atau perbaikan proses).

### K1. Data contoh templat ikut terjumlah ke A.1.a dan A.1.b

- Berkas sumber kompilasi untuk subkategori A (shared-6500) masih menyimpan baris contoh bawaan templat:
  - EKS: Ubi Kayu (A.1.a), Semangka dan Melon (A.1.b), dengan *baseline* bulat 80.000; 85.000; ….
  - DEF: Ubi Jalar (A.1.a), Anggrek dan Anthurium (A.1.b).
- Nilainya identik dengan contoh di berkas operator lain, dan Ubi Kayu serta Ubi Jalar juga sudah diisi lewat REV, sehingga terhitung ganda.
- REKONSILIASI menjumlahkan REV + EKS + DEF, sehingga contoh ini masuk ke Kompilasi Put 0. Pembuktian dengan mesin rujukan:
  - Output ADHB A.1.a 2025Q1 di LK = REV riil + 79.200 (contoh EKS) + 17.100 (contoh DEF), atau **sekitar +51%**.
  - Tahun 2019 jauh lebih besar (sekitar 9 kali lipat) karena indeks contoh ikut di-*backcast*. Indeks implisit A.1.a 2019 menjadi 213,7.
- **Tindakan segera di Excel:** kosongkan keenam item contoh pada A.1.a dan A.1.b, simpan data, simpan rekonsiliasi, lalu impor ulang ke LK 02.
- **Di sistem:** tidak ada data contoh di basis data produksi. Validasi V05 menandai nama komoditas yang sama di dua metode pada lapus yang sama.

### K2. Rasio konsumsi antara tahun dasar (RKA 2025 tahunan) kosong

- Kolom tahunan 2025 baris `r.IC.CP_` pada REV dan EKS adalah sel input. Bila kosong, NTB ADHK = (1 − 0) × Output ADHK, artinya **NTB ADHK sama dengan Output ADHK**.
- Terjadi pada 17 lapus untuk seluruh 30 triwulan: A.1.c, A.1.d, A.1.e, A.2, B.1, B.2, B.3, B.4, D.1, D.2, F, G.1, G.2, H.3.a, H.3.b, H.4, I.1.
- Selain itu, A.1.b memiliki beberapa item (mis. cabai) tanpa RKA tahun dasar.
- A.3 tidak mengisi RKA triwulanan sejak 2022Q1, sehingga NTB ADHB = Output selama 18 triwulan.
- TUV.3 (*own consumption*) NTB = Output sepanjang seri. Ini mungkin memang konsepnya; perlu dikonfirmasi.
- Akibatnya NTB ADHK terlalu tinggi, serta indeks implisit dan laju NTB ADHK menjadi bias.
- RKA tahun dasar seharusnya diisi dari hasil SE/SUT 2025 (sesuai catatan Anda bahwa hasil SE memengaruhi rasio BA). Selama hasil itu belum tersedia, perlu angka sementara yang disepakati.
- **Di sistem:** V02 memblokir pengajuan bila item aktif tidak memiliki RKA_TD (REV/EKS) atau RKA triwulanan pada periode yang outputnya > 0.

### K3. Item tanpa nilai tahun dasar 2025 menghilang dari ADHK

- Harga tahun dasar REV = ΣOutput2025/ΣKuantum2025 per item. IH tahun dasar EKS/DEF = rata-rata IH 2025 per item. Rasio KA tahun dasar DEF dihitung dari nilai 2025.
- Item yang hanya ada di 2019–2024 (atau baru muncul setelah 2025) karena itu memperoleh harga tahun dasar 0 atau rasio 0:
  - **A.3:** 21 item rinci per spesies 2019–2021 (data 2022+ memakai agregat DKP), sehingga **ADHK A.3 2019–2021 = 0** padahal ADHB > 0 (indeks implisit tak hingga).
  - **B.3:** Produksi Emas 2019–2022 masuk ADHB tetapi tidak masuk ADHK, sehingga indeks implisit 2019–2022 hanya 36–56.
  - A.1.b (7 item), A.1.a (Kedelai), A.1.c (Tebu): kontribusi ADHK hilang pada tahun-tahun item tersebut.
  - I.2 dan P (DEF): item 2019–2022/2023 mendapat RKA_TD = 0, sehingga NTB ADHK = Output ADHK pada tahun-tahun tersebut.
  - **C.2.14 Aluminium** (produk baru 2026): ADHK = 0 karena tidak ada harga 2025. Ini penting karena produksi smelter akan besar.
- Ini adalah **celah proses bisnis rebasing**: daftar komoditas berubah dari waktu ke waktu, tetapi rumus LK mengandaikan setiap item punya nilai 2025.
- **Di sistem:** setiap item wajib memiliki "jangkar tahun dasar" (harga/IH/RKA 2025). Bila item tidak ada di 2025, operator memilih salah satu cara berikut (wajib alasan; disetujui supervisor):
  1. Isi harga/IH/RKA tahun dasar pengganti, mis. harga 2025 hasil deflasi IHPB.
  2. Sambungkan ke item penerus (mis. spesies 2019–2021 → agregat DKP 2022+) dengan *overlap*.
  3. Ganti metode.
- V03 memblokir pengajuan bila ada item tanpa jangkar.

### T1. Adjustment ADHB tanpa pasangan ADHK

- D.1 memiliki *coverage adjustment* ADHB −39% tanpa ADHK, sehingga **indeks implisit D.1 2025 = 61** (seharusnya ≈100 pada tahun dasar).
- P memiliki +15% tanpa ADHK, sehingga indeks implisit 2025 = 115.
- **Di sistem:** V06 memeriksa bahwa indeks implisit tahunan 2025 per lapus = 100 ± toleransi. Dialog ADJ1/ADJ2/SC menawarkan pengisian ADHK otomatis (ADHB ÷ IH) yang dapat diubah.

### T2. Pajak dan subsidi atas produk (TOP/SOP) belum diisi

PDRB Put 0 = NTB (baris TOP.SOP = 0). Dalam TD2025, PDRB = NTB atas harga dasar + TOP − SOP. Perlu data dasar pajak atas produk (PPN, cukai, bea masuk, pajak daerah atas barang/jasa tertentu, dan sebagainya) serta subsidi atas produk, beserta metodenya. **Perlu arahan BPS RI.**

### T3. Hasil rekonsiliasi tersimpan tidak sinkron dengan data dasar

- Di Excel, "simpan data" (`simpanRev/Eks/Def`) dan "simpan rekonsiliasi" (`simpanRekon`) adalah dua langkah terpisah. Bila data diubah tanpa menyimpan ulang rekonsiliasi, LK 02 mengimpor angka lama.
- Terbukti pada:
  - B.3 di berkas Dewi: ADHB 2019–2022 berbeda sekitar 65 kali antara data terkini dan hasil simpan yang dikompilasi.
  - D.1 dan H.5 di berkas sonya. Kedua lapus ini dikompilasi dari berkas Dewi, sehingga tidak berdampak.
- **Di sistem:** tidak ada langkah "simpan rekonsiliasi". Setiap perubahan memicu hitung ulang otomatis, dan setiap hasil menyimpan *hash input* dan versi mesin.

### T4. A.1.e Jasa Pertanian memakai indikator yang diketik manual

- "Kuantum" A.1.e berisi output ADHB A.1.a–A.1.d (sumber "PDRB ADHB"), tetapi angkanya tidak sama dengan hasil hitung LK yang sama (rasio 0,08–0,95).
- ADHK A.1.e = output **ADHB** × harga tahun dasar, sehingga volume tercampur efek harga.
- **Rekomendasi (perlu persetujuan metodologi):** tautkan otomatis.
  - Output ADHB A.1.e = r_t × ΣOutput ADHB(A.1.a–d).
  - Output ADHK A.1.e = r̄₂₀₂₅ × ΣOutput ADHK(A.1.a–d).
  - Sistem menyediakan "seri tertaut" (output lapus lain) sehingga A.1.e dihitung ulang otomatis setelah A.1.a–d berubah.

### T5. Pengelolaan berkas dan akses

- Penggabungan data antaroperator memakai makro `Copy_Data` dan `inputall` dengan memilih berkas, tanpa kontrol akses dan tanpa jejak perubahan.
- Berkas .xlsm berukuran 14–40 MB beredar di folder bersama.
- Risiko kebocoran dan penimpaan data tinggi. Sistem menggantinya dengan penugasan per lapus, RBAC, dan audit.

### T6. Tabel SoG di lembar KOMPILASI (LK 02) salah pembagi

- Rumus Tabel 9–11 (*source of growth*) di lembar KOMPILASI membagi dengan baris 210, yaitu ADHK **S.3 (Kesenian Swasta Nonmarket)**. Seharusnya baris 217, yaitu PDRB ADHK.
- Berkas `6500 Kaltara TD 2025.xlsx` adalah salinan lembar ini, sehingga ikut salah. Contoh: SoG q-to-q kategori A 2019Q2 tampil 57,094%, padahal yang benar 0,136%.
- Lembar EXPORT_KOMPILASI memakai tata letak berbeda; di sana baris 210 memang PDRB ADHK, sehingga benar.
- **Tindakan di Excel:** jangan memakai Tabel 9–11 dari lembar KOMPILASI atau dari berkas `6500 Kaltara TD 2025.xlsx`; pakai hasil tombol EXPORT KOMPILASI. Laporkan ke pengelola LK nasional.
- **Di sistem:** SoG dihitung dari baris PDRB secara eksplisit dan diuji.

### S — Sedang/rendah (perlu konfirmasi atau perbaikan kecil)

| No | Temuan | Rekomendasi |
|---|---|---|
| S1 | C.1.1, C.2.3, dan H.1 tanpa data | Bila memang tidak ada aktivitas di Kaltara, tandai **nihil** secara eksplisit (status lapus `NIHIL`) agar tidak terbaca "belum diisi" |
| S2 | Data 2026 belum lengkap: harga D.1 2026 kosong (Output ADHB 0 sedangkan ADHK > 0); D.2, F, dan M kosong di 2026 | V01 (kelengkapan per periode) |
| S3 | Pada REKONSILIASI baris 29–31 berlabel "Rasio Konsumsi Antara", rumusnya NTB/Output (rasio NTB) | Sistem menampilkan rasio KA = 1 − NTB/Output dengan label yang benar |
| S4 | LK 02 berjudul "Kompilasi CVM", tetapi tabelnya FBY. Lembar OLAH_* (QOM, UVUC, UICH, FTR) *very hidden*, berisi #REF!, dan masih berstruktur 17 kategori | Konfirmasi ke BPS RI apakah rilis regional TD2025 memakai FBY atau CVM. Sistem: FBY bawaan, CVM-QOM sebagai modul opsional |
| S5 | SIMULASI blok 2019 dan SoG y-on-y 2019 berisi #REF! karena tidak ada 2018 | Tampilkan kosong; tidak dihitung |
| S6 | Deflator identik lintas lapus (C.2.10=C.2.11; C.2.15–C.2.17; J.1=J.2=K; R.1–R.3; S, TUV) | Wajar bila sumber deflator sama. Sistem memakai satu **seri referensi** yang ditautkan ke banyak item, bukan disalin |
| S7 | D.2 indeks implisit = 100 di semua tahun (harga gas konstan) | Cek ketersediaan harga gas berkala |
| S8 | Bobot item EKS hanya dipakai untuk indeks agregat tampilan, tidak memengaruhi output | Jelaskan di UI agar operator tidak salah paham |
| S9 | Berkas Indeks IBS memuat **data mikro perusahaan** (nama, KIP, nilai produksi). Indeks hanya tersedia 2022Q1–2025Q3, dan yang berisi hanya KBLI 10, 16, 18, 23, 25 | Data mikro **tidak** dimasukkan ke sistem; hanya indeks agregat KBLI 2 digit. *Backcast* 2019–2021 C.2.x memakai IMK lama |
| S10 | Put 0 baru untuk provinsi (6500) | Kab/kota menyusul dengan struktur yang sama |
| S11 | Nama komoditas tidak baku (spasi ganda, "Gurame; Gurami", "imk", "Reaisasi") | Katalog komoditas baku dan *autocomplete* |

---

## C. Validasi otomatis yang dibangun ke sistem

| Kode | Aturan | Sifat |
|---|---|---|
| V01 | Item aktif: sel periode wajib belum diisi | Peringatan; memblokir pengajuan bila periode berjalan |
| V02 | RKA_TD kosong (REV/EKS) atau RKA triwulanan kosong saat output > 0 | Blokir pengajuan |
| V03 | Item tanpa jangkar tahun dasar (harga/IH/RKA 2025) | Blokir pengajuan |
| V04 | EKS: jenis indeks kosong, baseline ADHB dan ADHK keduanya kosong, atau indeks t−1/t+1 kosong saat rantai berjalan | Peringatan |
| V05 | Komoditas sama di dua metode pada lapus yang sama (potensi hitung ganda) | Blokir kecuali dikonfirmasi beralasan |
| V06 | Indeks implisit tahunan 2025 per lapus ≠ 100 ± 0,5 | Peringatan keras |
| V07 | ADJ1/ADJ2/SC ADHB tanpa pasangan ADHK (atau sebaliknya) | Peringatan |
| V08 | Lonjakan q-to-q / y-on-y volume atau implisit melewati ambang (dapat diatur per lapus) | Peringatan |
| V09 | NTB ≥ Output atau NTB < 0 | Peringatan keras |
| V10 | ADHK = 0 sementara ADHB > 0 (atau sebaliknya) | Blokir pengajuan |
| V11 | Selisih terhadap *control total* (CT) melebihi ambang | Informasi |
| V12 | Item EKS tanpa baseline (tidak berkontribusi) | Informasi |
| V13 | Lapus tanpa item dan tanpa status NIHIL | Blokir kunci putaran |
| V14 | TOP/SOP kosong saat putaran akan dikunci | Blokir kunci (dapat dikecualikan admin dengan alasan) |
| V15 | Hasil tersimpan berbeda dari hitung ulang (hash input berubah) | Tidak mungkin terjadi; diuji di CI |
| V16 | Satuan isian berbeda dengan satuan item (E7) | Peringatan |
| V17 | Item berlaku tetapi semua seri wajib kosong pada periode berjalan | Peringatan |

Tingkat dan ambang dibaca dari `ref.validasi` (F3; ambang V08/V11 dan kalibrasi P95 per lapus: docs/02 §11 keputusan 16).

---

## E. Celah proses bisnis tambahan (pemeriksaan v4)

| No | Celah | Usulan |
|---|---|---|
| E1 | Belum ada tempat menyimpan angka **rilis resmi** TD2010 2019–sekarang. Angka ini dibutuhkan untuk laju y-on-y triwulan pertama, baseline EKS TD2010, dan pembanding revisi. | Tabel `lk.tabel_pokok_rilis` beserta menu impor rilis (izin `rilis.impor`) |
| E2 | Pemisahan T/U/V pada TD2025 belum ada di LK resmi (masih TUV). | Simpan terpisah. Ekspor ke format LK 02 menjumlahkan menjadi TUV. Konfirmasi pemetaan PRT (rumah tangga pemberi kerja) ke U |
| E3 | Data dasar Drive untuk 2019–2021 hanya sebagian (umumnya mulai 2022–2024). | Riwayat TD2010 diambil dari rilis (E1). Riwayat TD2025 berasal dari *backcast* Put 0 |
| E4 | Lapus tanpa data di Drive: TD2010 N, T, U, B.3, J (sebagian), K.1; TD2025 C.1.1, C.2.3, H.1, V. | Wajib diisi atau ditandai NIHIL sebelum kunci putaran (V13) |
| E5 | Tidak ada jadwal rilis dan *cut-off* data per putaran. | Putaran menyimpan tanggal *cut-off*; data dasar yang diubah setelah *cut-off* butuh alasan dan tercatat |
| E6 | Kab/kota belum punya LK sendiri (Put 0 hanya 6500). | Struktur sama per wilayah; laporan selisih provinsi vs Σ kab/kota hanya sebagai pembanding |
| E7 | Satuan dan skala sering tidak tertulis di sumber (gas bumi, nilai impor, LKPM, pajak Nunukan). | Satuan wajib di item; validasi V16 menandai satuan berbeda |

## D. Hal yang perlu dikonfirmasi

1. Nilai RKA tahun dasar 2025 per item: dari SUT/SE 2025 atau angka sementara? Siapa yang menetapkan?
2. Metode dan sumber data TOP/SOP untuk Kaltara.
3. FBY atau CVM untuk rilis regional TD2025; bila CVM, metode *overlap* apa (QOM/annual overlap) dan tahun referensinya.
4. Persetujuan metode A.1.e tertaut (T4).
5. Cara standar untuk item yang tidak ada di 2025 (K3): harga deflasi, *overlap*, atau ganti metode.
6. Jadwal *cut-over* TD2010 → TD2025 dari BPS RI (menentukan lamanya jalur paralel).
7. TUV.3 dengan NTB = Output: memang konsepnya?
8. Pemisahan TUV menjadi T (TUV.1 + TUV.2), U (TUV.3), V (nihil) untuk tampilan sistem; ekspor tetap TUV.
9. Sumber angka rilis TD2010 2019–2025 untuk diimpor sebagai riwayat (BRS/publikasi atau LK induk final).
