# Rumus Mesin Hitung SINERGI (versi 4)

Spesifikasi wajib mesin hitung. Untuk TD2025, rumus ini identik dengan LK Excel resmi "01 LK PDRB Triwulanan TD2025 v.1.0" dan "02 LK Kompilasi PDRB TD 2025 v.1.0". Kesamaan diuji dengan `engine_ref/lk_engine.py` atas data Kaltara Put 0:

- 71 dari 72 lapus identik dengan hasil simpan LK. B.3 berbeda karena hasil simpannya usang.
- Templat terisi yang diimpor kembali menghasilkan angka identik untuk 72/72 lapus.

TD2010 memakai mesin yang sama. Bedanya ada pada **jangkar tahun dasar** (bagian 2) dan **rumus turunan** (bagian 7).

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

| Jangkar | Bila diisi (`lk.parameter_item`) | Bila kosong (bawaan TD2025) |
|---|---|---|
| H̄ (REV) | `H_TD` (TD2010: harga 2010) | Σ₍T₀₎ Output ADHB ÷ Σ₍T₀₎ kuantum |
| ĪH (EKS, DEF) | `IH_TD` (TD2010: 100) | rata-rata IH pada T₀ |
| RKA_TD (REV, EKS) | `RKA_TD` — **wajib** | — (kosong = 0, diblokir validasi V02) |
| RKA_TD (DEF) | dipakai hanya bila tidak ada data T₀ | 1 − Σ₍T₀₎ NTB ADHB ÷ Σ₍T₀₎ Output ADHB |

Item tanpa data tahun dasar wajib diberi jangkar (V03). Contohnya spesies ikan 2019–2021, emas 2019–2022, dan aluminium 2026. Tanpa jangkar, ADHK item tersebut menjadi 0 (temuan K3).

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
2. NTB ADHB = NTB_ADHB bila diisi. Bila kosong: (1 − RKA(t)) × Output ADHB; jika RKA(t) juga kosong, pakai RKA_TD. Ini pola TD2010, misalnya belanja pegawai O/P/Q dengan RKA_TD = 0.
3. Output ADHK = Output ADHB ÷ IH(t) × ĪH
4. NTB ADHK = (1 − RKA_TD) × Output ADHK

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

**Tahap SIMULASI** (per lapus daun × triwulan; izin `simulasi.edit`):
- NTB ADHK final = NTB ADHK kompilasi + SIM (ADHK); NTB ADHB final = NTB ADHB kompilasi + SIM (ADHB)
- Output final ikut proporsi NTB: Output.SIM = Output × NTB.SIM ÷ NTB
- Bantuan input: "target laju y-on-y" → adj = NTB(t−4) × (1 + g/100) − NTB kompilasi; "target implisit" → adj = target implisit × NTB ADHK ÷ 100 − NTB ADHB

Semua penyesuaian wajib beralasan (min. 10 karakter) dan hanya status `disetujui` yang masuk angka final.

## 7. Rumus turunan dan tautan (`lk.tautan_seri`)

Seri yang tidak diketik operator, tetapi diselesaikan sistem sebelum langkah 1:

| Kode rumus | Rumus | Dipakai |
|---|---|---|
| `TPK_X_KAMAR` | KUANTUM = TPK (persen) × KAMAR | I.1 hotel (sama dengan LK TD2025: 35,99 × 375 = 13.496,25) |
| `JANGKAR_X_IH_100` | HARGA = H_TD × IH ÷ 100 | TD2010 hortikultura A.1.b, A.1.d |
| `KAPITA_X_PENDUDUK_X_3` | OUT_ADHB = per kapita × penduduk × 3 ÷ 10⁶ × faktor | TD2010 I.1 sewa, I.2 makan minum (faktor 0,8865) |
| `MARGIN_X_OUTPUT` | OUT_ADHB = R_MARGIN × Σ Output ADHB lapus barang (+ impor) | TD2010 G.2 arus komoditas |
| `SERI_REFERENSI` | seri diambil dari `lk.nilai_seri_referensi` (satu seri untuk banyak item) | deflator bersama: indeks upah, implisit PMTB, IHPB, IHP |
| `HASIL_LAPUS` | seri = Σ hasil lapus lain (OUT_CP/OUT_K/GVA_CP/GVA_K/IMPLISIT_OUT) × faktor | A.1.e jasa pertanian ← A.1.a–A.1.d (usulan T4) |

Rumus hanya boleh dipilih dari daftar baku (CHECK di DB). Tidak ada ekspresi bebas.

## 8. Kompilasi dan tabel pokok (format tetap seperti Excel)

1. Hitung semua lapus daun. Urutan dependensi dibangun dari `lk.tautan_seri` (HASIL_LAPUS, MARGIN); siklus ditolak.
2. Agregasi bottom-up mengikuti `ref.lapus.induk_id`: subkategori = Σ daun; kategori = Σ subkategori.
3. **Kelompok publikasi** (`ref.lapus_kelompok`) = Σ anggota. Kelompok tidak punya item dan tidak menambah total:
   - TD2010: "M,N" = M + N; "R,S,T,U" = R + S + T + U (format publikasi 17 kategori)
   - TD2025: "TUV" = T + U + V (format ekspor LK 02 BPS)
4. TD2025: NTB = Σ kategori A … V; TOP.SOP = TOP − SOP; PDRB = NTB + TOP.SOP
5. TD2010: PDRB = Σ kategori A … U; PDRB tanpa migas = PDRB − (B.1 + C.1.b)
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
