-- Uji asap skema (jalankan pada basis data uji kosong setelah schema.sql + seed_ref.sql).
\set ON_ERROR_STOP 1
BEGIN;
DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='app_test') THEN
  CREATE ROLE app_test LOGIN PASSWORD 'uji' IN ROLE app_rw; END IF; END $$;
INSERT INTO sec.pengguna (username, nama, password_hash) VALUES ('op.a','Operator A','x'),('op.b','Operator B','x'),('sup','Supervisor','x');
INSERT INTO sec.pengguna_peran SELECT u.id, p.id FROM sec.pengguna u, sec.peran p
 WHERE (u.username,p.kode) IN (('op.a','operator'),('op.b','operator'),('sup','supervisor'));
INSERT INTO lk.putaran (tahun_dasar_id, tahun, triwulan, nomor, nama, jenis, status, periode_awal_id, periode_akhir_id)
SELECT td.id, 2026, 2, 0, 'Put 0', 'BACKCAST', 'terbuka',
       (SELECT id FROM ref.periode WHERE tahun=2019 AND triwulan=1), (SELECT id FROM ref.periode WHERE tahun=2026 AND triwulan=2)
FROM ref.tahun_dasar td WHERE td.kode='TD2025';
INSERT INTO lk.penugasan (pengguna_id, tahun_dasar_id, wilayah_kode, lapus_id, peran_tugas)
SELECT u.id, l.tahun_dasar_id, '6500', l.id, 'operator' FROM sec.pengguna u, ref.lapus l
WHERE u.username='op.a' AND l.kode='A.1.a' AND l.tahun_dasar_id=(SELECT id FROM ref.tahun_dasar WHERE kode='TD2025');
COMMIT;

GRANT app_rw TO app_test;
SET ROLE app_test;

-- 1) Operator A boleh menambah item di A.1.a
BEGIN;
SELECT set_config('app.user_id', (SELECT id::text FROM sec.pengguna WHERE username='op.a'), true);
INSERT INTO lk.item (tahun_dasar_id, wilayah_kode, lapus_id, metode_kode, nomor, nama, satuan_kode, alasan)
SELECT l.tahun_dasar_id, '6500', l.id, 'REV', 1, 'Padi', 'ton', 'uji' FROM ref.lapus l
WHERE l.kode='A.1.a' AND l.tahun_dasar_id=(SELECT id FROM ref.tahun_dasar WHERE kode='TD2025');
INSERT INTO lk.nilai_item (putaran_id, item_id, jenis_seri, periode_id, nilai)
SELECT (SELECT id FROM lk.putaran LIMIT 1), (SELECT id FROM lk.item WHERE nama='Padi'), 'KUANTUM', p.id, 1000
FROM ref.periode p WHERE p.tahun=2025;
COMMIT;
\echo 'OK 1: operator menulis lapus yang ditugaskan'

-- 2) Operator B ditolak RLS
BEGIN;
SELECT set_config('app.user_id', (SELECT id::text FROM sec.pengguna WHERE username='op.b'), true);
DO $$ BEGIN
  INSERT INTO lk.nilai_item (putaran_id, item_id, jenis_seri, periode_id, nilai)
  SELECT (SELECT id FROM lk.putaran LIMIT 1), (SELECT id FROM lk.item WHERE nama='Padi'), 'HARGA', p.id, 5 FROM ref.periode p WHERE p.tahun=2025;
  RAISE EXCEPTION 'GAGAL: RLS tidak menolak';
EXCEPTION WHEN insufficient_privilege THEN RAISE NOTICE 'OK 2: RLS menolak operator lain';
END $$;
COMMIT;

-- 3) EKS wajib jenis indeks; nomor melebihi batas ditolak
BEGIN;
SELECT set_config('app.user_id', (SELECT id::text FROM sec.pengguna WHERE username='op.a'), true);
DO $$ BEGIN
  INSERT INTO lk.item (tahun_dasar_id, wilayah_kode, lapus_id, metode_kode, nomor, nama)
  SELECT l.tahun_dasar_id, '6500', l.id, 'EKS', 1, 'Indeks X' FROM ref.lapus l WHERE l.kode='A.1.a' AND l.tahun_dasar_id=2;
  RAISE EXCEPTION 'GAGAL: EKS tanpa jenis indeks diterima';
EXCEPTION WHEN check_violation THEN RAISE NOTICE 'OK 3a: EKS wajib jenis indeks'; END $$;
DO $$ BEGIN
  INSERT INTO lk.item (tahun_dasar_id, wilayah_kode, lapus_id, metode_kode, nomor, nama)
  SELECT l.tahun_dasar_id, '6500', l.id, 'DEF', 51, 'Item 51' FROM ref.lapus l WHERE l.kode='A.1.a' AND l.tahun_dasar_id=2;
  RAISE EXCEPTION 'GAGAL: nomor 51 DEF diterima';
EXCEPTION WHEN check_violation THEN RAISE NOTICE 'OK 3b: batas 50 item DEF'; END $$;
COMMIT;

-- 4) Penyesuaian wajib alasan
BEGIN;
SELECT set_config('app.user_id', (SELECT id::text FROM sec.pengguna WHERE username='op.a'), true);
DO $$ BEGIN
  INSERT INTO lk.penyesuaian (putaran_id, wilayah_kode, lapus_id, tahap, metode_kode, jenis_kode, harga, periode_id, nilai, alasan)
  SELECT (SELECT id FROM lk.putaran LIMIT 1), '6500', l.id, 'METODE', 'REV', 'ADJ1', 'CP', (SELECT id FROM ref.periode WHERE tahun=2025 AND triwulan=1), 10, 'x'
  FROM ref.lapus l WHERE l.kode='A.1.a' AND l.tahun_dasar_id=2;
  RAISE EXCEPTION 'GAGAL: alasan pendek diterima';
EXCEPTION WHEN check_violation THEN RAISE NOTICE 'OK 4: alasan penyesuaian wajib'; END $$;
COMMIT;

RESET ROLE;
-- 4b) Tabel pokok menampilkan seluruh pohon lapus (format tetap) walau hasil belum ada
DO $$ DECLARE n int; m int; BEGIN
  SELECT count(*) INTO n FROM lk.v_tabel_pokok v WHERE v.wilayah_kode='6500' AND v.tahun=2025 AND v.triwulan=1;
  SELECT count(*) INTO m FROM ref.lapus WHERE tahun_dasar_id=(SELECT id FROM ref.tahun_dasar WHERE kode='TD2025');
  IF n <> m THEN RAISE EXCEPTION 'GAGAL: baris tabel pokok % <> lapus %', n, m; END IF;
  RAISE NOTICE 'OK 4b: tabel pokok % baris (kategori sampai subkategori, NTB, TOP/SOP, PDRB)', n;
END $$;

-- 4c) Item PDK boleh sampai 200; tautan RUMUS harus dari daftar
BEGIN;
SELECT set_config('app.user_id', (SELECT id::text FROM sec.pengguna WHERE username='op.a'), true);
INSERT INTO lk.item (tahun_dasar_id, wilayah_kode, lapus_id, metode_kode, nomor, nama, alasan)
SELECT l.tahun_dasar_id, '6500', l.id, 'PDK', 150, 'Indikator pendukung', 'uji' FROM ref.lapus l WHERE l.kode='A.1.a' AND l.tahun_dasar_id=2;
DO $$ BEGIN
  INSERT INTO lk.tautan_seri (item_id, jenis_seri, sumber, rumus) VALUES ((SELECT id FROM lk.item WHERE nama='Padi'), 'HARGA', 'RUMUS', 'BEBAS_SQL');
  RAISE EXCEPTION 'GAGAL: rumus bebas diterima';
EXCEPTION WHEN check_violation THEN RAISE NOTICE 'OK 4c: rumus turunan hanya dari daftar baku'; END $$;
COMMIT;

-- 5) Kunci putaran -> tulis ditolak (P0423)
UPDATE lk.putaran SET status='terkunci';
SET ROLE app_test;
BEGIN;
SELECT set_config('app.user_id', (SELECT id::text FROM sec.pengguna WHERE username='op.a'), true);
DO $$ BEGIN
  UPDATE lk.nilai_item SET nilai = 2000;
  RAISE EXCEPTION 'GAGAL: putaran terkunci bisa diubah';
EXCEPTION WHEN SQLSTATE 'P0423' THEN RAISE NOTICE 'OK 5: putaran terkunci menolak tulis'; END $$;
COMMIT;

-- 6) Audit append-only dan berantai
DO $$ BEGIN
  DELETE FROM audit.log;
  RAISE EXCEPTION 'GAGAL: audit dapat dihapus';
EXCEPTION WHEN insufficient_privilege THEN RAISE NOTICE 'OK 6a: audit tidak dapat dihapus'; END $$;
RESET ROLE;
DO $$ DECLARE n int; BEGIN
  SELECT count(*) INTO n FROM (SELECT hash_sebelum, lag(hash) OVER (ORDER BY id) AS prev FROM audit.log) x
   WHERE x.prev IS NOT NULL AND x.hash_sebelum IS DISTINCT FROM x.prev;
  IF n > 0 THEN RAISE EXCEPTION 'GAGAL: rantai hash audit putus (%)', n; END IF;
  RAISE NOTICE 'OK 6b: rantai hash audit utuh';
END $$;