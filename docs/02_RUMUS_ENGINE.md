# Rumus Mesin Hitung SINERGI (versi 4)

Spesifikasi wajib mesin hitung. Untuk TD2025, rumus ini identik dengan LK Excel resmi "01 LK PDRB Triwulanan TD2025 v.1.0" dan "02 LK Kompilasi PDRB TD 2025 v.1.0". Kesamaan diuji dengan `engine_ref/lk_engine.py` atas data Kaltara Put 0:

- 71 dari 72 lapus identik dengan hasil simpan LK. B.3 berbeda karena hasil simpannya usang.
- Templat terisi yang diimpor kembali menghasilkan angka identik untuk 72/72 lapus.

TD2010 memakai mesin yang sama. Bedanya ada pada **jangkar tahun dasar** (bagian 2) dan **rumus turunan** (bagian 7).

Mesin produksi: `apps/api/engine` (modul murni). Oracle: `engine_ref/lk_engine.py` (per lapus sampai BENC),
`engine_ref/turunan.py` (rumus turunan dan tautan), `engine_ref/kompilasi.py` (tingkat wilayah: graf tautan,
simulasi, agregasi, tabel turunan). Golden test: mesin produksi = oracle, relatif ≤ 1e-9.

Setiap rumus diikuti asal angkanya di basis data (`db/schema.sql`).

---

## 0. Notasi dan aturan umum

| Simbol | Arti | Diambil dari (DB) |
|---|---|---|
| t | triwulan (2010Q1 … 2045Q4; seri TD2025 mulai 2019Q1) | `ref.periode` |
| T₀ | 4 triwulan **tahun baseline** (TD2025 = 2025; TD2010 = `ref.tahun_dasar.tahun_baseline_eks`, mis. 2024) | `ref.tahun_dasar` |
| i | satu item (komoditas/rincian) = wilayah × lapus × metode × nomor | `lk.item` |
| ADHB / CP | harga berlaku | — |
| ADHK / K | harga konstan tahun dasar (FBY, aditif) | — |
| RKA | rasio konsumsi antara = KA ÷ Output | seri `RKA` di `lk.nilai_item` |
| RKA_TD | rasio KA tahun dasar per item (jangkar) | `lk.parameter_item` kode `RKA_TD` |
| H_TD, IH_TD | jangkar harga / indeks harga tahun dasar | `lk.parameter_item` kode `H_TD`, `IH_TD` |

Perilaku yang harus sama dengan Excel:

1. Sel kosong dihitung 0 dalam jumlah dan kali. Pembagian dengan 0 atau kosong menghasilkan 0 (`IFERROR(…,0)`).
2. Rata-rata mengabaikan sel kosong; bila semua kosong, hasilnya 0.
3. Nilai tahunan = jumlah 4 triwulan (output, NTB). Indeks dan harga tahunan punya rumus sendiri.
4. Hitung dalam float64, simpan `NUMERIC` presisi penuh, bulatkan hanya saat tampil atau ekspor.
5. Kosong ≠ nol untuk **validasi**. Kolom `status_sel` membedakan `tidak_tersedia` dan `belum`, tetapi keduanya 0 di mesin.

**Komoditas dinamis.** Item boleh muncul atau hilang antartriwulan (`periode_mulai_id`, `periode_selesai_id`). Output lapus selalu jumlah item yang punya data pada triwulan itu. Format tabel pokok tidak berubah karena baris tabel pokok adalah lapus, bukan item.

---

## 1. Alur hitung satu lapus (satu wilayah, satu putaran)

```
data dasar item (REV | EKS | DEF)        [+ rumus turunan & tautan diselesaikan dulu]
  └─► hitung per item ─► jumlah per metode (PR)
        └─► + ADJ1 coverage, ADJ2 konseptual, SC sekunder (per metode)   = PRE-RECON metode
              └─► jumlah REV + EKS + DEF                                  = PRE-RECON lapus
                    └─► + ADJ3 rekonsiliasi                                = POST-RECON
                          └─► + ADJ4 benchmarking                          = BENC (hasil LK 01)
                                └─► agregasi pohon + SIMULASI (LK 02)      = FINAL (tabel pokok)
```

Satu lapus boleh memakai ketiga metode sekaligus; hasilnya **dijumlahkan**. Item `PDK` (pendukung) tidak dihitung.

---

## 2. Jangkar tahun dasar (satu mesin untuk TD2010 dan TD2025)

Aturan dipilih menurut `ref.tahun_dasar.jangkar_dari_data` (keputusan 3 §11): TD2025 = ya, TD2010 = tidak.

| Jangkar | Bila diisi (`lk.parameter_item`) | Bila kosong, `jangkar_dari_data` = ya (TD2025) | Bila kosong, = tidak (TD2010) |
|---|---|---|---|
| H̄ (REV) | `H_TD` (TD2010: harga 2010) | Σ₍T₀₎ Output ADHB ÷ Σ₍T₀₎ kuantum | 0 (V03) |
| ĪH (EKS, DEF) | `IH_TD` (TD2010: 100) | rata-rata IH pada T₀ | 0 (V03) |
| RKA_TD (REV, EKS) | `RKA_TD` — **wajib** | kosong = 0, diblokir validasi V02 | sama |
| RKA_TD (DEF) | TD2025: dipakai hanya bila tidak ada data T₀; TD2010: selalu | 1 − Σ₍T₀₎ NTB ADHB ÷ Σ₍T₀₎ Output ADHB | 0 (V03) |
| R_TD margin (`R_MARGIN_TD`) | dipakai | Σ₍T₀₎ (R × basis ADHB) ÷ Σ₍T₀₎ basis ADHB (bagian 7) | 0 (V03) |

T₀ = 4 triwulan `tahun_baseline_eks`. Pada TD2010, T₀ hanya titik awal rantai EKS (BASE_ADHB/BASE_ADHK), tidak pernah
sumber jangkar. Item tanpa data tahun dasar wajib diberi jangkar (V03). Contohnya spesies ikan 2019–2021, emas 2019–2022, dan aluminium 2026. Tanpa jangkar, ADHK item tersebut menjadi 0 (temuan K3).

## 3. REV — Revaluasi (kuantum × harga)

Seri: `KUANTUM`, `HARGA`, `RKA`. Seri `IH` bersifat opsional.

1. Output ADHB(i,t) = KUANTUM × HARGA
2. Output ADHK(i,t) = KUANTUM × H̄(i)
3. NTB ADHB(i,t) = (1 − RKA(i,t)) × Output ADHB
4. NTB ADHK(i,t) = (1 − RKA_TD(i)) × Output ADHK

## 4. EKS — Ekstrapolasi

Seri: `INDEKS`, `IH`, `BASE_ADHB` dan `BASE_ADHK` (4 triwulan T₀), `RKA`. Kolom `jenis_indeks`: **IP** (indeks produksi, menggerakkan ADHK) atau **IB** (indeks berlaku, menggerakkan ADHB). Bobot hanya untuk indeks agregat tampilan.

| | IB | IP |
|---|---|---|
| T₀ (triwulan q) | CP = BASE_ADHB(q); K = CP ÷ IH × ĪH | K = BASE_ADHK(q); CP = K × IH ÷ ĪH |
| maju t > T₀ | CP(t) = I(t)/I(t−1) × CP(t−1); K = CP ÷ IH × ĪH | K(t) = I(t)/I(t−1) × K(t−1); CP = K × IH ÷ ĪH |
| mundur t < T₀ (*backcast*) | CP(t) = I(t)/I(t+1) × CP(t+1); K = CP ÷ IH × ĪH | K(t) = I(t)/I(t+1) × K(t+1); CP = K × IH ÷ ĪH |

NTB dihitung sama seperti REV. Jika rantai indeks putus (indeks kosong), semua periode sesudah atau sebelumnya menjadi 0 (V04).

## 5. DEF — Deflasi

Seri: `OUT_ADHB`, `NTB_ADHB` (opsional), `IH`, `RKA` (opsional).

1. Output ADHB = OUT_ADHB
2. NTB ADHB = NTB_ADHB bila diisi. Bila kosong: (1 − RKA(t)) × Output ADHB; jika RKA(t) juga kosong, pakai RKA_TD. Ini pola TD2010, misalnya belanja pegawai O/P/Q dengan RKA_TD = 0. Bila NTB_ADHB, seri RKA, dan RKA_TD semuanya kosong, NTB ADHB = 0 (perilaku LK).
3. Output ADHK = Output ADHB ÷ IH(t) × ĪH; item margin (bagian 7) membawa output ADHK langsung (arus barang).
4. NTB ADHK = (1 − RKA_TD) × Output ADHK

**TOP/SOP** (keputusan 1 §11): item pada lapus berjenis `top`/`sop` tidak punya konsumsi antara, sehingga NTB = output
(ADHB dan ADHK) apa pun isian RKA/NTB_ADHB-nya. Berlaku untuk REV, EKS, dan DEF.

## 6. Penyesuaian (adjustment) — tiga tahap

**Tahap METODE** (per lapus × metode × triwulan, terpisah ADHB/ADHK):
- Output PRE = ΣOutput + ADJ1 + ADJ2 + SC
- NTB PRE = ΣNTB + r × (ADJ1 + SC) + r × ADJ2, dengan r = ΣNTB ÷ ΣOutput metode itu

**Tahap REKON** (per lapus × triwulan, terpisah ADHB/ADHK):
- Output POST = Output PRE + ADJ3
- NTB POST = NTB PRE + (ADJ3 ÷ Output PRE) × NTB PRE
- Output BENC = Output POST + ADJ4_OUTPUT
- NTB BENC = NTB POST + ADJ4_NTB
- KA = Output − NTB. CT_OUTPUT dan CT_NTB hanya pembanding (V11).

**Tahap SIMULASI** (per lapus berdata × triwulan; izin `simulasi.edit`):
- NTB ADHK final = NTB ADHK kompilasi + SIM (ADHK); NTB ADHB final = NTB ADHB kompilasi + SIM (ADHB)
- Output final ikut proporsi NTB: Output.SIM = Output × NTB.SIM ÷ NTB. Triwulan tanpa SIM (0): FINAL = BENC apa adanya.
- Baris agregat FINAL = Σ FINAL lapus berdata (simulasi tidak diinput pada agregat).
- Bantuan input: "target laju y-on-y" → adj = NTB(t−4) × (1 + g/100) − NTB kompilasi; "target implisit" → adj = target implisit × NTB ADHK ÷ 100 − NTB ADHB

Semua penyesuaian wajib beralasan (min. 10 karakter) dan hanya status `disetujui` yang masuk angka final
(`lk.hasil_*`). Pratinjau draf/diajukan dihitung saat diminta dan tidak disimpan (keputusan 8a §11).

## 7. Rumus turunan dan tautan (`lk.tautan_seri`)

Seri yang tidak diketik operator, tetapi diselesaikan sistem sebelum langkah 1:

| Kode rumus | Rumus | Dipakai |
|---|---|---|
| `TPK_X_KAMAR` | KUANTUM = TPK (persen) × KAMAR | I.1 hotel (sama dengan LK TD2025: 35,99 × 375 = 13.496,25) |
| `JANGKAR_X_IH_100` | HARGA = H_TD × IH ÷ 100 | TD2010 hortikultura A.1.b, A.1.d |
| `KAPITA_X_PENDUDUK_X_3` | OUT_ADHB = per kapita × penduduk × 3 ÷ 10⁶ × faktor | TD2010 I.1 sewa, I.2 makan minum (faktor 0,8865) |
| `MARGIN_X_OUTPUT` | basis = Σ Output lapus barang tahap **BENC**; OUT_ADHB = R_MARGIN(t) × basis ADHB(t) × faktor; Output ADHK = R_TD × basis ADHK(t) × faktor | TD2010 G.2 arus komoditas (keputusan 4) |
| `MARGIN_X_IMPOR` | basis ADHB = V_IMPOR × KURS (KURS = 1 bila item tanpa seri KURS); basis ADHK = basis ADHB ÷ IH × ĪH; OUT_ADHB = R_MARGIN(t) × basis ADHB × faktor; Output ADHK = R_TD × basis ADHK × faktor | TD2010 G.2 margin barang impor (keputusan 4) |
| `SERI_REFERENSI` | seri = `lk.nilai_seri_referensi` (wilayah yang sama) × faktor; seri belum diisi = kosong | deflator bersama: indeks upah, implisit PMTB, IHPB, IHP, kurs |
| `HASIL_LAPUS` | seri = Σ hasil lapus lain tahap **BENC** (OUT_CP/OUT_K/GVA_CP/GVA_K; IMPLISIT_OUT = ΣOUT_CP ÷ ΣOUT_K × 100) × faktor | tersedia; A.1.e tetap mengikuti LK resmi (keputusan 6) |

Rumus hanya boleh dipilih dari daftar baku (CHECK di DB). Tidak ada ekspresi bebas. Rumus dipasang pada seri sasarannya:
TPK_X_KAMAR → KUANTUM (REV), JANGKAR_X_IH_100 → HARGA (REV), KAPITA/MARGIN → OUT_ADHB (DEF); selain itu ditolak.

Aturan penyelesaian:
- Urutan: masa berlaku item → SERI_REFERENSI → HASIL_LAPUS → RUMUS (urutan baku di atas) → masa berlaku lagi. Seri
  tertaut menggantikan isian manual.
- Nilai rumus pada triwulan t kosong bila semua komponen seri item pada t kosong; komponen kosong lainnya = 0. Hasil
  lapus lain selalu terisi. Output ADHK margin hanya ada pada triwulan yang Output ADHB margin-nya ada.
- R_TD = `R_MARGIN_TD` (parameter item, migrasi 0004) atau, bila kosong dan `jangkar_dari_data`, rata-rata tertimbang
  R pada T₀; TD2010 tanpa parameter = 0. Item margin tetap DEF: NTB ADHB = NTB_ADHB atau (1 − RKA) × output; NTB ADHK =
  (1 − RKA_TD) × Output ADHK. Baris IH item margin barang tidak dipakai.
- Lapus sumber boleh daun, subkategori, kategori, atau kelompok (diurai ke lapus berdata di bawahnya); baris total
  ditolak. Lapus sumber tanpa data bernilai 0.

**Masa berlaku item** (`periode_mulai_id`/`periode_selesai_id`): nilai di luar masa berlaku dianggap tidak ada sebelum
hitung, termasuk untuk jangkar dan rantai EKS. Data overlap item lama tidak terhitung ganda; item yang T₀-nya di luar
masa berlaku wajib berjangkar (V03). Status `nonaktif` tidak menghapus riwayat (tetap dihitung).

## 8. Kompilasi dan tabel pokok (format tetap seperti Excel)

1. Hitung semua lapus berdata (daun, TOP, SOP). Urutan dependensi dibangun dari `lk.tautan_seri` (HASIL_LAPUS,
   MARGIN_X_OUTPUT); siklus ditolak dengan pesan berisi kode lapus. Lapus berdata yang tidak punya item REV/EKS/DEF
   dan tidak punya penyesuaian tidak diberi hasil (baris tabel pokok kosong, bukan 0).
2. Agregasi bottom-up mengikuti `ref.lapus.induk_id` (baris aktif): subkategori = Σ anak; kategori = Σ subkategori,
   untuk tahap BENC dan FINAL.
3. **Kelompok publikasi** (`ref.lapus_kelompok`) = Σ anggota. Kelompok tidak punya item dan tidak menambah total:
   - TD2010: "M,N" = M + N; "R,S,T,U" = R + S + T + U (format publikasi 17 kategori)
   - TD2025: "TUV" = T + U + V (format ekspor LK 02 BPS)
4. Baris total dibaca dari jenis baris master: NTB = Σ akar pohon (kategori/daun tanpa induk); TOP.SOP = Σ TOP − Σ SOP;
   PDRB = NTB + TOP.SOP. TD2025: NTB = Σ kategori A … V; TD2010 (tanpa baris NTB/TOP/SOP): PDRB = Σ kategori A … U.
5. PDRB tanpa migas (kedua tahun dasar, keputusan 7) = PDRB − Σ lapus `is_migas` (lapus berbendera yang tidak punya
   leluhur berbendera, agar tidak terhitung ganda). Seed: TD2010 B.1 + C.1.b; TD2025 B.1 + C.1.2.
6. Tabel turunan per baris pohon (kategori, subkategori, daun, kelompok, total):
   - distribusi = ADHB ÷ PDRB ADHB × 100
   - q-to-q = X(t) ÷ X(t−1) × 100 − 100; y-on-y terhadap X(t−4); c-to-c = Σ T1..t tahun ini ÷ Σ T1..t tahun lalu × 100 − 100
   - implisit = ADHB ÷ ADHK × 100, beserta lajunya
   - SoG q-to-q = (X(t) − X(t−1)) ÷ PDRB(t−1) × 100. Pembagi = **PDRB ADHK**, bukan baris S.3 (temuan T6). SoG y-on-y dan c-to-c dihitung analog.
   - Bila pembagi 0 atau periode pembanding tidak ada, sel dikosongkan.
7. View `lk.v_tabel_pokok` mengembalikan **semua** baris pohon untuk setiap periode, walaupun hasil belum ada. Akibatnya format tabel pokok tetap dan sama dengan Excel, terlepas dari komoditas apa yang dipakai.

## 9. Mode volume

Bawaan FBY (harga konstan tahun dasar, aditif). Modul CVM *one-quarter overlap* disiapkan tetapi tidak aktif sampai ada ketetapan BPS RI (temuan S4).

## 10. Peta asal angka di backend

| Langkah | Tabel baca | Tabel tulis |
|---|---|---|
| Item, data dasar, jangkar | `lk.item`, `lk.nilai_item`, `lk.parameter_item` | — |
| Rumus turunan dan tautan | `lk.tautan_seri`, `lk.nilai_seri_referensi`, `lk.hasil_lapus` | (seri turunan di memori) |
| Hitung item dan metode | data di atas + `lk.penyesuaian` (METODE) | `lk.hasil_item`, `lk.hasil_metode` |
| Rekonsiliasi | `lk.hasil_metode`, `lk.penyesuaian` (REKON) | `lk.hasil_lapus` PRE/POST/BENC |
| Agregasi dan kelompok | `ref.lapus`, `ref.lapus_kelompok` | `lk.hasil_lapus` (semua baris) |
| Simulasi | `lk.hasil_lapus` BENC, `lk.penyesuaian` (SIMULASI) | `lk.hasil_lapus` FINAL |
| Tabel pokok dan dashboard | `lk.v_tabel_pokok` | — |
| Pembanding rilis | `lk.tabel_pokok_rilis` | — |

Setiap baris hasil menyimpan `versi_mesin` dan `hash_input`, sehingga tidak ada langkah "simpan rekonsiliasi" terpisah (temuan T3).

---

## 11. Keputusan metodologi 5 November 2026 (berlaku mulai F2; keputusan 14–17 di F3)

Keputusan berikut dicatat di master/skema (migrasi 0003 dan 0004). Sejak F2, rumusnya sudah diterapkan di mesin
produksi dan `engine_ref`, beserta uji unit dan golden, dan bagian 1–10 di atas sudah memuatnya.

| No | Keputusan | Sudah di master/skema | Diterapkan di |
|---|---|---|---|
| 1 | **TOP/SOP = lapus berisi item**, bukan isian langsung (LK 01 TD2025 juga mencantumkannya di daftar industri). Konsumsi antara = 0, jadi NTB = output. Pajak berbasis nilai (PPN, PBJT, bea masuk): DEF. Cukai dan subsidi per unit (BBM, LPG, listrik, pupuk): REV, volume × tarif atau subsidi per unit tahun dasar. | TOP/SOP boleh punya item dan penugasan | F2 ✓ (KA = 0, agregasi), F3 ✓ (item: + Komoditas, sheet templat `TOP_SOP`) |
| 2 | **V14** tetap memblokir kunci putaran, kecuali admin memberi status `dikecualikan` dengan catatan wajib (agar Put 0 tetap bisa dikunci). | — | F4 |
| 3 | **Jangkar menurut tahun dasar:** `ref.tahun_dasar.jangkar_dari_data` (TD2025 = ya, TD2010 = tidak). Bila tidak: V03 mewajibkan jangkar untuk semua item, dan tahun baseline hanya titik awal rantai EKS, tidak pernah sumber jangkar. Untuk DEF TD2010, `RKA_TD` diambil dari parameter, bukan rasio tahun baseline (perilaku `engine_ref` lama salah untuk TD2010). Templat TD2010 mengisi IH dasar = 100 untuk seri bersatuan "2010=100". | kolom `jangkar_dari_data` | F2 ✓ (`engine_ref` + mesin), F3 ✓ (impor templat: IH "2010=100" tanpa jangkar = 100; V03) |
| 4 | **Margin G.2 (TD2010):** output lapus barang diambil dari tahap **BENC**, bukan FINAL (agar G tidak berubah sendiri saat simulasi lapus lain). ADHB memakai rasio margin triwulan berjalan, ADHK memakai rasio margin tahun dasar. Baris impor memakai rumus baru `MARGIN_X_IMPOR` = R × V_IMPOR (× kurs bila US$) × faktor. | `MARGIN_X_IMPOR`, `R_MARGIN_TD`, seri `KURS` (migrasi 0004) | F2 ✓ |
| 5 | **"Ikut item lain"** (mis. IH IMK ikut IBS, harga ternak) menjadi **seri referensi**; jenis seri referensi menerima `harga`; importer mengonversi otomatis. | `lk.seri_referensi.jenis` `harga`, `lapus_pemilik_id` (0005) | F3 ✓ (seri `REF_<SERI>_<LAPUS>_<METODE><NO>` milik lapus sumber; sumber dan pengikut ditautkan) |
| 6 | **A.1.e** tetap mengikuti LK resmi agar identik dengan LK Put 0. Bila T4 disetujui, perlu kode rumus baru `RASIO_X_HASIL`. | — | — |
| 7 | **PDRB tanpa migas** di kedua tahun dasar = PDRB − Σ NTB lapus `is_migas`, dibaca dari master (bukan kode tetap). | baris `PDRB.NM` TD2025 | F2 ✓ |
| 8 | **Pratinjau adjustment** draf/diajukan di layar LK Hitung, dihitung di layar saja, tidak disimpan, berlabel "PRATINJAU – belum resmi", tidak muncul di tabel pokok/dashboard/ekspor. **Ditegaskan (a): hanya tampilan.** Worker hanya menulis penyesuaian `disetujui` ke `lk.hasil_*`; pratinjau memakai draf/diajukan/disetujui tanpa disimpan. | — | F2 ✓ (mesin/worker), F4 (layar) |
| 9 | **Ambang validasi** dapat diatur per lapus; opsi kalibrasi otomatis ambang = P95 riwayat 2019–2025 (median P95 y-on-y NTB ADHK Put 0 = 11,3%; 12 lapus rutin > 30%). | `ref.validasi.parameter` (0005) | F3 ✓ (lihat keputusan 16) |
| 10 | **Pembanding y-on-y dari rilis TD2010** bila periode pembanding tidak ada di putaran: rilis terbaru yang tanggalnya ≤ tanggal *cut-off* putaran; satu tahun pembanding memakai satu versi rilis (penting untuk c-to-c). Rilis TD2010 tidak pernah menjadi pembanding TD2025. Perlu kolom `tanggal_rilis`, `status_angka`, `tanggal_cutoff`. | — | F4/F5/F6 |
| 11 | **ADHK margin = arus barang:** Output ADHK margin = rasio margin tahun dasar (`R_MARGIN_TD`) × Σ Output ADHK BENC lapus barang × faktor; baris IH item margin barang tidak dipakai. TD2025 tanpa parameter: rata-rata tertimbang R pada T₀. | `lk.parameter_item.kode` + `R_MARGIN_TD` (0004) | F2 ✓ |
| 12 | **ADHK margin impor:** R_TD × (V_IMPOR × KURS ÷ IH × ĪH) × faktor (impor harga konstan dideflasi IH). KURS = seri komponen DEF baru, boleh ditautkan ke seri referensi; item tanpa seri KURS = 1. | `ref.jenis_seri` DEF `KURS` (0004) | F2 ✓ |
| 13 | **Masa berlaku item:** nilai di luar `periode_mulai`–`periode_selesai` dianggap tidak ada sebelum hitung (termasuk jangkar dan rantai EKS). | — | F2 ✓ |
| 14 | **Sambungan item penerus** (`item_asal_id`, docs/04 §3) hanya dicatat; **rumus tidak berubah** dan V03 tetap memblokir item tanpa jangkar. Dialog Sambungkan memberi **usulan jangkar** dari triwulan overlap: H_TD = harga tahun dasar penerus × (harga rata-rata tertimbang item lama ÷ penerus pada overlap); IH_TD = IH tahun dasar penerus × (rata-rata IH lama ÷ penerus pada overlap); RKA_TD = RKA_TD penerus. Operator menyimpannya sebagai parameter beralasan. Overlap < 4 triwulan diberi catatan. | — | F3 ✓ |
| 15 | **Penyesuaian dari templat** (sheet PENYESUAIAN) masuk sebagai **draf**; pemegang izin `penyesuaian.putus` boleh memilih "setujui penyesuaian dari berkas" (tercatat di audit). Nilai yang berubah kembali menjadi draf. Simulasi tidak diimpor. | — | F3 ✓ |
| 16 | **Ambang V08 bawaan:** 30% untuk q-to-q dan y-on-y volume (NTB ADHK) dan implisit NTB. Admin dapat mengubah per lapus (`per_lapus` = `"TD2025:A.3"`) atau menyalakan kalibrasi P95 2019–2025 per lapus (min. 8 titik; ambang = maks(P95, batas bawah), batas bawah = ambang tetap bila `batas_bawah_persen` kosong). V11 bawaan 1%. V06 toleransi 0,5. | `ref.validasi.parameter` (0005) | F3 ✓ |
| 17 | **DEF TD2025 memakai RKA tanpa NTB_ADHB tahun dasar** (RKA_TD terhitung 1 → NTB ADHK = 0) **dijaga validasi**, rumus tidak diubah: V02 (blokir ajukan) meminta NTB_ADHB tahun dasar diisi atau metode diganti. | — | F3 ✓ (V02) |

Aturan teknis F3 (data dasar dan validasi; tidak mengubah rumus, tercatat agar dapat ditinjau):
- Validasi memakai tahap BENC per lapus; V09/V10 (lapus) dan V02/V10 (item) dirangkum per baris (jumlah dan rentang triwulan),
  V01 hanya periode berjalan (`periode_akhir` putaran) dan menghormati sel `tidak_tersedia` (kosong ≠ nol); seri tertaut
  diganti komponen rumusnya; RKA diperiksa V02 (bukan V01); TOP/SOP tanpa RKA. Item PDK tidak divalidasi (tidak dihitung).
- V03 menandai jangkar yang kosong **dan** membuat ADHK/NTB ADHK item 0: REV H_TD (TD2010 selalu; TD2025 bila kuantum T₀
  kosong), EKS/DEF IH_TD (kecuali margin barang), DEF RKA_TD (TD2010 selalu; TD2025 bila output T₀ kosong), margin R_MARGIN_TD.
- V05 membandingkan nama baku (spasi dirapikan, huruf kecil) atau katalog yang sama, beda metode, masa berlaku bertumpang;
  boleh dikonfirmasi beralasan (`lk.konfirmasi_validasi`, bertahan setelah hitung ulang).
- V13 (daun tanpa item dan bukan NIHIL), V14 (TOP/SOP tanpa item), V15 (sidik hasil tersimpan ≠ hitung ulang) memblokir kunci
  putaran; V15 dihitung saat diminta (`GET /api/validasi/kunci`). V16: satuan item ≠ satuan baris KUANTUM, dan satuan berkas ≠
  satuan tersimpan (pratinjau impor).
- Pesan validasi tidak memuat angka PDRB (hanya kode, periode, ambang).

Aturan teknis F2 (konsekuensi rumus, bukan keputusan metodologi baru; tercatat agar dapat ditinjau):
- Triwulan tanpa SIM: FINAL = BENC, juga bila NTB BENC = 0 (rumus proporsi tidak dipakai, sehingga tidak ada pembagian 0 yang mengosongkan output).
- Lapus berdata tanpa item REV/EKS/DEF dan tanpa penyesuaian tidak diberi hasil; agregat tanpa satu pun sumber berdata juga tidak.
- Sumbu hitung = periode putaran diperluas agar mencakup T₀ (rantai EKS dan jangkar); hanya periode putaran yang ditulis.
- Faktor tautan berlaku untuk semua sumber (SERI_REFERENSI, HASIL_LAPUS, RUMUS); bawaan 1.
