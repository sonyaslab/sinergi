-- Seed master SINERGI (Sistem Neraca Ekonomi Regional Terintegrasi) (TD2010/KBLI 2020 + TD2025/KBLI 2025). Dibangkitkan dari scripts/lapus_master.py. Jalankan setelah schema.sql.
BEGIN;
INSERT INTO ref.tahun_dasar (kode, tahun_dasar, status, tahun_awal_seri, klasifikasi, tahun_baseline_eks, keterangan) VALUES
  ('TD2010', 2010, 'produksi', 2010, 'KBLI2020', 2024, 'Produksi berjalan sampai cut-over; lalu arsip (read-only). Kategori A-U, M/N dan R/S/T/U terpisah.'),
  ('TD2025', 2025, 'paralel', 2019, 'KBLI2025', 2025, 'Rebasing; seri 2019Q1 ke depan; Put 0 = backcast. Kategori A-V, T/U/V terpisah (TUV = kelompok ekspor LK 02).');
INSERT INTO ref.periode (tahun, triwulan) SELECT y, q FROM generate_series(2010, 2045) y, generate_series(1, 4) q;
INSERT INTO ref.wilayah (kode, nama, level, induk, urutan) VALUES
  ('6500','Provinsi Kalimantan Utara','provinsi',NULL,0), ('6501','Kabupaten Malinau','kabupaten','6500',1),
  ('6502','Kabupaten Bulungan','kabupaten','6500',2), ('6503','Kabupaten Tana Tidung','kabupaten','6500',3),
  ('6504','Kabupaten Nunukan','kabupaten','6500',4), ('6571','Kota Tarakan','kota','6500',5);
INSERT INTO ref.metode (kode, nama, maks_item, keterangan) VALUES
  ('REV','Revaluasi',100,'Output = kuantum x harga; ADHK = kuantum x harga tahun dasar (jangkar atau rata-rata tertimbang tahun dasar)'),
  ('EKS','Ekstrapolasi',50,'Baseline tahun baseline (ADHB & ADHK) dirantai indeks IP/IB maju dan mundur'),
  ('DEF','Deflasi',50,'ADHK = output ADHB / IH x IH tahun dasar; NTB ADHB input atau (1-RKA) x output'),
  ('PDK','Pendukung',200,'Indikator pendukung; tidak dihitung ke output');
INSERT INTO ref.jenis_seri (metode_kode, kode, nama, wajib, komponen, hanya_td, urutan) VALUES
  ('REV','KUANTUM','Kuantum produksi',true,false,false,1),
  ('REV','HARGA','Harga per satuan',true,false,false,2),
  ('REV','IH','Indeks harga (opsional, harga turunan)',false,false,false,3),
  ('REV','RKA','Rasio konsumsi antara',true,false,false,4),
  ('REV','TPK','Tingkat penghunian kamar (persen)',false,true,false,5),
  ('REV','KAMAR','Jumlah kamar',false,true,false,6),
  ('EKS','INDEKS','Indeks ekstrapolator',true,false,false,1),
  ('EKS','IH','Indeks harga',true,false,false,2),
  ('EKS','BASE_ADHB','Baseline output ADHB',false,false,true,3),
  ('EKS','BASE_ADHK','Baseline output ADHK',false,false,true,4),
  ('EKS','RKA','Rasio konsumsi antara',true,false,false,5),
  ('DEF','OUT_ADHB','Output ADHB',true,false,false,1),
  ('DEF','NTB_ADHB','NTB ADHB',false,false,false,2),
  ('DEF','IH','Indeks harga',true,false,false,3),
  ('DEF','RKA','Rasio konsumsi antara (bila NTB tidak diinput)',false,false,false,4),
  ('DEF','NILAI_KAPITA','Pengeluaran per kapita per bulan',false,true,false,5),
  ('DEF','PENDUDUK','Jumlah penduduk',false,true,false,6),
  ('DEF','VOLUME','Volume (pendukung)',false,true,false,7),
  ('DEF','V_IMPOR','Nilai impor',false,true,false,8),
  ('DEF','R_MARGIN','Rasio margin perdagangan',false,true,false,9),
  ('PDK','NILAI','Nilai indikator',true,false,false,1);
INSERT INTO ref.jenis_penyesuaian (kode, tahap, nama, ubah_angka, wajib_alasan) VALUES
  ('ADJ1','METODE','Penyesuaian cakupan (coverage)',true,true),
  ('ADJ2','METODE','Penyesuaian konseptual',true,true),
  ('SC','METODE','Output sekunder',true,true),
  ('ADJ3','REKON','Rekonsiliasi (pada output, NTB proporsional)',true,true),
  ('ADJ4_OUTPUT','REKON','Benchmarking output',true,true),
  ('ADJ4_NTB','REKON','Benchmarking NTB',true,true),
  ('CT_OUTPUT','REKON','Control total output (pembanding)',false,false),
  ('CT_NTB','REKON','Control total NTB (pembanding)',false,false),
  ('SIM_NTB','SIMULASI','Penyesuaian akhir NTB (ADHK: laju; ADHB: implisit)',true,true);
INSERT INTO ref.satuan (kode, nama) VALUES ('ton','ton'), ('kuintal','kuintal'), ('kg','kg'), ('m3','m3'), ('kWh','kWh'), ('MWh','MWh'), ('ekor','ekor'), ('barel','barel'), ('penumpang','penumpang'), ('unit','unit'), ('persen','persen'), ('kamar','kamar'), ('jiwa','jiwa'), ('indeks','indeks'), ('rasio','rasio'), ('juta Rp','juta Rp'), ('ribu Rp','ribu Rp'), ('Rp','Rp'), ('gram','gram'), ('ribu metrik ton','ribu metrik ton');
INSERT INTO ref.validasi (kode, nama, tingkat) VALUES
  ('V01','Sel wajib periode berjalan kosong','blokir_ajukan'),
  ('V02','RKA tahun dasar / RKA triwulanan kosong saat output > 0','blokir_ajukan'),
  ('V03','Item tanpa jangkar tahun dasar','blokir_ajukan'),
  ('V04','EKS: jenis indeks/baseline/rantai indeks kosong','peringatan'),
  ('V05','Komoditas sama di dua metode pada lapus yang sama','blokir_ajukan'),
  ('V06','Implisit tahunan tahun dasar != 100 +- 0,5','peringatan'),
  ('V07','ADJ ADHB tanpa pasangan ADHK (atau sebaliknya)','peringatan'),
  ('V08','Lonjakan q-to-q / y-on-y melewati ambang','peringatan'),
  ('V09','NTB >= Output atau NTB < 0','peringatan'),
  ('V10','ADHK = 0 sementara ADHB > 0','blokir_ajukan'),
  ('V11','Selisih terhadap control total','info'),
  ('V12','Item EKS tanpa baseline','info'),
  ('V13','Lapus tanpa item dan tanpa status NIHIL','blokir_kunci'),
  ('V14','TOP/SOP kosong saat kunci (TD2025)','blokir_kunci'),
  ('V15','Hasil tersimpan berbeda dari hitung ulang','blokir_kunci'),
  ('V16','Satuan isian berbeda dengan satuan item','peringatan'),
  ('V17','Item berlaku tetapi semua seri wajib kosong pada periode berjalan','peringatan');
-- Pohon lapus TD2010
INSERT INTO ref.lapus (tahun_dasar_id, kode, nama, level, urutan, jenis, is_migas, kode_lk_bps) VALUES
  ((SELECT id FROM ref.tahun_dasar WHERE kode='TD2010'),'A','Pertanian, Kehutanan, dan Perikanan',1,1,'kategori',false,NULL),
  ((SELECT id FROM ref.tahun_dasar WHERE kode='TD2010'),'A.1','Pertanian, Peternakan, Perburuan dan Jasa Pertanian',2,2,'sub',false,NULL),
  ((SELECT id FROM ref.tahun_dasar WHERE kode='TD2010'),'A.1.a','Tanaman Pangan',3,3,'daun',false,NULL),
  ((SELECT id FROM ref.tahun_dasar WHERE kode='TD2010'),'A.1.b','Tanaman Hortikultura Semusim',3,4,'daun',false,NULL),
  ((SELECT id FROM ref.tahun_dasar WHERE kode='TD2010'),'A.1.c','Perkebunan Semusim',3,5,'daun',false,NULL),
  ((SELECT id FROM ref.tahun_dasar WHERE kode='TD2010'),'A.1.d','Tanaman Hortikultura Tahunan dan Lainnya',3,6,'daun',false,NULL),
  ((SELECT id FROM ref.tahun_dasar WHERE kode='TD2010'),'A.1.e','Perkebunan Tahunan',3,7,'daun',false,NULL),
  ((SELECT id FROM ref.tahun_dasar WHERE kode='TD2010'),'A.1.f','Peternakan',3,8,'daun',false,NULL),
  ((SELECT id FROM ref.tahun_dasar WHERE kode='TD2010'),'A.1.g','Jasa Pertanian dan Perburuan',3,9,'daun',false,NULL),
  ((SELECT id FROM ref.tahun_dasar WHERE kode='TD2010'),'A.2','Kehutanan dan Penebangan Kayu',2,10,'daun',false,NULL),
  ((SELECT id FROM ref.tahun_dasar WHERE kode='TD2010'),'A.3','Perikanan',2,11,'daun',false,NULL),
  ((SELECT id FROM ref.tahun_dasar WHERE kode='TD2010'),'B','Pertambangan dan Penggalian',1,12,'kategori',false,NULL),
  ((SELECT id FROM ref.tahun_dasar WHERE kode='TD2010'),'B.1','Pertambangan Minyak, Gas dan Panas Bumi',2,13,'daun',true,NULL),
  ((SELECT id FROM ref.tahun_dasar WHERE kode='TD2010'),'B.2','Pertambangan Batubara dan Lignit',2,14,'daun',false,NULL),
  ((SELECT id FROM ref.tahun_dasar WHERE kode='TD2010'),'B.3','Pertambangan Bijih Logam',2,15,'daun',false,NULL),
  ((SELECT id FROM ref.tahun_dasar WHERE kode='TD2010'),'B.4','Pertambangan dan Penggalian Lainnya',2,16,'daun',false,NULL),
  ((SELECT id FROM ref.tahun_dasar WHERE kode='TD2010'),'C','Industri Pengolahan',1,17,'kategori',false,NULL),
  ((SELECT id FROM ref.tahun_dasar WHERE kode='TD2010'),'C.1','Industri Batubara dan Pengilangan Migas',2,18,'sub',false,NULL),
  ((SELECT id FROM ref.tahun_dasar WHERE kode='TD2010'),'C.1.a','Industri Batu Bara',3,19,'daun',false,NULL),
  ((SELECT id FROM ref.tahun_dasar WHERE kode='TD2010'),'C.1.b','Industri Pengilangan Migas',3,20,'daun',true,NULL),
  ((SELECT id FROM ref.tahun_dasar WHERE kode='TD2010'),'C.2','Industri Makanan dan Minuman',2,21,'daun',false,NULL),
  ((SELECT id FROM ref.tahun_dasar WHERE kode='TD2010'),'C.3','Pengolahan Tembakau',2,22,'daun',false,NULL),
  ((SELECT id FROM ref.tahun_dasar WHERE kode='TD2010'),'C.4','Industri Tekstil dan Pakaian Jadi',2,23,'daun',false,NULL),
  ((SELECT id FROM ref.tahun_dasar WHERE kode='TD2010'),'C.5','Industri Kulit, Barang dari Kulit dan Alas Kaki',2,24,'daun',false,NULL),
  ((SELECT id FROM ref.tahun_dasar WHERE kode='TD2010'),'C.6','Industri Kayu, Barang dari Kayu dan Gabus dan Barang Anyaman',2,25,'daun',false,NULL),
  ((SELECT id FROM ref.tahun_dasar WHERE kode='TD2010'),'C.7','Industri Kertas dan Barang dari Kertas; Percetakan dan Reproduksi Media Rekaman',2,26,'daun',false,NULL),
  ((SELECT id FROM ref.tahun_dasar WHERE kode='TD2010'),'C.8','Industri Kimia, Farmasi dan Obat Tradisional',2,27,'daun',false,NULL),
  ((SELECT id FROM ref.tahun_dasar WHERE kode='TD2010'),'C.9','Industri Karet, Barang dari Karet dan Plastik',2,28,'daun',false,NULL),
  ((SELECT id FROM ref.tahun_dasar WHERE kode='TD2010'),'C.10','Industri Barang Galian bukan Logam',2,29,'daun',false,NULL),
  ((SELECT id FROM ref.tahun_dasar WHERE kode='TD2010'),'C.11','Industri Logam Dasar',2,30,'daun',false,NULL),
  ((SELECT id FROM ref.tahun_dasar WHERE kode='TD2010'),'C.12','Industri Barang Logam; Komputer, Barang Elektronik, Optik; dan Peralatan Listrik',2,31,'daun',false,NULL),
  ((SELECT id FROM ref.tahun_dasar WHERE kode='TD2010'),'C.13','Industri Mesin dan Perlengkapan YTDL',2,32,'daun',false,NULL),
  ((SELECT id FROM ref.tahun_dasar WHERE kode='TD2010'),'C.14','Industri Alat Angkutan',2,33,'daun',false,NULL),
  ((SELECT id FROM ref.tahun_dasar WHERE kode='TD2010'),'C.15','Industri Furnitur',2,34,'daun',false,NULL),
  ((SELECT id FROM ref.tahun_dasar WHERE kode='TD2010'),'C.16','Industri Pengolahan Lainnya; Jasa Reparasi dan Pemasangan Mesin dan Peralatan',2,35,'daun',false,NULL),
  ((SELECT id FROM ref.tahun_dasar WHERE kode='TD2010'),'D','Pengadaan Listrik dan Gas',1,36,'kategori',false,NULL),
  ((SELECT id FROM ref.tahun_dasar WHERE kode='TD2010'),'D.1','Ketenagalistrikan',2,37,'daun',false,NULL),
  ((SELECT id FROM ref.tahun_dasar WHERE kode='TD2010'),'D.2','Pengadaan Gas dan Produksi Es',2,38,'daun',false,NULL),
  ((SELECT id FROM ref.tahun_dasar WHERE kode='TD2010'),'E','Pengadaan Air, Pengelolaan Sampah, Limbah dan Daur Ulang',1,39,'daun',false,NULL),
  ((SELECT id FROM ref.tahun_dasar WHERE kode='TD2010'),'F','Konstruksi',1,40,'daun',false,NULL),
  ((SELECT id FROM ref.tahun_dasar WHERE kode='TD2010'),'G','Perdagangan Besar dan Eceran; Reparasi Mobil dan Sepeda Motor',1,41,'kategori',false,NULL),
  ((SELECT id FROM ref.tahun_dasar WHERE kode='TD2010'),'G.1','Perdagangan Mobil, Sepeda Motor dan Reparasinya',2,42,'daun',false,NULL),
  ((SELECT id FROM ref.tahun_dasar WHERE kode='TD2010'),'G.2','Perdagangan Besar dan Eceran, Bukan Mobil dan Sepeda Motor',2,43,'daun',false,NULL),
  ((SELECT id FROM ref.tahun_dasar WHERE kode='TD2010'),'H','Transportasi dan Pergudangan',1,44,'kategori',false,NULL),
  ((SELECT id FROM ref.tahun_dasar WHERE kode='TD2010'),'H.1','Angkutan Rel',2,45,'daun',false,NULL),
  ((SELECT id FROM ref.tahun_dasar WHERE kode='TD2010'),'H.2','Angkutan Darat',2,46,'daun',false,NULL),
  ((SELECT id FROM ref.tahun_dasar WHERE kode='TD2010'),'H.3','Angkutan Laut',2,47,'daun',false,NULL),
  ((SELECT id FROM ref.tahun_dasar WHERE kode='TD2010'),'H.4','Angkutan Sungai Danau dan Penyeberangan',2,48,'daun',false,NULL),
  ((SELECT id FROM ref.tahun_dasar WHERE kode='TD2010'),'H.5','Angkutan Udara',2,49,'daun',false,NULL),
  ((SELECT id FROM ref.tahun_dasar WHERE kode='TD2010'),'H.6','Pergudangan dan Jasa Penunjang Angkutan; Pos dan Kurir',2,50,'daun',false,NULL),
  ((SELECT id FROM ref.tahun_dasar WHERE kode='TD2010'),'I','Penyediaan Akomodasi dan Makan Minum',1,51,'kategori',false,NULL),
  ((SELECT id FROM ref.tahun_dasar WHERE kode='TD2010'),'I.1','Penyediaan Akomodasi',2,52,'daun',false,NULL),
  ((SELECT id FROM ref.tahun_dasar WHERE kode='TD2010'),'I.2','Penyediaan Makan Minum',2,53,'daun',false,NULL),
  ((SELECT id FROM ref.tahun_dasar WHERE kode='TD2010'),'J','Informasi dan Komunikasi',1,54,'daun',false,NULL),
  ((SELECT id FROM ref.tahun_dasar WHERE kode='TD2010'),'K','Jasa Keuangan dan Asuransi',1,55,'kategori',false,NULL),
  ((SELECT id FROM ref.tahun_dasar WHERE kode='TD2010'),'K.1','Jasa Perantara Keuangan',2,56,'daun',false,NULL),
  ((SELECT id FROM ref.tahun_dasar WHERE kode='TD2010'),'K.2','Asuransi dan Dana Pensiun',2,57,'daun',false,NULL),
  ((SELECT id FROM ref.tahun_dasar WHERE kode='TD2010'),'K.3','Jasa Keuangan Lainnya',2,58,'daun',false,NULL),
  ((SELECT id FROM ref.tahun_dasar WHERE kode='TD2010'),'K.4','Jasa Penunjang Keuangan',2,59,'daun',false,NULL),
  ((SELECT id FROM ref.tahun_dasar WHERE kode='TD2010'),'L','Real Estat',1,60,'daun',false,NULL),
  ((SELECT id FROM ref.tahun_dasar WHERE kode='TD2010'),'M','Aktivitas Profesional, Ilmiah dan Teknis',1,61,'daun',false,NULL),
  ((SELECT id FROM ref.tahun_dasar WHERE kode='TD2010'),'N','Aktivitas Penyewaan, Ketenagakerjaan, Agen Perjalanan dan Penunjang Usaha Lainnya',1,62,'daun',false,NULL),
  ((SELECT id FROM ref.tahun_dasar WHERE kode='TD2010'),'M,N','Jasa Perusahaan (kelompok publikasi 17 kategori)',1,63,'kelompok',false,NULL),
  ((SELECT id FROM ref.tahun_dasar WHERE kode='TD2010'),'O','Administrasi Pemerintahan, Pertahanan dan Jaminan Sosial Wajib',1,64,'daun',false,NULL),
  ((SELECT id FROM ref.tahun_dasar WHERE kode='TD2010'),'P','Jasa Pendidikan',1,65,'daun',false,NULL),
  ((SELECT id FROM ref.tahun_dasar WHERE kode='TD2010'),'Q','Jasa Kesehatan dan Kegiatan Sosial',1,66,'daun',false,NULL),
  ((SELECT id FROM ref.tahun_dasar WHERE kode='TD2010'),'R','Kesenian, Hiburan dan Rekreasi',1,67,'daun',false,NULL),
  ((SELECT id FROM ref.tahun_dasar WHERE kode='TD2010'),'S','Aktivitas Jasa Lainnya',1,68,'daun',false,NULL),
  ((SELECT id FROM ref.tahun_dasar WHERE kode='TD2010'),'T','Aktivitas Rumah Tangga sebagai Pemberi Kerja',1,69,'daun',false,NULL),
  ((SELECT id FROM ref.tahun_dasar WHERE kode='TD2010'),'U','Aktivitas Badan Internasional dan Badan Ekstra Internasional Lainnya',1,70,'daun',false,NULL),
  ((SELECT id FROM ref.tahun_dasar WHERE kode='TD2010'),'R,S,T,U','Jasa Lainnya (kelompok publikasi 17 kategori)',1,71,'kelompok',false,NULL),
  ((SELECT id FROM ref.tahun_dasar WHERE kode='TD2010'),'PDRB','Produk Domestik Regional Bruto',0,72,'pdrb',false,NULL),
  ((SELECT id FROM ref.tahun_dasar WHERE kode='TD2010'),'PDRB.NM','PDRB Tanpa Migas',0,73,'pdrb_nonmigas',false,NULL);
UPDATE ref.lapus c SET induk_id = p.id FROM ref.lapus p, ref.tahun_dasar td
WHERE td.kode='TD2010' AND c.tahun_dasar_id=td.id AND p.tahun_dasar_id=td.id AND p.kode = (CASE
  WHEN c.kode='A.1' THEN 'A'
  WHEN c.kode='A.1.a' THEN 'A.1'
  WHEN c.kode='A.1.b' THEN 'A.1'
  WHEN c.kode='A.1.c' THEN 'A.1'
  WHEN c.kode='A.1.d' THEN 'A.1'
  WHEN c.kode='A.1.e' THEN 'A.1'
  WHEN c.kode='A.1.f' THEN 'A.1'
  WHEN c.kode='A.1.g' THEN 'A.1'
  WHEN c.kode='A.2' THEN 'A'
  WHEN c.kode='A.3' THEN 'A'
  WHEN c.kode='B.1' THEN 'B'
  WHEN c.kode='B.2' THEN 'B'
  WHEN c.kode='B.3' THEN 'B'
  WHEN c.kode='B.4' THEN 'B'
  WHEN c.kode='C.1' THEN 'C'
  WHEN c.kode='C.1.a' THEN 'C.1'
  WHEN c.kode='C.1.b' THEN 'C.1'
  WHEN c.kode='C.2' THEN 'C'
  WHEN c.kode='C.3' THEN 'C'
  WHEN c.kode='C.4' THEN 'C'
  WHEN c.kode='C.5' THEN 'C'
  WHEN c.kode='C.6' THEN 'C'
  WHEN c.kode='C.7' THEN 'C'
  WHEN c.kode='C.8' THEN 'C'
  WHEN c.kode='C.9' THEN 'C'
  WHEN c.kode='C.10' THEN 'C'
  WHEN c.kode='C.11' THEN 'C'
  WHEN c.kode='C.12' THEN 'C'
  WHEN c.kode='C.13' THEN 'C'
  WHEN c.kode='C.14' THEN 'C'
  WHEN c.kode='C.15' THEN 'C'
  WHEN c.kode='C.16' THEN 'C'
  WHEN c.kode='D.1' THEN 'D'
  WHEN c.kode='D.2' THEN 'D'
  WHEN c.kode='G.1' THEN 'G'
  WHEN c.kode='G.2' THEN 'G'
  WHEN c.kode='H.1' THEN 'H'
  WHEN c.kode='H.2' THEN 'H'
  WHEN c.kode='H.3' THEN 'H'
  WHEN c.kode='H.4' THEN 'H'
  WHEN c.kode='H.5' THEN 'H'
  WHEN c.kode='H.6' THEN 'H'
  WHEN c.kode='I.1' THEN 'I'
  WHEN c.kode='I.2' THEN 'I'
  WHEN c.kode='K.1' THEN 'K'
  WHEN c.kode='K.2' THEN 'K'
  WHEN c.kode='K.3' THEN 'K'
  WHEN c.kode='K.4' THEN 'K' END);
INSERT INTO ref.lapus_kelompok (kelompok_id, anggota_id)
SELECT k.id, a.id FROM ref.lapus k JOIN ref.lapus a ON a.tahun_dasar_id = k.tahun_dasar_id
WHERE k.tahun_dasar_id=(SELECT id FROM ref.tahun_dasar WHERE kode='TD2010') AND k.kode='M,N' AND a.kode IN ('M','N');
INSERT INTO ref.lapus_kelompok (kelompok_id, anggota_id)
SELECT k.id, a.id FROM ref.lapus k JOIN ref.lapus a ON a.tahun_dasar_id = k.tahun_dasar_id
WHERE k.tahun_dasar_id=(SELECT id FROM ref.tahun_dasar WHERE kode='TD2010') AND k.kode='R,S,T,U' AND a.kode IN ('R','S','T','U');
-- Pohon lapus TD2025
INSERT INTO ref.lapus (tahun_dasar_id, kode, nama, level, urutan, jenis, is_migas, kode_lk_bps) VALUES
  ((SELECT id FROM ref.tahun_dasar WHERE kode='TD2025'),'A','Pertanian, Kehutanan, dan Perikanan',1,1,'kategori',false,NULL),
  ((SELECT id FROM ref.tahun_dasar WHERE kode='TD2025'),'A.1','Pertanian Tanaman, Peternakan, Perburuan, dan Kegiatan Jasa Terkait',2,2,'sub',false,NULL),
  ((SELECT id FROM ref.tahun_dasar WHERE kode='TD2025'),'A.1.a','Pertanian Tanaman Pangan',3,3,'daun',false,NULL),
  ((SELECT id FROM ref.tahun_dasar WHERE kode='TD2025'),'A.1.b','Pertanian Tanaman Hortikultura',3,4,'daun',false,NULL),
  ((SELECT id FROM ref.tahun_dasar WHERE kode='TD2025'),'A.1.c','Pertanian Tanaman Perkebunan',3,5,'daun',false,NULL),
  ((SELECT id FROM ref.tahun_dasar WHERE kode='TD2025'),'A.1.d','Peternakan',3,6,'daun',false,NULL),
  ((SELECT id FROM ref.tahun_dasar WHERE kode='TD2025'),'A.1.e','Jasa Pertanian dan Perburuan',3,7,'daun',false,NULL),
  ((SELECT id FROM ref.tahun_dasar WHERE kode='TD2025'),'A.2','Pengelolaan Kehutanan dan Pemanenan Kayu',2,8,'daun',false,NULL),
  ((SELECT id FROM ref.tahun_dasar WHERE kode='TD2025'),'A.3','Perikanan',2,9,'daun',false,NULL),
  ((SELECT id FROM ref.tahun_dasar WHERE kode='TD2025'),'B','Pertambangan dan Penggalian',1,10,'kategori',false,NULL),
  ((SELECT id FROM ref.tahun_dasar WHERE kode='TD2025'),'B.1','Pertambangan Minyak Bumi, Gas Alam, dan Panas Bumi',2,11,'daun',true,NULL),
  ((SELECT id FROM ref.tahun_dasar WHERE kode='TD2025'),'B.2','Pertambangan Batu Bara dan Lignit',2,12,'daun',false,NULL),
  ((SELECT id FROM ref.tahun_dasar WHERE kode='TD2025'),'B.3','Pertambangan Bijih Logam',2,13,'daun',false,NULL),
  ((SELECT id FROM ref.tahun_dasar WHERE kode='TD2025'),'B.4','Pertambangan dan Penggalian Lainnya',2,14,'daun',false,NULL),
  ((SELECT id FROM ref.tahun_dasar WHERE kode='TD2025'),'C','Industri',1,15,'kategori',false,NULL),
  ((SELECT id FROM ref.tahun_dasar WHERE kode='TD2025'),'C.1','Industri Produk dari Batu Bara dan Pengilangan Minyak Bumi',2,16,'sub',false,NULL),
  ((SELECT id FROM ref.tahun_dasar WHERE kode='TD2025'),'C.1.1','Industri Produk dari Batu Bara',3,17,'daun',false,NULL),
  ((SELECT id FROM ref.tahun_dasar WHERE kode='TD2025'),'C.1.2','Industri Pengilangan Minyak Bumi',3,18,'daun',true,NULL),
  ((SELECT id FROM ref.tahun_dasar WHERE kode='TD2025'),'C.2','Industri Non Migas',2,19,'sub',false,NULL),
  ((SELECT id FROM ref.tahun_dasar WHERE kode='TD2025'),'C.2.1','Industri Makanan',3,20,'daun',false,NULL),
  ((SELECT id FROM ref.tahun_dasar WHERE kode='TD2025'),'C.2.2','Industri Minuman',3,21,'daun',false,NULL),
  ((SELECT id FROM ref.tahun_dasar WHERE kode='TD2025'),'C.2.3','Industri Produk Tembakau',3,22,'daun',false,NULL),
  ((SELECT id FROM ref.tahun_dasar WHERE kode='TD2025'),'C.2.4','Industri Tekstil',3,23,'daun',false,NULL),
  ((SELECT id FROM ref.tahun_dasar WHERE kode='TD2025'),'C.2.5','Industri Pakaian Jadi dan Perlengkapannya',3,24,'daun',false,NULL),
  ((SELECT id FROM ref.tahun_dasar WHERE kode='TD2025'),'C.2.6','Industri Kulit dan Produk Sejenis',3,25,'daun',false,NULL),
  ((SELECT id FROM ref.tahun_dasar WHERE kode='TD2025'),'C.2.7','Industri Kayu, Barang dari Kayu, dan Sejenisnya',3,26,'daun',false,NULL),
  ((SELECT id FROM ref.tahun_dasar WHERE kode='TD2025'),'C.2.8','Industri Kertas dan Barang dari Kertas',3,27,'daun',false,NULL),
  ((SELECT id FROM ref.tahun_dasar WHERE kode='TD2025'),'C.2.9','Industri Percetakan dan Reproduksi Media Rekaman',3,28,'daun',false,NULL),
  ((SELECT id FROM ref.tahun_dasar WHERE kode='TD2025'),'C.2.10','Industri Bahan Kimia dan Barang dari Bahan Kimia',3,29,'daun',false,NULL),
  ((SELECT id FROM ref.tahun_dasar WHERE kode='TD2025'),'C.2.11','Industri Sediaan Farmasi, Obat Kimia, dan Obat Tradisional',3,30,'daun',false,NULL),
  ((SELECT id FROM ref.tahun_dasar WHERE kode='TD2025'),'C.2.12','Industri Barang dari Karet dan Plastik',3,31,'daun',false,NULL),
  ((SELECT id FROM ref.tahun_dasar WHERE kode='TD2025'),'C.2.13','Industri Produk Mineral Nonlogam',3,32,'daun',false,NULL),
  ((SELECT id FROM ref.tahun_dasar WHERE kode='TD2025'),'C.2.14','Industri Logam Dasar',3,33,'daun',false,NULL),
  ((SELECT id FROM ref.tahun_dasar WHERE kode='TD2025'),'C.2.15','Industri Produk Logam Pabrikasi Bukan Mesin dan Peralatannya',3,34,'daun',false,NULL),
  ((SELECT id FROM ref.tahun_dasar WHERE kode='TD2025'),'C.2.16','Industri Produk Komputer, Elektronik, dan Optik',3,35,'daun',false,NULL),
  ((SELECT id FROM ref.tahun_dasar WHERE kode='TD2025'),'C.2.17','Industri Peralatan Listrik',3,36,'daun',false,NULL),
  ((SELECT id FROM ref.tahun_dasar WHERE kode='TD2025'),'C.2.18','Industri Mesin dan Perlengkapan YTDL',3,37,'daun',false,NULL),
  ((SELECT id FROM ref.tahun_dasar WHERE kode='TD2025'),'C.2.19','Industri Kendaraan Bermotor dan Alat Angkutan Lainnya',3,38,'daun',false,NULL),
  ((SELECT id FROM ref.tahun_dasar WHERE kode='TD2025'),'C.2.20','Industri Furnitur',3,39,'daun',false,NULL),
  ((SELECT id FROM ref.tahun_dasar WHERE kode='TD2025'),'C.2.21','Industri Produk Lainnya',3,40,'daun',false,NULL),
  ((SELECT id FROM ref.tahun_dasar WHERE kode='TD2025'),'C.2.22','Reparasi, Pemeliharaan, dan Pemasangan Mesin dan Peralatan',3,41,'daun',false,NULL),
  ((SELECT id FROM ref.tahun_dasar WHERE kode='TD2025'),'D','Penyediaan Listrik, Gas, Uap/Air Panas, dan Udara Dingin',1,42,'kategori',false,NULL),
  ((SELECT id FROM ref.tahun_dasar WHERE kode='TD2025'),'D.1','Penyediaan Listrik',2,43,'daun',false,NULL),
  ((SELECT id FROM ref.tahun_dasar WHERE kode='TD2025'),'D.2','Penyediaan Gas, Uap/Air Panas, dan Udara Dingin',2,44,'daun',false,NULL),
  ((SELECT id FROM ref.tahun_dasar WHERE kode='TD2025'),'E','Penyediaan Air, Pengelolaan Limbah, Penanganan Limbah dan Remediasi',1,45,'kategori',false,NULL),
  ((SELECT id FROM ref.tahun_dasar WHERE kode='TD2025'),'E.1','Penyediaan Air',2,46,'daun',false,NULL),
  ((SELECT id FROM ref.tahun_dasar WHERE kode='TD2025'),'E.2','Pengelolaan Limbah dan Aktivitas Remediasi',2,47,'sub',false,NULL),
  ((SELECT id FROM ref.tahun_dasar WHERE kode='TD2025'),'E.2.a','Pengelolaan Limbah dan Aktivitas Remediasi Pemerintah',3,48,'daun',false,NULL),
  ((SELECT id FROM ref.tahun_dasar WHERE kode='TD2025'),'E.2.b','Pengelolaan Limbah dan Aktivitas Remediasi Swasta',3,49,'daun',false,NULL),
  ((SELECT id FROM ref.tahun_dasar WHERE kode='TD2025'),'F','Konstruksi',1,50,'daun',false,NULL),
  ((SELECT id FROM ref.tahun_dasar WHERE kode='TD2025'),'G','Perdagangan Besar dan Eceran',1,51,'kategori',false,NULL),
  ((SELECT id FROM ref.tahun_dasar WHERE kode='TD2025'),'G.1','Perdagangan Besar',2,52,'daun',false,NULL),
  ((SELECT id FROM ref.tahun_dasar WHERE kode='TD2025'),'G.2','Perdagangan Eceran',2,53,'daun',false,NULL),
  ((SELECT id FROM ref.tahun_dasar WHERE kode='TD2025'),'H','Transportasi dan Penyimpanan',1,54,'kategori',false,NULL),
  ((SELECT id FROM ref.tahun_dasar WHERE kode='TD2025'),'H.1','Transportasi Kereta Api',2,55,'daun',false,NULL),
  ((SELECT id FROM ref.tahun_dasar WHERE kode='TD2025'),'H.2','Transportasi Jalan dan Transportasi melalui Saluran Pipa',2,56,'daun',false,NULL),
  ((SELECT id FROM ref.tahun_dasar WHERE kode='TD2025'),'H.3','Transportasi Perairan',2,57,'sub',false,NULL),
  ((SELECT id FROM ref.tahun_dasar WHERE kode='TD2025'),'H.3.a','Angkutan Laut',3,58,'daun',false,NULL),
  ((SELECT id FROM ref.tahun_dasar WHERE kode='TD2025'),'H.3.b','Angkutan Sungai, Danau, dan Penyeberangan (ASDP)',3,59,'daun',false,NULL),
  ((SELECT id FROM ref.tahun_dasar WHERE kode='TD2025'),'H.4','Transportasi Udara',2,60,'daun',false,NULL),
  ((SELECT id FROM ref.tahun_dasar WHERE kode='TD2025'),'H.5','Pergudangan dan Penunjang Transportasi',2,61,'daun',false,NULL),
  ((SELECT id FROM ref.tahun_dasar WHERE kode='TD2025'),'H.6','Aktivitas Pos dan Kurir',2,62,'daun',false,NULL),
  ((SELECT id FROM ref.tahun_dasar WHERE kode='TD2025'),'I','Penyediaan Akomodasi dan Makan Minum',1,63,'kategori',false,NULL),
  ((SELECT id FROM ref.tahun_dasar WHERE kode='TD2025'),'I.1','Penyediaan Akomodasi',2,64,'daun',false,NULL),
  ((SELECT id FROM ref.tahun_dasar WHERE kode='TD2025'),'I.2','Penyediaan Makanan dan Minuman',2,65,'daun',false,NULL),
  ((SELECT id FROM ref.tahun_dasar WHERE kode='TD2025'),'J','Penerbitan, Penyiaran, serta Produksi dan Distribusi Konten',1,66,'kategori',false,NULL),
  ((SELECT id FROM ref.tahun_dasar WHERE kode='TD2025'),'J.1','Penerbitan, Penyiaran, serta Produksi dan Distribusi Konten Pemerintah',2,67,'daun',false,NULL),
  ((SELECT id FROM ref.tahun_dasar WHERE kode='TD2025'),'J.2','Penerbitan, Penyiaran, serta Produksi dan Distribusi Konten Swasta',2,68,'daun',false,NULL),
  ((SELECT id FROM ref.tahun_dasar WHERE kode='TD2025'),'K','Telekomunikasi, Pemrograman Komputer, Konsultasi, Infrastruktur Komputasi, dan Informasi Lainnya',1,69,'daun',false,NULL),
  ((SELECT id FROM ref.tahun_dasar WHERE kode='TD2025'),'L','Jasa Keuangan dan Asuransi',1,70,'kategori',false,NULL),
  ((SELECT id FROM ref.tahun_dasar WHERE kode='TD2025'),'L.1','Aktivitas Intermediasi Keuangan',2,71,'daun',false,NULL),
  ((SELECT id FROM ref.tahun_dasar WHERE kode='TD2025'),'L.2','Aktivitas Keuangan Lainnya, Kecuali Asuransi dan Dana Pensiun',2,72,'daun',false,NULL),
  ((SELECT id FROM ref.tahun_dasar WHERE kode='TD2025'),'L.3','Aktivitas Asuransi, Reasuransi, Penjaminan, dan Dana Pensiun',2,73,'daun',false,NULL),
  ((SELECT id FROM ref.tahun_dasar WHERE kode='TD2025'),'L.4','Aktivitas Penunjang Keuangan',2,74,'daun',false,NULL),
  ((SELECT id FROM ref.tahun_dasar WHERE kode='TD2025'),'M','Real Estat',1,75,'daun',false,NULL),
  ((SELECT id FROM ref.tahun_dasar WHERE kode='TD2025'),'N','Aktivitas Profesional, Ilmiah, dan Teknis',1,76,'daun',false,NULL),
  ((SELECT id FROM ref.tahun_dasar WHERE kode='TD2025'),'O','Aktivitas Administratif dan Penunjang Usaha',1,77,'daun',false,NULL),
  ((SELECT id FROM ref.tahun_dasar WHERE kode='TD2025'),'P','Administrasi Pemerintahan dan Pertahanan; Jaminan Sosial Wajib',1,78,'daun',false,NULL),
  ((SELECT id FROM ref.tahun_dasar WHERE kode='TD2025'),'Q','Pendidikan',1,79,'kategori',false,NULL),
  ((SELECT id FROM ref.tahun_dasar WHERE kode='TD2025'),'Q.1','Pendidikan Pemerintah',2,80,'daun',false,NULL),
  ((SELECT id FROM ref.tahun_dasar WHERE kode='TD2025'),'Q.2','Pendidikan Swasta Market',2,81,'daun',false,NULL),
  ((SELECT id FROM ref.tahun_dasar WHERE kode='TD2025'),'Q.3','Pendidikan Swasta Nonmarket',2,82,'daun',false,NULL),
  ((SELECT id FROM ref.tahun_dasar WHERE kode='TD2025'),'R','Aktivitas Kesehatan dan Sosial',1,83,'kategori',false,NULL),
  ((SELECT id FROM ref.tahun_dasar WHERE kode='TD2025'),'R.1','Aktivitas Kesehatan Pemerintah',2,84,'daun',false,NULL),
  ((SELECT id FROM ref.tahun_dasar WHERE kode='TD2025'),'R.2','Aktivitas Kesehatan Swasta Market',2,85,'daun',false,NULL),
  ((SELECT id FROM ref.tahun_dasar WHERE kode='TD2025'),'R.3','Aktivitas Kesehatan Swasta Nonmarket',2,86,'daun',false,NULL),
  ((SELECT id FROM ref.tahun_dasar WHERE kode='TD2025'),'S','Aktivitas Kesenian, Olahraga, dan Rekreasi',1,87,'kategori',false,NULL),
  ((SELECT id FROM ref.tahun_dasar WHERE kode='TD2025'),'S.1','Aktivitas Kesenian, Olahraga dan Rekreasi Pemerintah',2,88,'daun',false,NULL),
  ((SELECT id FROM ref.tahun_dasar WHERE kode='TD2025'),'S.2','Aktivitas Kesenian, Olahraga dan Rekreasi Lainnya Swasta Market',2,89,'daun',false,NULL),
  ((SELECT id FROM ref.tahun_dasar WHERE kode='TD2025'),'S.3','Aktivitas Kesenian, Olahraga dan Rekreasi Lainnya Swasta Nonmarket',2,90,'daun',false,NULL),
  ((SELECT id FROM ref.tahun_dasar WHERE kode='TD2025'),'T','Aktivitas Jasa Lainnya',1,91,'kategori',false,NULL),
  ((SELECT id FROM ref.tahun_dasar WHERE kode='TD2025'),'T.1','Aktivitas Jasa Lainnya Swasta Market',2,92,'daun',false,'TUV.1'),
  ((SELECT id FROM ref.tahun_dasar WHERE kode='TD2025'),'T.2','Aktivitas Jasa Lainnya Swasta Nonmarket',2,93,'daun',false,'TUV.2'),
  ((SELECT id FROM ref.tahun_dasar WHERE kode='TD2025'),'U','Aktivitas Rumah Tangga sebagai Pemberi Kerja dan Produksi untuk Keperluan Sendiri',1,94,'daun',false,'TUV.3'),
  ((SELECT id FROM ref.tahun_dasar WHERE kode='TD2025'),'V','Aktivitas Badan Internasional dan Badan Ekstra Internasional Lainnya',1,95,'daun',false,NULL),
  ((SELECT id FROM ref.tahun_dasar WHERE kode='TD2025'),'TUV','Aktivitas Lainnya (kelompok format LK 02 BPS)',1,96,'kelompok',false,NULL),
  ((SELECT id FROM ref.tahun_dasar WHERE kode='TD2025'),'NTB','Nilai Tambah Bruto atas Harga Dasar',0,97,'ntb',false,NULL),
  ((SELECT id FROM ref.tahun_dasar WHERE kode='TD2025'),'TOP','Pajak atas Produk',0,98,'top',false,NULL),
  ((SELECT id FROM ref.tahun_dasar WHERE kode='TD2025'),'SOP','Subsidi atas Produk',0,99,'sop',false,NULL),
  ((SELECT id FROM ref.tahun_dasar WHERE kode='TD2025'),'TOP.SOP','Pajak dikurangi Subsidi atas Produk',0,100,'topsop',false,NULL),
  ((SELECT id FROM ref.tahun_dasar WHERE kode='TD2025'),'PDRB','Produk Domestik Regional Bruto',0,101,'pdrb',false,NULL);
UPDATE ref.lapus c SET induk_id = p.id FROM ref.lapus p, ref.tahun_dasar td
WHERE td.kode='TD2025' AND c.tahun_dasar_id=td.id AND p.tahun_dasar_id=td.id AND p.kode = (CASE
  WHEN c.kode='A.1' THEN 'A'
  WHEN c.kode='A.1.a' THEN 'A.1'
  WHEN c.kode='A.1.b' THEN 'A.1'
  WHEN c.kode='A.1.c' THEN 'A.1'
  WHEN c.kode='A.1.d' THEN 'A.1'
  WHEN c.kode='A.1.e' THEN 'A.1'
  WHEN c.kode='A.2' THEN 'A'
  WHEN c.kode='A.3' THEN 'A'
  WHEN c.kode='B.1' THEN 'B'
  WHEN c.kode='B.2' THEN 'B'
  WHEN c.kode='B.3' THEN 'B'
  WHEN c.kode='B.4' THEN 'B'
  WHEN c.kode='C.1' THEN 'C'
  WHEN c.kode='C.1.1' THEN 'C.1'
  WHEN c.kode='C.1.2' THEN 'C.1'
  WHEN c.kode='C.2' THEN 'C'
  WHEN c.kode='C.2.1' THEN 'C.2'
  WHEN c.kode='C.2.2' THEN 'C.2'
  WHEN c.kode='C.2.3' THEN 'C.2'
  WHEN c.kode='C.2.4' THEN 'C.2'
  WHEN c.kode='C.2.5' THEN 'C.2'
  WHEN c.kode='C.2.6' THEN 'C.2'
  WHEN c.kode='C.2.7' THEN 'C.2'
  WHEN c.kode='C.2.8' THEN 'C.2'
  WHEN c.kode='C.2.9' THEN 'C.2'
  WHEN c.kode='C.2.10' THEN 'C.2'
  WHEN c.kode='C.2.11' THEN 'C.2'
  WHEN c.kode='C.2.12' THEN 'C.2'
  WHEN c.kode='C.2.13' THEN 'C.2'
  WHEN c.kode='C.2.14' THEN 'C.2'
  WHEN c.kode='C.2.15' THEN 'C.2'
  WHEN c.kode='C.2.16' THEN 'C.2'
  WHEN c.kode='C.2.17' THEN 'C.2'
  WHEN c.kode='C.2.18' THEN 'C.2'
  WHEN c.kode='C.2.19' THEN 'C.2'
  WHEN c.kode='C.2.20' THEN 'C.2'
  WHEN c.kode='C.2.21' THEN 'C.2'
  WHEN c.kode='C.2.22' THEN 'C.2'
  WHEN c.kode='D.1' THEN 'D'
  WHEN c.kode='D.2' THEN 'D'
  WHEN c.kode='E.1' THEN 'E'
  WHEN c.kode='E.2' THEN 'E'
  WHEN c.kode='E.2.a' THEN 'E.2'
  WHEN c.kode='E.2.b' THEN 'E.2'
  WHEN c.kode='G.1' THEN 'G'
  WHEN c.kode='G.2' THEN 'G'
  WHEN c.kode='H.1' THEN 'H'
  WHEN c.kode='H.2' THEN 'H'
  WHEN c.kode='H.3' THEN 'H'
  WHEN c.kode='H.3.a' THEN 'H.3'
  WHEN c.kode='H.3.b' THEN 'H.3'
  WHEN c.kode='H.4' THEN 'H'
  WHEN c.kode='H.5' THEN 'H'
  WHEN c.kode='H.6' THEN 'H'
  WHEN c.kode='I.1' THEN 'I'
  WHEN c.kode='I.2' THEN 'I'
  WHEN c.kode='J.1' THEN 'J'
  WHEN c.kode='J.2' THEN 'J'
  WHEN c.kode='L.1' THEN 'L'
  WHEN c.kode='L.2' THEN 'L'
  WHEN c.kode='L.3' THEN 'L'
  WHEN c.kode='L.4' THEN 'L'
  WHEN c.kode='Q.1' THEN 'Q'
  WHEN c.kode='Q.2' THEN 'Q'
  WHEN c.kode='Q.3' THEN 'Q'
  WHEN c.kode='R.1' THEN 'R'
  WHEN c.kode='R.2' THEN 'R'
  WHEN c.kode='R.3' THEN 'R'
  WHEN c.kode='S.1' THEN 'S'
  WHEN c.kode='S.2' THEN 'S'
  WHEN c.kode='S.3' THEN 'S'
  WHEN c.kode='T.1' THEN 'T'
  WHEN c.kode='T.2' THEN 'T' END);
INSERT INTO ref.lapus_kelompok (kelompok_id, anggota_id)
SELECT k.id, a.id FROM ref.lapus k JOIN ref.lapus a ON a.tahun_dasar_id = k.tahun_dasar_id
WHERE k.tahun_dasar_id=(SELECT id FROM ref.tahun_dasar WHERE kode='TD2025') AND k.kode='TUV' AND a.kode IN ('T','U','V');
-- Konkordansi TD2010 (KBLI 2020) -> TD2025 (KBLI 2025); bobot diisi dari SUT/SE2026 bila 1:N
INSERT INTO ref.konkordansi_lapus (lapus_asal_id, lapus_tujuan_id, bobot, catatan)
SELECT a.id, b.id, x.bobot, x.ket FROM (VALUES
  ('A.1.a','A.1.a',1::numeric,NULL),
  ('A.1.b','A.1.b',1::numeric,'Hortikultura semusim'),
  ('A.1.d','A.1.b',1::numeric,'Hortikultura tahunan'),
  ('A.1.c','A.1.c',1::numeric,'Perkebunan semusim'),
  ('A.1.e','A.1.c',1::numeric,'Perkebunan tahunan'),
  ('A.1.f','A.1.d',1::numeric,NULL),
  ('A.1.g','A.1.e',1::numeric,NULL),
  ('A.2','A.2',1::numeric,NULL),
  ('A.3','A.3',1::numeric,NULL),
  ('B.1','B.1',1::numeric,NULL),
  ('B.2','B.2',1::numeric,NULL),
  ('B.3','B.3',1::numeric,NULL),
  ('B.4','B.4',1::numeric,NULL),
  ('C.1.a','C.1.1',1::numeric,NULL),
  ('C.1.b','C.1.2',1::numeric,'LNG dan pengilangan'),
  ('C.2','C.2.1',NULL::numeric,'KBLI 10'),
  ('C.2','C.2.2',NULL::numeric,'KBLI 11'),
  ('C.3','C.2.3',1::numeric,'KBLI 12'),
  ('C.4','C.2.4',NULL::numeric,'KBLI 13'),
  ('C.4','C.2.5',NULL::numeric,'KBLI 14'),
  ('C.5','C.2.6',1::numeric,'KBLI 15'),
  ('C.6','C.2.7',1::numeric,'KBLI 16'),
  ('C.7','C.2.8',NULL::numeric,'KBLI 17'),
  ('C.7','C.2.9',NULL::numeric,'KBLI 18'),
  ('C.8','C.2.10',NULL::numeric,'KBLI 20'),
  ('C.8','C.2.11',NULL::numeric,'KBLI 21'),
  ('C.9','C.2.12',1::numeric,'KBLI 22'),
  ('C.10','C.2.13',1::numeric,'KBLI 23'),
  ('C.11','C.2.14',1::numeric,'KBLI 24'),
  ('C.12','C.2.15',NULL::numeric,'KBLI 25'),
  ('C.12','C.2.16',NULL::numeric,'KBLI 26'),
  ('C.12','C.2.17',NULL::numeric,'KBLI 27'),
  ('C.13','C.2.18',1::numeric,'KBLI 28'),
  ('C.14','C.2.19',1::numeric,'KBLI 29-30'),
  ('C.15','C.2.20',1::numeric,'KBLI 31'),
  ('C.16','C.2.21',NULL::numeric,'KBLI 32'),
  ('C.16','C.2.22',NULL::numeric,'KBLI 33'),
  ('D.1','D.1',1::numeric,NULL),
  ('D.2','D.2',1::numeric,'Gas; produksi es ikut D.2'),
  ('E','E.1',NULL::numeric,'Penyediaan air'),
  ('E','E.2.a',NULL::numeric,'Limbah pemerintah'),
  ('E','E.2.b',NULL::numeric,'Limbah swasta'),
  ('F','F',1::numeric,NULL),
  ('G.1','G.1',NULL::numeric,'Perdagangan besar kendaraan'),
  ('G.1','G.2',NULL::numeric,'Eceran kendaraan'),
  ('G.1','T.1',NULL::numeric,'Reparasi mobil/motor pindah ke T di KBLI 2025'),
  ('G.2','G.1',NULL::numeric,'Perdagangan besar'),
  ('G.2','G.2',NULL::numeric,'Perdagangan eceran'),
  ('H.1','H.1',1::numeric,NULL),
  ('H.2','H.2',1::numeric,NULL),
  ('H.3','H.3.a',1::numeric,NULL),
  ('H.4','H.3.b',1::numeric,NULL),
  ('H.5','H.4',1::numeric,NULL),
  ('H.6','H.5',NULL::numeric,'Pergudangan, penunjang'),
  ('H.6','H.6',NULL::numeric,'Pos dan kurir'),
  ('I.1','I.1',1::numeric,NULL),
  ('I.2','I.2',1::numeric,NULL),
  ('J','J.1',NULL::numeric,'Penerbitan/penyiaran pemerintah'),
  ('J','J.2',NULL::numeric,'Penerbitan/penyiaran swasta'),
  ('J','K',NULL::numeric,'Telekomunikasi, pemrograman, jasa informasi'),
  ('K.1','L.1',1::numeric,NULL),
  ('K.2','L.3',1::numeric,NULL),
  ('K.3','L.2',1::numeric,NULL),
  ('K.4','L.4',1::numeric,NULL),
  ('L','M',1::numeric,NULL),
  ('M','N',1::numeric,NULL),
  ('N','O',1::numeric,NULL),
  ('O','P',1::numeric,NULL),
  ('P','Q.1',NULL::numeric,'Pemerintah'),
  ('P','Q.2',NULL::numeric,'Swasta market'),
  ('P','Q.3',NULL::numeric,'Swasta nonmarket'),
  ('Q','R.1',NULL::numeric,'Pemerintah'),
  ('Q','R.2',NULL::numeric,'Swasta market'),
  ('Q','R.3',NULL::numeric,'Swasta nonmarket'),
  ('R','S.1',NULL::numeric,'Pemerintah'),
  ('R','S.2',NULL::numeric,'Swasta market'),
  ('R','S.3',NULL::numeric,'Swasta nonmarket'),
  ('S','T.1',NULL::numeric,'Swasta market'),
  ('S','T.2',NULL::numeric,'Organisasi nirlaba'),
  ('T','U',1::numeric,'Rumah tangga'),
  ('U','V',1::numeric,'Badan internasional')
) AS x(asal, tujuan, bobot, ket)
JOIN ref.lapus a ON a.kode = x.asal AND a.tahun_dasar_id = (SELECT id FROM ref.tahun_dasar WHERE kode='TD2010')
JOIN ref.lapus b ON b.kode = x.tujuan AND b.tahun_dasar_id = (SELECT id FROM ref.tahun_dasar WHERE kode='TD2025');
INSERT INTO sec.peran (kode, nama) VALUES ('admin','Administrator'), ('operator','Operator'), ('supervisor','Supervisor (pimpinan)'), ('auditor','Auditor (baca saja)');
INSERT INTO sec.izin (kode, nama) VALUES ('master.kelola','master.kelola'), ('pengguna.kelola','pengguna.kelola'), ('putaran.kelola','putaran.kelola'), ('putaran.kunci','putaran.kunci'), ('putaran.buka_kunci','putaran.buka_kunci'), ('data_dasar.isi','data_dasar.isi'), ('data_dasar.impor','data_dasar.impor'), ('item.tambah','item.tambah'), ('metode.pilih','metode.pilih'), ('biaya_antara.isi','biaya_antara.isi'), ('penyesuaian.usul','penyesuaian.usul'), ('penyesuaian.putus','penyesuaian.putus'), ('lk.ajukan','lk.ajukan'), ('lk.setujui','lk.setujui'), ('simulasi.edit','simulasi.edit'), ('tabel_pokok.lihat','tabel_pokok.lihat'), ('dashboard.lihat','dashboard.lihat'), ('ekspor.tabel_pokok','ekspor.tabel_pokok'), ('audit.lihat','audit.lihat'), ('data.tulis_semua','data.tulis_semua'), ('rilis.impor','rilis.impor');
INSERT INTO sec.peran_izin (peran_id, izin_kode) SELECT p.id, x.iz FROM (VALUES
  ('admin','master.kelola'),
  ('admin','pengguna.kelola'),
  ('admin','putaran.kelola'),
  ('admin','putaran.kunci'),
  ('admin','putaran.buka_kunci'),
  ('admin','data_dasar.isi'),
  ('admin','data_dasar.impor'),
  ('admin','item.tambah'),
  ('admin','metode.pilih'),
  ('admin','biaya_antara.isi'),
  ('admin','penyesuaian.usul'),
  ('admin','penyesuaian.putus'),
  ('admin','lk.ajukan'),
  ('admin','lk.setujui'),
  ('admin','simulasi.edit'),
  ('admin','tabel_pokok.lihat'),
  ('admin','dashboard.lihat'),
  ('admin','ekspor.tabel_pokok'),
  ('admin','audit.lihat'),
  ('admin','data.tulis_semua'),
  ('admin','rilis.impor'),
  ('operator','data_dasar.isi'),
  ('operator','data_dasar.impor'),
  ('operator','item.tambah'),
  ('operator','metode.pilih'),
  ('operator','biaya_antara.isi'),
  ('operator','penyesuaian.usul'),
  ('operator','lk.ajukan'),
  ('operator','tabel_pokok.lihat'),
  ('operator','dashboard.lihat'),
  ('supervisor','penyesuaian.putus'),
  ('supervisor','lk.setujui'),
  ('supervisor','putaran.kunci'),
  ('supervisor','simulasi.edit'),
  ('supervisor','tabel_pokok.lihat'),
  ('supervisor','dashboard.lihat'),
  ('supervisor','ekspor.tabel_pokok'),
  ('supervisor','audit.lihat'),
  ('auditor','tabel_pokok.lihat'),
  ('auditor','dashboard.lihat'),
  ('auditor','audit.lihat')
) AS x(peran, iz) JOIN sec.peran p ON p.kode = x.peran;
INSERT INTO sec.pengguna (username, nama, password_hash, wajib_ganti_sandi, aktif) VALUES ('sistem.worker', 'Worker hitung otomatis', '!disabled', false, true);
COMMIT;
