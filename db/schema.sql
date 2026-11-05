-- =====================================================================
-- SINERGI (Sistem Neraca Ekonomi Regional Terintegrasi) — skema basis data (PostgreSQL 16)
-- Versi 4 (+ migrasi Alembic s.d. 0003) — mendukung TD2010/KBLI 2020 (produksi berjalan) dan TD2025/KBLI 2025 (rebasing),
-- kategori M,N dan R,S,T,U(,V) terpisah + kelompok publikasi; komoditas dinamis per triwulan;
-- seri 2010–2045, item dinamis per wilayah/lapus/metode, rasio KA per item,
-- adjustment 3 tingkat (METODE, REKON, SIMULASI), multi-operator, audit.
--
-- Konvensi:
--   * Skema: ref (master), lk (perhitungan), sec (akses), audit (jejak).
--   * Nilai angka: NUMERIC tanpa batas presisi (mesin hitung float64,
--     disimpan presisi penuh; dibulatkan hanya saat tampil/ekspor).
--   * Aplikasi menyetel konteks per transaksi:
--       SET LOCAL app.user_id = '<id>';  SET LOCAL app.ip = '<ip>';
--   * Peran DB: app_owner (DDL, migrasi), app_rw (aplikasi), app_ro (laporan).
--     Buat peran-peran ini lebih dulu (lihat bagian akhir) atau jalankan
--     skrip ini sebagai app_owner.
-- =====================================================================

CREATE SCHEMA IF NOT EXISTS ext;
CREATE EXTENSION IF NOT EXISTS pgcrypto SCHEMA ext;

CREATE SCHEMA IF NOT EXISTS ref;
CREATE SCHEMA IF NOT EXISTS lk;
CREATE SCHEMA IF NOT EXISTS sec;
CREATE SCHEMA IF NOT EXISTS audit;

-- ---------------------------------------------------------------------
-- Fungsi bantu konteks
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION sec.uid() RETURNS bigint
LANGUAGE sql STABLE AS $$
  SELECT NULLIF(current_setting('app.user_id', true), '')::bigint
$$;

-- =====================================================================
-- SEC — pengguna, peran, izin
-- =====================================================================
CREATE TABLE sec.pengguna (
  id               bigserial PRIMARY KEY,
  username         text NOT NULL UNIQUE CHECK (username ~ '^[a-z0-9._-]{3,40}$'),
  nama             text NOT NULL,
  email            text UNIQUE,
  nip              text,
  password_hash    text NOT NULL,                 -- Argon2id
  totp_secret_enc  bytea,                         -- terenkripsi (Fernet) di aplikasi
  totp_aktif       boolean NOT NULL DEFAULT false,
  wajib_ganti_sandi boolean NOT NULL DEFAULT true,
  aktif            boolean NOT NULL DEFAULT true,
  gagal_login      smallint NOT NULL DEFAULT 0,
  terkunci_sampai  timestamptz,
  terakhir_login   timestamptz,
  dibuat_pada      timestamptz NOT NULL DEFAULT now(),
  diubah_pada      timestamptz NOT NULL DEFAULT now(),
  totp_langkah_terakhir bigint                    -- migrasi 0002: kode TOTP tidak boleh dipakai ulang
);
COMMENT ON COLUMN sec.pengguna.totp_langkah_terakhir IS 'Langkah waktu (unix/30) kode TOTP terakhir yang diterima; kode dengan langkah <= ini ditolak';

CREATE TABLE sec.peran (
  id    smallserial PRIMARY KEY,
  kode  text NOT NULL UNIQUE,          -- admin, operator, supervisor, pimpinan, auditor
  nama  text NOT NULL,
  aktif boolean NOT NULL DEFAULT true  -- migrasi 0003: peran nonaktif tidak memberi izin
);

CREATE TABLE sec.izin (
  kode  text PRIMARY KEY,              -- mis. data_dasar.isi, putaran.kunci
  nama  text NOT NULL
);

CREATE TABLE sec.peran_izin (
  peran_id  smallint NOT NULL REFERENCES sec.peran(id) ON DELETE CASCADE,
  izin_kode text     NOT NULL REFERENCES sec.izin(kode) ON DELETE CASCADE,
  PRIMARY KEY (peran_id, izin_kode)
);

CREATE TABLE sec.pengguna_peran (
  pengguna_id bigint   NOT NULL REFERENCES sec.pengguna(id) ON DELETE CASCADE,
  peran_id    smallint NOT NULL REFERENCES sec.peran(id) ON DELETE CASCADE,
  PRIMARY KEY (pengguna_id, peran_id)
);

CREATE TABLE sec.sesi (
  id            uuid PRIMARY KEY DEFAULT ext.gen_random_uuid(),
  pengguna_id   bigint NOT NULL REFERENCES sec.pengguna(id) ON DELETE CASCADE,
  refresh_hash  text NOT NULL,                    -- SHA-256 token refresh (bukan token mentah)
  dibuat_pada   timestamptz NOT NULL DEFAULT now(),
  aktif_terakhir timestamptz NOT NULL DEFAULT now(),
  kedaluwarsa   timestamptz NOT NULL,
  ip            inet,
  ua_hash       text,
  dicabut       boolean NOT NULL DEFAULT false
);
CREATE INDEX ON sec.sesi (pengguna_id) WHERE NOT dicabut;

CREATE OR REPLACE FUNCTION sec.punya_izin(p_izin text) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = sec, pg_temp AS $$
  SELECT EXISTS (
    SELECT 1 FROM sec.pengguna_peran pp
    JOIN sec.peran pr ON pr.id = pp.peran_id AND pr.aktif
    JOIN sec.peran_izin pi ON pi.peran_id = pp.peran_id
    JOIN sec.pengguna u ON u.id = pp.pengguna_id AND u.aktif
    WHERE pp.pengguna_id = sec.uid() AND pi.izin_kode = p_izin)
$$;

-- =====================================================================
-- REF — master
-- =====================================================================
CREATE TABLE ref.tahun_dasar (
  id              smallserial PRIMARY KEY,
  kode            text NOT NULL UNIQUE,                 -- TD2010, TD2025
  tahun_dasar     smallint NOT NULL,
  status          text NOT NULL CHECK (status IN ('rencana','paralel','produksi','arsip')),
  tahun_awal_seri smallint NOT NULL,
  klasifikasi     text NOT NULL CHECK (klasifikasi IN ('KBLI2020','KBLI2025')),
  tahun_baseline_eks smallint NOT NULL,           -- TD2025: 2025; TD2010: tahun rilis terakhir (mis. 2024)
  keterangan      text,
  jangkar_dari_data boolean NOT NULL DEFAULT true -- migrasi 0003: TD2025 true; TD2010 false (jangkar wajib diisi)
);
COMMENT ON COLUMN ref.tahun_dasar.jangkar_dari_data IS 'true: jangkar (H_TD/IH_TD/RKA_TD DEF) boleh dihitung dari data tahun baseline bila kosong (TD2025); false: jangkar wajib diisi (TD2010, V03)';

CREATE TABLE ref.periode (
  id        serial PRIMARY KEY,
  tahun     smallint NOT NULL CHECK (tahun BETWEEN 2000 AND 2100),
  triwulan  smallint NOT NULL CHECK (triwulan BETWEEN 1 AND 4),
  urut      integer GENERATED ALWAYS AS (tahun * 4 + triwulan - 1) STORED,
  label     text    GENERATED ALWAYS AS ('Q' || triwulan || '-' || tahun) STORED,
  UNIQUE (tahun, triwulan),
  UNIQUE (urut)
);

CREATE TABLE ref.wilayah (
  kode   char(4) PRIMARY KEY,
  nama   text NOT NULL,
  level  text NOT NULL CHECK (level IN ('provinsi','kabupaten','kota')),
  induk  char(4) REFERENCES ref.wilayah(kode),
  urutan smallint NOT NULL DEFAULT 0,
  aktif  boolean NOT NULL DEFAULT true
);

CREATE TABLE ref.lapus (
  id              serial PRIMARY KEY,
  tahun_dasar_id  smallint NOT NULL REFERENCES ref.tahun_dasar(id),
  kode            text NOT NULL,
  nama            text NOT NULL,
  induk_id        integer REFERENCES ref.lapus(id),
  level           smallint NOT NULL CHECK (level BETWEEN 0 AND 4),
  urutan          integer NOT NULL,                    -- urutan baris tabel pokok (tetap, sama dengan Excel)
  jenis           text NOT NULL CHECK (jenis IN ('kategori','sub','daun','kelompok','ntb','top','sop','topsop','pdrb','pdrb_nonmigas')),
  kode_lk_bps     text,                                -- kode di LK 02 BPS bila berbeda (mis. T.1 -> TUV.1)
  is_migas        boolean NOT NULL DEFAULT false,
  aktif           boolean NOT NULL DEFAULT true,
  UNIQUE (tahun_dasar_id, kode),
  UNIQUE (tahun_dasar_id, urutan)
);
-- Kelompok publikasi: baris gabungan yang hanya dijumlahkan (M,N; R,S,T,U; TUV). Tidak punya item.
CREATE TABLE ref.lapus_kelompok (
  kelompok_id integer NOT NULL REFERENCES ref.lapus(id) ON DELETE CASCADE,
  anggota_id  integer NOT NULL REFERENCES ref.lapus(id) ON DELETE CASCADE,
  PRIMARY KEY (kelompok_id, anggota_id)
);

COMMENT ON TABLE ref.lapus IS 'Pohon lapangan usaha per tahun dasar. Format tabel pokok TETAP mengikuti urutan ini; item data dasar tidak mengubah baris.';

CREATE TABLE ref.konkordansi_lapus (
  id               serial PRIMARY KEY,
  lapus_asal_id    integer NOT NULL REFERENCES ref.lapus(id),   -- TD2010
  lapus_tujuan_id  integer NOT NULL REFERENCES ref.lapus(id),   -- TD2025
  bobot            numeric CHECK (bobot IS NULL OR (bobot >= 0 AND bobot <= 1)),
  catatan          text,
  UNIQUE (lapus_asal_id, lapus_tujuan_id)
);

CREATE TABLE ref.metode (
  kode      text PRIMARY KEY CHECK (kode IN ('REV','EKS','DEF','PDK')),
  nama      text NOT NULL,
  maks_item smallint NOT NULL,
  keterangan text
);

CREATE TABLE ref.jenis_seri (
  metode_kode text NOT NULL REFERENCES ref.metode(kode),
  kode        text NOT NULL,          -- REV: KUANTUM,HARGA,IH,RKA | EKS: INDEKS,IH,BASE_ADHB,BASE_ADHK,RKA | DEF: OUT_ADHB,NTB_ADHB,IH,RKA | PDK: NILAI | komponen
  nama        text NOT NULL,
  wajib       boolean NOT NULL DEFAULT false,
  komponen    boolean NOT NULL DEFAULT false,   -- seri bantu untuk rumus turunan (TPK, KAMAR, NILAI_KAPITA, ...)
  hanya_td    boolean NOT NULL DEFAULT false,   -- true: hanya diisi pada 4 triwulan tahun baseline
  urutan      smallint NOT NULL,
  PRIMARY KEY (metode_kode, kode)
);

CREATE TABLE ref.jenis_penyesuaian (
  kode        text PRIMARY KEY,       -- ADJ1, ADJ2, SC, ADJ3, ADJ4_OUT, ADJ4_NTB, CT_OUT, CT_NTB, SIM_NTB
  tahap       text NOT NULL CHECK (tahap IN ('METODE','REKON','SIMULASI')),
  nama        text NOT NULL,
  ubah_angka  boolean NOT NULL DEFAULT true,  -- false untuk CT (pembanding)
  wajib_alasan boolean NOT NULL DEFAULT true
);

CREATE TABLE ref.satuan (
  kode  text PRIMARY KEY,
  nama  text NOT NULL,
  aktif boolean NOT NULL DEFAULT true
);

CREATE TABLE ref.sumber_data (
  id        serial PRIMARY KEY,
  nama      text NOT NULL UNIQUE,
  instansi  text,
  keterangan text,
  aktif     boolean NOT NULL DEFAULT true
);

CREATE TABLE ref.katalog_komoditas (
  id          serial PRIMARY KEY,
  nama_baku   text NOT NULL UNIQUE,
  sinonim     text[] NOT NULL DEFAULT '{}',
  satuan_kode text REFERENCES ref.satuan(kode),
  kbli        text,
  catatan     text,
  aktif       boolean NOT NULL DEFAULT true
);

CREATE TABLE ref.validasi (
  kode       text PRIMARY KEY,         -- V01..V15
  nama       text NOT NULL,
  tingkat    text NOT NULL CHECK (tingkat IN ('info','peringatan','blokir_ajukan','blokir_kunci')),
  parameter  jsonb NOT NULL DEFAULT '{}',
  aktif      boolean NOT NULL DEFAULT true
);

-- =====================================================================
-- LK — putaran, penugasan, item, data dasar, penyesuaian, hasil
-- =====================================================================
CREATE TABLE lk.putaran (
  id                bigserial PRIMARY KEY,
  tahun_dasar_id    smallint NOT NULL REFERENCES ref.tahun_dasar(id),
  tahun             smallint NOT NULL,
  triwulan          smallint NOT NULL CHECK (triwulan BETWEEN 1 AND 4),
  nomor             smallint NOT NULL DEFAULT 1,
  nama              text NOT NULL,                       -- mis. "Put 0", "Putaran 1", "Rilis"
  jenis             text NOT NULL CHECK (jenis IN ('BACKCAST','REGULER','REVISI','RILIS')),
  status            text NOT NULL DEFAULT 'draf' CHECK (status IN ('draf','terbuka','ditutup','terkunci')),
  periode_awal_id   integer NOT NULL REFERENCES ref.periode(id),   -- awal seri yang boleh diubah
  periode_akhir_id  integer NOT NULL REFERENCES ref.periode(id),   -- triwulan berjalan
  sumber_putaran_id bigint REFERENCES lk.putaran(id),
  mode_volume       text NOT NULL DEFAULT 'FBY' CHECK (mode_volume IN ('FBY','CVM_QOM')),
  dibuka_oleh       bigint REFERENCES sec.pengguna(id),
  dibuka_pada       timestamptz,
  dikunci_oleh      bigint REFERENCES sec.pengguna(id),
  dikunci_pada      timestamptz,
  catatan           text,
  UNIQUE (tahun_dasar_id, tahun, triwulan, nomor)
);

CREATE TABLE lk.penugasan (
  id              bigserial PRIMARY KEY,
  pengguna_id     bigint   NOT NULL REFERENCES sec.pengguna(id) ON DELETE CASCADE,
  tahun_dasar_id  smallint NOT NULL REFERENCES ref.tahun_dasar(id),
  wilayah_kode    char(4)  NOT NULL REFERENCES ref.wilayah(kode),
  lapus_id        integer  NOT NULL REFERENCES ref.lapus(id),
  peran_tugas     text     NOT NULL CHECK (peran_tugas IN ('operator','pemeriksa')),
  berlaku_mulai   date NOT NULL DEFAULT current_date,
  berlaku_sampai  date,
  UNIQUE (pengguna_id, tahun_dasar_id, wilayah_kode, lapus_id, peran_tugas)
);
CREATE INDEX ON lk.penugasan (wilayah_kode, lapus_id);

-- Item = satu baris rincian/komoditas dalam satu lapus-wilayah-metode.
-- Operator dapat MENAMBAH item kapan saja (komoditas berbeda per triwulan sesuai ketersediaan).
CREATE TABLE lk.item (
  id                 bigserial PRIMARY KEY,
  tahun_dasar_id     smallint NOT NULL REFERENCES ref.tahun_dasar(id),
  wilayah_kode       char(4)  NOT NULL REFERENCES ref.wilayah(kode),
  lapus_id           integer  NOT NULL REFERENCES ref.lapus(id),
  metode_kode        text     NOT NULL REFERENCES ref.metode(kode),
  nomor              smallint NOT NULL CHECK (nomor BETWEEN 1 AND 200),
  katalog_id         integer REFERENCES ref.katalog_komoditas(id),
  nama               text NOT NULL CHECK (length(trim(nama)) > 0),
  satuan_kode        text REFERENCES ref.satuan(kode),
  sumber_id          integer REFERENCES ref.sumber_data(id),
  sumber_teks        text,
  keterangan         text,
  jenis_indeks       text CHECK (jenis_indeks IN ('IP','IB')),     -- wajib untuk EKS
  bobot              numeric,                                        -- EKS: hanya indeks agregat tampilan
  periode_mulai_id   integer REFERENCES ref.periode(id),             -- komoditas dinamis: berlaku mulai triwulan ini
  periode_selesai_id integer REFERENCES ref.periode(id),             -- ... sampai triwulan ini (NULL = masih berlaku)
  lapus_padanan_id   integer REFERENCES ref.lapus(id),               -- lapus di tahun dasar lain (konkordansi item, untuk rebasing)
  item_asal_id       bigint  REFERENCES lk.item(id),                 -- item yang diganti/disambung (overlap rebasing)
  status             text NOT NULL DEFAULT 'aktif' CHECK (status IN ('aktif','nonaktif')),
  dibuat_putaran_id  bigint REFERENCES lk.putaran(id),
  dibuat_oleh        bigint REFERENCES sec.pengguna(id),
  dibuat_pada        timestamptz NOT NULL DEFAULT now(),
  alasan             text,
  UNIQUE (tahun_dasar_id, wilayah_kode, lapus_id, metode_kode, nomor),
  CHECK (metode_kode <> 'EKS' OR jenis_indeks IS NOT NULL)
);
CREATE INDEX ON lk.item (wilayah_kode, lapus_id, metode_kode) WHERE status = 'aktif';

-- Batas jumlah item per metode (REV 100, EKS 50, DEF 50 — mengikuti LK).
CREATE OR REPLACE FUNCTION lk.cek_maks_item() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE v_maks smallint;
BEGIN
  SELECT maks_item INTO v_maks FROM ref.metode WHERE kode = NEW.metode_kode;
  IF NEW.nomor > v_maks THEN
    RAISE EXCEPTION 'Nomor item % melebihi batas % untuk metode %', NEW.nomor, v_maks, NEW.metode_kode
      USING ERRCODE = 'check_violation';
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER trg_item_maks BEFORE INSERT OR UPDATE ON lk.item
  FOR EACH ROW EXECUTE FUNCTION lk.cek_maks_item();

-- Nilai data dasar per item per seri per periode, terikat putaran.
CREATE TABLE lk.nilai_item (
  putaran_id  bigint  NOT NULL REFERENCES lk.putaran(id) ON DELETE CASCADE,
  item_id     bigint  NOT NULL REFERENCES lk.item(id),
  jenis_seri  text    NOT NULL,
  periode_id  integer NOT NULL REFERENCES ref.periode(id),
  nilai       numeric,
  status_sel  text NOT NULL DEFAULT 'isi' CHECK (status_sel IN ('isi','tidak_tersedia','belum')),
  catatan     text,
  diubah_oleh bigint REFERENCES sec.pengguna(id),
  diubah_pada timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (putaran_id, item_id, jenis_seri, periode_id),
  CHECK (status_sel <> 'isi' OR nilai IS NOT NULL)
);
CREATE INDEX ON lk.nilai_item (item_id, jenis_seri);

-- Parameter skalar per item: RKA_TD (rasio KA tahun dasar), H_TD / IH_TD (jangkar tahun dasar pengganti).
CREATE TABLE lk.parameter_item (
  putaran_id bigint NOT NULL REFERENCES lk.putaran(id) ON DELETE CASCADE,
  item_id    bigint NOT NULL REFERENCES lk.item(id),
  kode       text   NOT NULL CHECK (kode IN ('RKA_TD','H_TD','IH_TD','R_MARGIN_TD')),  -- R_MARGIN_TD: migrasi 0004
  nilai      numeric NOT NULL,
  alasan     text,
  diubah_oleh bigint REFERENCES sec.pengguna(id),
  diubah_pada timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (putaran_id, item_id, kode),
  CHECK (kode IN ('RKA_TD','R_MARGIN_TD') OR alasan IS NOT NULL)  -- jangkar pengganti wajib beralasan; rasio tahun dasar tidak
);

-- LK Biaya Antara tahun dasar (hasil SE2026/SUT). Rasio dihitung otomatis lalu diterapkan ke RKA_TD item.
CREATE TABLE lk.struktur_biaya (
  id               bigserial PRIMARY KEY,
  tahun_dasar_id   smallint NOT NULL REFERENCES ref.tahun_dasar(id),
  wilayah_kode     char(4)  NOT NULL REFERENCES ref.wilayah(kode),
  lapus_id         integer  NOT NULL REFERENCES ref.lapus(id),
  item_id          bigint   REFERENCES lk.item(id),          -- NULL = berlaku untuk seluruh lapus
  output           numeric  CHECK (output IS NULL OR output >= 0),
  ba_bahan numeric, ba_energi numeric, ba_jasa numeric, ba_sewa numeric, ba_lainnya numeric,
  ba_total_langsung numeric,                                 -- diisi bila rincian tidak tersedia
  total_ba         numeric GENERATED ALWAYS AS (COALESCE(NULLIF(COALESCE(ba_bahan,0)+COALESCE(ba_energi,0)+COALESCE(ba_jasa,0)
                                                 +COALESCE(ba_sewa,0)+COALESCE(ba_lainnya,0),0), ba_total_langsung)) STORED,
  rasio_ka         numeric GENERATED ALWAYS AS (CASE WHEN output > 0 THEN COALESCE(NULLIF(COALESCE(ba_bahan,0)+COALESCE(ba_energi,0)
                                                 +COALESCE(ba_jasa,0)+COALESCE(ba_sewa,0)+COALESCE(ba_lainnya,0),0), ba_total_langsung) / output END) STORED,
  sumber           text NOT NULL DEFAULT 'SE2026',
  status           text NOT NULL DEFAULT 'draf' CHECK (status IN ('draf','disetujui')),
  diubah_oleh      bigint REFERENCES sec.pengguna(id),
  diubah_pada      timestamptz NOT NULL DEFAULT now(),
  UNIQUE NULLS NOT DISTINCT (tahun_dasar_id, wilayah_kode, lapus_id, item_id)
);
COMMENT ON TABLE lk.struktur_biaya IS 'Format LK Biaya Antara. Tombol "Terapkan" menyalin rasio_ka (status disetujui) ke lk.parameter_item RKA_TD item terkait (item -> lapus -> induk).';

-- Seri referensi bersama (IHK/IHPB, indeks IBS/IMK agregat, PDRB TD2010 sebagai ekstrapolator, dll.).
-- DILARANG menyimpan data mikro perusahaan.
CREATE TABLE lk.seri_referensi (
  id         serial PRIMARY KEY,
  kode       text NOT NULL UNIQUE,
  nama       text NOT NULL,
  jenis      text NOT NULL CHECK (jenis IN ('indeks_harga','indeks_produksi','indeks_nilai','pdrb_td2010','lainnya')),
  satuan     text,
  sumber_id  integer REFERENCES ref.sumber_data(id),
  keterangan text
);

CREATE TABLE lk.nilai_seri_referensi (
  putaran_id   bigint  NOT NULL REFERENCES lk.putaran(id) ON DELETE CASCADE,
  seri_id      integer NOT NULL REFERENCES lk.seri_referensi(id),
  wilayah_kode char(4) NOT NULL REFERENCES ref.wilayah(kode),
  periode_id   integer NOT NULL REFERENCES ref.periode(id),
  nilai        numeric NOT NULL,
  diubah_oleh  bigint REFERENCES sec.pengguna(id),
  diubah_pada  timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (putaran_id, seri_id, wilayah_kode, periode_id)
);

-- Tautan: seri item diambil otomatis dari seri referensi ATAU dari hasil lapus lain
-- (mis. A.1.e ← Σ output A.1.a–A.1.d). Seri tertaut tidak dapat diisi manual.
CREATE TABLE lk.tautan_seri (
  item_id          bigint  NOT NULL REFERENCES lk.item(id) ON DELETE CASCADE,
  jenis_seri       text    NOT NULL,
  sumber           text    NOT NULL CHECK (sumber IN ('SERI_REFERENSI','HASIL_LAPUS','RUMUS')),
  rumus            text CHECK (rumus IS NULL OR rumus IN ('TPK_X_KAMAR','JANGKAR_X_IH_100','KAPITA_X_PENDUDUK_X_3',
                                                         'MARGIN_X_OUTPUT','MARGIN_X_IMPOR')),  -- MARGIN_X_IMPOR: migrasi 0004
  seri_id          integer REFERENCES lk.seri_referensi(id),
  lapus_sumber_ids integer[],
  besaran          text CHECK (besaran IN ('OUT_CP','OUT_K','GVA_CP','GVA_K','IMPLISIT_OUT')),
  faktor           numeric NOT NULL DEFAULT 1,
  PRIMARY KEY (item_id, jenis_seri),
  CHECK ((sumber = 'SERI_REFERENSI' AND seri_id IS NOT NULL)
      OR (sumber = 'HASIL_LAPUS' AND lapus_sumber_ids IS NOT NULL AND besaran IS NOT NULL)
      OR (sumber = 'RUMUS' AND rumus IS NOT NULL))
);

CREATE TABLE lk.penyesuaian (
  id              bigserial PRIMARY KEY,
  putaran_id      bigint  NOT NULL REFERENCES lk.putaran(id) ON DELETE CASCADE,
  wilayah_kode    char(4) NOT NULL REFERENCES ref.wilayah(kode),
  lapus_id        integer NOT NULL REFERENCES ref.lapus(id),
  tahap           text    NOT NULL CHECK (tahap IN ('METODE','REKON','SIMULASI')),
  metode_kode     text    REFERENCES ref.metode(kode),
  jenis_kode      text    NOT NULL REFERENCES ref.jenis_penyesuaian(kode),
  harga           text    NOT NULL CHECK (harga IN ('CP','K')),
  periode_id      integer NOT NULL REFERENCES ref.periode(id),
  nilai           numeric NOT NULL,
  alasan          text,
  status          text NOT NULL DEFAULT 'draf' CHECK (status IN ('draf','diajukan','disetujui','ditolak')),
  diusulkan_oleh  bigint REFERENCES sec.pengguna(id),
  diusulkan_pada  timestamptz NOT NULL DEFAULT now(),
  diputus_oleh    bigint REFERENCES sec.pengguna(id),
  diputus_pada    timestamptz,
  catatan_putusan text,
  CHECK ((tahap = 'METODE') = (metode_kode IS NOT NULL))
);
CREATE UNIQUE INDEX uq_penyesuaian ON lk.penyesuaian
  (putaran_id, wilayah_kode, lapus_id, tahap, COALESCE(metode_kode, '-'), jenis_kode, harga, periode_id);

CREATE OR REPLACE FUNCTION lk.cek_penyesuaian() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE j ref.jenis_penyesuaian;
BEGIN
  SELECT * INTO j FROM ref.jenis_penyesuaian WHERE kode = NEW.jenis_kode;
  IF j.tahap <> NEW.tahap THEN
    RAISE EXCEPTION 'Jenis % tidak berlaku pada tahap %', NEW.jenis_kode, NEW.tahap USING ERRCODE = 'check_violation';
  END IF;
  IF j.wajib_alasan AND coalesce(length(trim(NEW.alasan)), 0) < 10 THEN
    RAISE EXCEPTION 'Alasan penyesuaian wajib diisi (min. 10 karakter)' USING ERRCODE = 'check_violation';
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER trg_penyesuaian_cek BEFORE INSERT OR UPDATE ON lk.penyesuaian
  FOR EACH ROW EXECUTE FUNCTION lk.cek_penyesuaian();

-- Hasil per item (untuk telusur kontribusi) — ditulis oleh mesin.
CREATE TABLE lk.hasil_item (
  putaran_id bigint  NOT NULL REFERENCES lk.putaran(id) ON DELETE CASCADE,
  item_id    bigint  NOT NULL REFERENCES lk.item(id),
  periode_id integer NOT NULL REFERENCES ref.periode(id),
  out_cp numeric NOT NULL, gva_cp numeric NOT NULL,
  out_k  numeric NOT NULL, gva_k  numeric NOT NULL,
  PRIMARY KEY (putaran_id, item_id, periode_id)
);

-- Hasil per metode (PR = jumlah item; PRE = setelah ADJ1/ADJ2/SC).
CREATE TABLE lk.hasil_metode (
  putaran_id   bigint  NOT NULL REFERENCES lk.putaran(id) ON DELETE CASCADE,
  wilayah_kode char(4) NOT NULL REFERENCES ref.wilayah(kode),
  lapus_id     integer NOT NULL REFERENCES ref.lapus(id),
  metode_kode  text    NOT NULL REFERENCES ref.metode(kode),
  periode_id   integer NOT NULL REFERENCES ref.periode(id),
  out_cp_pr numeric NOT NULL, gva_cp_pr numeric NOT NULL, out_k_pr numeric NOT NULL, gva_k_pr numeric NOT NULL,
  out_cp_pre numeric NOT NULL, gva_cp_pre numeric NOT NULL, out_k_pre numeric NOT NULL, gva_k_pre numeric NOT NULL,
  PRIMARY KEY (putaran_id, wilayah_kode, lapus_id, metode_kode, periode_id)
);

-- Hasil per lapus (daun dan agregat). Tahap: PRE, POST, BENC (hasil LK 01), FINAL (setelah simulasi).
CREATE TABLE lk.hasil_lapus (
  putaran_id   bigint  NOT NULL REFERENCES lk.putaran(id) ON DELETE CASCADE,
  wilayah_kode char(4) NOT NULL REFERENCES ref.wilayah(kode),
  lapus_id     integer NOT NULL REFERENCES ref.lapus(id),
  periode_id   integer NOT NULL REFERENCES ref.periode(id),
  tahap        text    NOT NULL CHECK (tahap IN ('PRE','POST','BENC','FINAL')),
  out_cp numeric NOT NULL, gva_cp numeric NOT NULL,
  out_k  numeric NOT NULL, gva_k  numeric NOT NULL,
  versi_mesin  text NOT NULL,
  hash_input   text NOT NULL,                    -- SHA-256 semua input yang dipakai
  dihitung_pada timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (putaran_id, wilayah_kode, lapus_id, periode_id, tahap)
);
CREATE INDEX ON lk.hasil_lapus (putaran_id, wilayah_kode, tahap, periode_id);

CREATE TABLE lk.status_lapus (
  putaran_id   bigint  NOT NULL REFERENCES lk.putaran(id) ON DELETE CASCADE,
  wilayah_kode char(4) NOT NULL REFERENCES ref.wilayah(kode),
  lapus_id     integer NOT NULL REFERENCES ref.lapus(id),
  status       text NOT NULL DEFAULT 'belum'
               CHECK (status IN ('belum','draf','diajukan','disetujui','dikembalikan','nihil')),
  diperbarui_oleh bigint REFERENCES sec.pengguna(id),
  diperbarui_pada timestamptz NOT NULL DEFAULT now(),
  catatan      text,
  PRIMARY KEY (putaran_id, wilayah_kode, lapus_id)
);

CREATE TABLE lk.riwayat_status (
  id           bigserial PRIMARY KEY,
  putaran_id   bigint  NOT NULL REFERENCES lk.putaran(id) ON DELETE CASCADE,
  wilayah_kode char(4) NOT NULL,
  lapus_id     integer NOT NULL,
  dari         text, ke text NOT NULL,
  oleh         bigint REFERENCES sec.pengguna(id),
  pada         timestamptz NOT NULL DEFAULT now(),
  catatan      text
);

CREATE TABLE lk.hasil_validasi (
  id                 bigserial PRIMARY KEY,
  putaran_id         bigint  NOT NULL REFERENCES lk.putaran(id) ON DELETE CASCADE,
  wilayah_kode       char(4) NOT NULL,
  lapus_id           integer NOT NULL REFERENCES ref.lapus(id),
  item_id            bigint REFERENCES lk.item(id),
  periode_id         integer REFERENCES ref.periode(id),
  kode_validasi      text NOT NULL REFERENCES ref.validasi(kode),
  pesan              text NOT NULL,
  dikonfirmasi_oleh  bigint REFERENCES sec.pengguna(id),
  alasan_konfirmasi  text,
  dibuat_pada        timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ON lk.hasil_validasi (putaran_id, wilayah_kode, lapus_id);

-- Antrean hitung (worker latar; tanpa Redis).
CREATE TABLE lk.antrean_hitung (
  id           bigserial PRIMARY KEY,
  putaran_id   bigint  NOT NULL REFERENCES lk.putaran(id) ON DELETE CASCADE,
  wilayah_kode char(4) NOT NULL,
  lapus_id     integer,                         -- NULL = hitung penuh wilayah
  alasan       text NOT NULL,
  status       text NOT NULL DEFAULT 'menunggu' CHECK (status IN ('menunggu','proses','selesai','gagal')),
  dibuat_pada  timestamptz NOT NULL DEFAULT now(),
  mulai_pada   timestamptz, selesai_pada timestamptz,
  pesan        text
);
CREATE INDEX ON lk.antrean_hitung (status, dibuat_pada) WHERE status IN ('menunggu','proses');

-- ---------------------------------------------------------------------
-- Penguncian putaran: tolak semua penulisan ke putaran terkunci.
-- Aplikasi memetakan SQLSTATE 'P0423' ke HTTP 423 Locked.
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION lk.tolak_jika_terkunci() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE v_status text; v_pid bigint;
BEGIN
  v_pid := CASE WHEN TG_OP = 'DELETE' THEN OLD.putaran_id ELSE NEW.putaran_id END;
  SELECT status INTO v_status FROM lk.putaran WHERE id = v_pid;
  IF v_status = 'terkunci' AND coalesce(current_setting('app.izin_buka_kunci', true), '') <> 'ya' THEN
    RAISE EXCEPTION 'Putaran % terkunci', v_pid USING ERRCODE = 'P0423';
  END IF;
  RETURN CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END;
END $$;

DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['nilai_item','parameter_item','nilai_seri_referensi','penyesuaian',
                           'hasil_item','hasil_metode','hasil_lapus','status_lapus'] LOOP
    EXECUTE format('CREATE TRIGGER trg_%s_kunci BEFORE INSERT OR UPDATE OR DELETE ON lk.%I
                    FOR EACH ROW EXECUTE FUNCTION lk.tolak_jika_terkunci()', t, t);
  END LOOP;
END $$;

-- ---------------------------------------------------------------------
-- Pembatasan baris (RLS): operator hanya menulis lapus-wilayah yang ditugaskan.
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION lk.boleh_tulis(p_wilayah char(4), p_lapus integer) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = lk, sec, pg_temp AS $$
  SELECT sec.punya_izin('data.tulis_semua')
      OR EXISTS (SELECT 1 FROM lk.penugasan p
                 WHERE p.pengguna_id = sec.uid() AND p.peran_tugas = 'operator'
                   AND p.wilayah_kode = p_wilayah AND p.lapus_id = p_lapus
                   AND current_date >= p.berlaku_mulai
                   AND (p.berlaku_sampai IS NULL OR current_date <= p.berlaku_sampai))
$$;

CREATE OR REPLACE FUNCTION lk.boleh_tulis_item(p_item bigint) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = lk, sec, pg_temp AS $$
  SELECT lk.boleh_tulis(i.wilayah_kode, i.lapus_id) FROM lk.item i WHERE i.id = p_item
$$;

ALTER TABLE lk.item            ENABLE ROW LEVEL SECURITY;
ALTER TABLE lk.nilai_item      ENABLE ROW LEVEL SECURITY;
ALTER TABLE lk.parameter_item  ENABLE ROW LEVEL SECURITY;
ALTER TABLE lk.penyesuaian     ENABLE ROW LEVEL SECURITY;

-- Baca: semua pengguna terautentikasi aplikasi (pembatasan baca dilakukan di API sesuai izin).
CREATE POLICY baca_item  ON lk.item           FOR SELECT USING (sec.uid() IS NOT NULL OR current_user = 'app_ro');
CREATE POLICY baca_nilai ON lk.nilai_item     FOR SELECT USING (sec.uid() IS NOT NULL OR current_user = 'app_ro');
CREATE POLICY baca_param ON lk.parameter_item FOR SELECT USING (sec.uid() IS NOT NULL OR current_user = 'app_ro');
CREATE POLICY baca_adj   ON lk.penyesuaian    FOR SELECT USING (sec.uid() IS NOT NULL OR current_user = 'app_ro');

CREATE POLICY tulis_item  ON lk.item FOR ALL
  USING (lk.boleh_tulis(wilayah_kode, lapus_id)) WITH CHECK (lk.boleh_tulis(wilayah_kode, lapus_id));
CREATE POLICY tulis_nilai ON lk.nilai_item FOR ALL
  USING (lk.boleh_tulis_item(item_id)) WITH CHECK (lk.boleh_tulis_item(item_id));
CREATE POLICY tulis_param ON lk.parameter_item FOR ALL
  USING (lk.boleh_tulis_item(item_id)) WITH CHECK (lk.boleh_tulis_item(item_id));
-- Penyesuaian tahap SIMULASI hanya untuk pemegang izin simulasi.edit.
CREATE POLICY tulis_adj ON lk.penyesuaian FOR ALL
  USING (CASE WHEN tahap = 'SIMULASI' THEN sec.punya_izin('simulasi.edit')
              ELSE lk.boleh_tulis(wilayah_kode, lapus_id) OR sec.punya_izin('penyesuaian.putus') END)
  WITH CHECK (CASE WHEN tahap = 'SIMULASI' THEN sec.punya_izin('simulasi.edit')
                   ELSE lk.boleh_tulis(wilayah_kode, lapus_id) OR sec.punya_izin('penyesuaian.putus') END);

-- =====================================================================
-- AUDIT — jejak append-only berantai hash
-- =====================================================================
CREATE TABLE audit.log (
  id           bigserial PRIMARY KEY,
  waktu        timestamptz NOT NULL DEFAULT clock_timestamp(),
  pengguna_id  bigint,
  ip           inet,
  aksi         text NOT NULL,                  -- INSERT/UPDATE/DELETE/LOGIN/EKSPOR/KUNCI/...
  entitas      text NOT NULL,
  entitas_id   text,
  putaran_id   bigint,
  nilai_lama   jsonb,
  nilai_baru   jsonb,
  alasan       text,
  hash_sebelum text,
  hash         text NOT NULL
);
CREATE INDEX ON audit.log (entitas, entitas_id);
CREATE INDEX ON audit.log (pengguna_id, waktu);

CREATE OR REPLACE FUNCTION audit.rantai_hash() RETURNS trigger LANGUAGE plpgsql
SET search_path = audit, ext, pg_temp AS $$
DECLARE v_prev text;
BEGIN
  PERFORM pg_advisory_xact_lock(424242);
  SELECT hash INTO v_prev FROM audit.log ORDER BY id DESC LIMIT 1;
  NEW.hash_sebelum := v_prev;
  NEW.hash := encode(ext.digest(coalesce(v_prev,'') || NEW.waktu::text || coalesce(NEW.pengguna_id::text,'')
              || NEW.aksi || NEW.entitas || coalesce(NEW.entitas_id,'')
              || coalesce(NEW.nilai_lama::text,'') || coalesce(NEW.nilai_baru::text,''), 'sha256'), 'hex');
  RETURN NEW;
END $$;
CREATE TRIGGER trg_audit_hash BEFORE INSERT ON audit.log FOR EACH ROW EXECUTE FUNCTION audit.rantai_hash();

CREATE OR REPLACE FUNCTION audit.tolak_ubah() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION 'audit.log bersifat append-only' USING ERRCODE = 'insufficient_privilege';
END $$;
CREATE TRIGGER trg_audit_ro BEFORE UPDATE OR DELETE ON audit.log FOR EACH ROW EXECUTE FUNCTION audit.tolak_ubah();
CREATE TRIGGER trg_audit_trunc BEFORE TRUNCATE ON audit.log FOR EACH STATEMENT EXECUTE FUNCTION audit.tolak_ubah();

-- Pencatat generik perubahan data (dipasang pada tabel penting).
CREATE OR REPLACE FUNCTION audit.catat() RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER
SET search_path = audit, pg_temp AS $$
DECLARE v_id text; v_put bigint; j_old jsonb; j_new jsonb;
BEGIN
  j_old := CASE WHEN TG_OP IN ('UPDATE','DELETE') THEN to_jsonb(OLD) END;
  j_new := CASE WHEN TG_OP IN ('INSERT','UPDATE') THEN to_jsonb(NEW) END;
  v_id  := coalesce(j_new->>'id', j_old->>'id',
                    concat_ws('|', coalesce(j_new,j_old)->>'putaran_id', coalesce(j_new,j_old)->>'item_id',
                                   coalesce(j_new,j_old)->>'jenis_seri', coalesce(j_new,j_old)->>'periode_id',
                                   coalesce(j_new,j_old)->>'kode'));
  v_put := NULLIF(coalesce(j_new,j_old)->>'putaran_id','')::bigint;
  INSERT INTO audit.log (pengguna_id, ip, aksi, entitas, entitas_id, putaran_id, nilai_lama, nilai_baru, alasan, hash)
  VALUES (sec.uid(), NULLIF(current_setting('app.ip', true),'')::inet, TG_OP, TG_TABLE_SCHEMA||'.'||TG_TABLE_NAME,
          v_id, v_put, j_old, j_new, NULLIF(current_setting('app.alasan', true),''), 'x');
  RETURN NULL;
END $$;

DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['lk.item','lk.nilai_item','lk.parameter_item','lk.penyesuaian','lk.putaran',
                           'lk.penugasan','lk.status_lapus','lk.tautan_seri','lk.nilai_seri_referensi',
                           'sec.pengguna_peran','sec.peran_izin','ref.lapus','ref.konkordansi_lapus','lk.struktur_biaya'] LOOP
    EXECUTE format('CREATE TRIGGER trg_audit AFTER INSERT OR UPDATE OR DELETE ON %s
                    FOR EACH ROW EXECUTE FUNCTION audit.catat()', t);
  END LOOP;
END $$;

-- ---------------------------------------------------------------------
-- Migrasi 0003 (F1 master): RLS tulis master & hak akses, audit semua tabel master.
-- Tulis ref.* hanya dengan izin master.kelola; tulis peran/izin/penugasan hanya dengan izin pengguna.kelola.
-- ---------------------------------------------------------------------
DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['ref.tahun_dasar','ref.wilayah','ref.lapus','ref.lapus_kelompok','ref.konkordansi_lapus',
                           'ref.katalog_komoditas','ref.satuan','ref.sumber_data','ref.validasi'] LOOP
    EXECUTE format('ALTER TABLE %s ENABLE ROW LEVEL SECURITY', t);
    EXECUTE format('CREATE POLICY baca ON %s FOR SELECT USING (true)', t);
    EXECUTE format('CREATE POLICY kelola ON %s FOR ALL USING (sec.punya_izin(''master.kelola''))'
                   ' WITH CHECK (sec.punya_izin(''master.kelola''))', t);
  END LOOP;
  FOREACH t IN ARRAY ARRAY['sec.peran','sec.peran_izin','sec.pengguna_peran','lk.penugasan'] LOOP
    EXECUTE format('ALTER TABLE %s ENABLE ROW LEVEL SECURITY', t);
    EXECUTE format('CREATE POLICY baca ON %s FOR SELECT USING (true)', t);
    EXECUTE format('CREATE POLICY kelola ON %s FOR ALL USING (sec.punya_izin(''pengguna.kelola''))'
                   ' WITH CHECK (sec.punya_izin(''pengguna.kelola''))', t);
  END LOOP;
  FOREACH t IN ARRAY ARRAY['ref.tahun_dasar','ref.wilayah','ref.lapus_kelompok','ref.katalog_komoditas','ref.satuan',
                           'ref.sumber_data','ref.validasi','sec.peran'] LOOP
    EXECUTE format('CREATE TRIGGER trg_audit AFTER INSERT OR UPDATE OR DELETE ON %s
                    FOR EACH ROW EXECUTE FUNCTION audit.catat()', t);
  END LOOP;
END $$;

-- sec.pengguna diaudit tanpa hash sandi / rahasia TOTP dan tanpa pembukuan login (dicatat aplikasi).
CREATE OR REPLACE FUNCTION audit.catat_pengguna() RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER
SET search_path = audit, pg_temp AS $$
DECLARE
  j_old jsonb; j_new jsonb;
  rahasia text[] := ARRAY['password_hash','totp_secret_enc'];
  pembukuan text[] := ARRAY['gagal_login','terkunci_sampai','terakhir_login','totp_langkah_terakhir','diubah_pada'];
BEGIN
  j_old := CASE WHEN TG_OP IN ('UPDATE','DELETE') THEN to_jsonb(OLD) - rahasia END;
  j_new := CASE WHEN TG_OP IN ('INSERT','UPDATE') THEN to_jsonb(NEW) - rahasia END;
  IF TG_OP = 'UPDATE' THEN
    IF OLD.password_hash IS DISTINCT FROM NEW.password_hash THEN j_new := j_new || '{"sandi_diubah": true}'; END IF;
    IF OLD.totp_secret_enc IS DISTINCT FROM NEW.totp_secret_enc THEN
      j_new := j_new || '{"rahasia_totp_diubah": true}';
    END IF;
    IF (j_old - pembukuan) = (j_new - pembukuan) THEN RETURN NULL; END IF;
  END IF;
  INSERT INTO audit.log (pengguna_id, ip, aksi, entitas, entitas_id, nilai_lama, nilai_baru, alasan, hash)
  VALUES (sec.uid(), NULLIF(current_setting('app.ip', true),'')::inet, TG_OP, 'sec.pengguna',
          coalesce(j_new, j_old)->>'id', j_old, j_new, NULLIF(current_setting('app.alasan', true),''), 'x');
  RETURN NULL;
END $$;
CREATE TRIGGER trg_audit AFTER INSERT OR UPDATE OR DELETE ON sec.pengguna
  FOR EACH ROW EXECUTE FUNCTION audit.catat_pengguna();

CREATE TABLE audit.impor_berkas (
  id          bigserial PRIMARY KEY,
  nama_berkas text NOT NULL,
  sha256      text NOT NULL,
  jenis       text NOT NULL CHECK (jenis IN ('templat_xlsx','lk_xlsm','csv_panjang','seri_referensi')),
  pengguna_id bigint REFERENCES sec.pengguna(id),
  putaran_id  bigint REFERENCES lk.putaran(id),
  waktu       timestamptz NOT NULL DEFAULT now(),
  jumlah_baris integer,
  status      text NOT NULL CHECK (status IN ('pratinjau','diterapkan','ditolak')),
  pesan       jsonb
);   -- berkas mentah TIDAK disimpan

CREATE TABLE audit.ekspor (
  id          bigserial PRIMARY KEY,
  pengguna_id bigint REFERENCES sec.pengguna(id),
  waktu       timestamptz NOT NULL DEFAULT now(),
  jenis       text NOT NULL,
  parameter   jsonb NOT NULL,
  tanda_air   text NOT NULL
);

-- =====================================================================
-- VIEW tabel pokok (format tetap; urutan baris dari ref.lapus.urutan)
-- =====================================================================
CREATE TABLE lk.tabel_pokok_rilis (                    -- angka resmi yang sudah rilis (riwayat TD2010 2019+, pembanding)
  tahun_dasar_id smallint NOT NULL REFERENCES ref.tahun_dasar(id),
  wilayah_kode   char(4)  NOT NULL REFERENCES ref.wilayah(kode),
  lapus_id       integer  NOT NULL REFERENCES ref.lapus(id),
  periode_id     integer  NOT NULL REFERENCES ref.periode(id),
  ntb_adhb numeric, ntb_adhk numeric,
  sumber         text NOT NULL,                          -- mis. 'Rilis BRS Agustus 2025', 'LK TD2010 final'
  versi          text NOT NULL,
  diimpor_oleh   bigint REFERENCES sec.pengguna(id),
  diimpor_pada   timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (tahun_dasar_id, wilayah_kode, lapus_id, periode_id, versi)
);

CREATE TRIGGER trg_audit AFTER INSERT OR UPDATE OR DELETE ON lk.tabel_pokok_rilis
  FOR EACH ROW EXECUTE FUNCTION audit.catat();

-- Tabel pokok: SEMUA baris pohon lapus (kategori, subkategori, daun, kelompok, NTB, TOP, SOP, PDRB) untuk setiap periode
-- putaran, urut sesuai Excel. Baris tanpa hasil tetap tampil (nilai NULL) agar format tidak berubah.
CREATE OR REPLACE VIEW lk.v_tabel_pokok AS
SELECT pu.id AS putaran_id, w.kode AS wilayah_kode, l.tahun_dasar_id, l.urutan, l.kode AS kode_lapus, l.nama AS nama_lapus,
       l.level, l.jenis, p.tahun, p.triwulan, p.label AS periode,
       h.gva_cp AS ntb_adhb, h.gva_k AS ntb_adhk, h.out_cp AS output_adhb, h.out_k AS output_adhk,
       CASE WHEN h.gva_k <> 0 THEN h.gva_cp / h.gva_k * 100 END AS indeks_implisit
FROM lk.putaran pu
JOIN ref.lapus   l ON l.tahun_dasar_id = pu.tahun_dasar_id AND l.aktif
JOIN ref.periode p ON p.urut BETWEEN (SELECT urut FROM ref.periode WHERE id = pu.periode_awal_id)
                                 AND (SELECT urut FROM ref.periode WHERE id = pu.periode_akhir_id)
CROSS JOIN ref.wilayah w
LEFT JOIN lk.hasil_lapus h ON h.putaran_id = pu.id AND h.wilayah_kode = w.kode AND h.lapus_id = l.id
                          AND h.periode_id = p.id AND h.tahap = 'FINAL';

-- =====================================================================
-- PERAN BASIS DATA (jalankan sebagai superuser saat provisioning)
-- =====================================================================
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_rw') THEN CREATE ROLE app_rw NOLOGIN; END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_ro') THEN CREATE ROLE app_ro NOLOGIN; END IF;
END $$;

GRANT USAGE ON SCHEMA ref, lk, sec, audit, ext TO app_rw, app_ro;
GRANT SELECT ON ALL TABLES IN SCHEMA ref, lk TO app_ro;
GRANT SELECT ON ALL TABLES IN SCHEMA ref TO app_rw;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA lk, sec TO app_rw;
GRANT SELECT, INSERT ON ALL TABLES IN SCHEMA audit TO app_rw;
REVOKE UPDATE, DELETE, TRUNCATE ON ALL TABLES IN SCHEMA audit FROM app_rw;
GRANT USAGE ON ALL SEQUENCES IN SCHEMA lk, sec, audit TO app_rw;
-- Master (ref) diubah hanya lewat endpoint admin yang memakai koneksi app_rw + izin master.kelola:
GRANT INSERT, UPDATE ON ref.lapus, ref.lapus_kelompok, ref.konkordansi_lapus, ref.katalog_komoditas, ref.sumber_data,
      ref.satuan, ref.validasi, ref.tahun_dasar, ref.wilayah TO app_rw;
-- Migrasi 0003: hapus master (API menonaktifkan bila sudah dipakai data). Dibatasi izin master.kelola lewat RLS.
GRANT DELETE ON ref.tahun_dasar, ref.wilayah, ref.lapus, ref.lapus_kelompok, ref.konkordansi_lapus,
      ref.katalog_komoditas, ref.satuan, ref.sumber_data TO app_rw;
GRANT USAGE ON ALL SEQUENCES IN SCHEMA ref TO app_rw;
-- app_rw TIDAK memiliki hak DDL dan bukan pemilik tabel, sehingga RLS berlaku.
