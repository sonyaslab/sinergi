"""F3 Data dasar: metadata seri item, seri referensi harga, validasi V01–V17, RLS tautan dan seri referensi.

- lk.seri_item: satu baris templat = satu seri item (satuan, label, catatan, lokasi sumber, teks tautan asli, urutan),
  agar ekspor templat sama persis dengan impor (round-trip). Nilai tetap di lk.nilai_item.
- lk.item.padanan_teks: isi asli kolom "Kode LK BPS" (TD2025) / "Lapus TD2025 (konkordansi)" (TD2010).
- lk.seri_referensi.jenis menerima 'harga' (keputusan 5: "ikut item lain" -> seri referensi). Definisi seri referensi
  diaudit. Tulis seri referensi dan nilainya hanya dengan izin data.tulis_semua atau master.kelola (seri dipakai
  banyak lapus), atau oleh operator lapus pemilik (lapus_pemilik_id; seri hasil konversi "ikut item lain") untuk
  wilayah yang ditugaskan. lk.tautan_seri ber-RLS seperti lk.item (operator hanya lapus yang ditugaskan).
- lk.hasil_validasi: tingkat temuan, seri, dan kunci stabil (untuk konfirmasi). lk.konfirmasi_validasi menyimpan
  konfirmasi beralasan (V05) yang bertahan setelah hitung ulang.
- Kebijakan RLS tulis lk.* dipecah per perintah (INSERT/UPDATE/DELETE): FOR ALL juga berlaku saat SELECT sehingga
  fungsi izin dievaluasi per baris pada setiap baca (pemuat worker macet pada puluhan ribu nilai).
- ref.validasi.parameter: V05 boleh dikonfirmasi; V06 toleransi 0,5; V08 ambang tetap 30% + kalibrasi P95 opsional per
  lapus (keputusan 9/16); V11 ambang 1%.

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-05
"""
from __future__ import annotations

from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None

BACA = "sec.uid() IS NOT NULL OR current_user = 'app_ro'"
# Teks fungsi HARUS sama persis dengan db/schema.sql (diuji tests/rls/test_skema_sinkron.py).
BOLEH_TULIS_SERI_REF = """CREATE OR REPLACE FUNCTION lk.boleh_tulis_seri_ref(p_pemilik integer, p_wilayah char(4))
RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER SET search_path = lk, sec, pg_temp AS $$
  SELECT sec.punya_izin('data.tulis_semua') OR sec.punya_izin('master.kelola')
      OR (p_pemilik IS NOT NULL AND EXISTS (
            SELECT 1 FROM lk.penugasan p
             WHERE p.pengguna_id = sec.uid() AND p.peran_tugas = 'operator' AND p.lapus_id = p_pemilik
               AND (p_wilayah IS NULL OR p.wilayah_kode = p_wilayah)
               AND current_date >= p.berlaku_mulai
               AND (p.berlaku_sampai IS NULL OR current_date <= p.berlaku_sampai)))
$$;"""
KEBIJAKAN_TULIS = [  # (nama, tabel, ekspresi); 4 pertama sudah ada sejak baseline (FOR ALL)
    ("tulis_item", "lk.item", "lk.boleh_tulis(wilayah_kode, lapus_id)"),
    ("tulis_nilai", "lk.nilai_item", "lk.boleh_tulis_item(item_id)"),
    ("tulis_param", "lk.parameter_item", "lk.boleh_tulis_item(item_id)"),
    ("tulis_adj", "lk.penyesuaian", "CASE WHEN tahap = 'SIMULASI' THEN sec.punya_izin('simulasi.edit') ELSE"
                                    " lk.boleh_tulis(wilayah_kode, lapus_id) OR sec.punya_izin('penyesuaian.putus')"
                                    " END"),
    ("tulis_seri", "lk.seri_item", "lk.boleh_tulis_item(item_id)"),
    ("tulis_tautan", "lk.tautan_seri", "lk.boleh_tulis_item(item_id)"),
    ("tulis_konfirmasi", "lk.konfirmasi_validasi",
     "lk.boleh_tulis(wilayah_kode, lapus_id) OR sec.punya_izin('lk.setujui')"),
    ("tulis_seri_ref", "lk.seri_referensi", "lk.boleh_tulis_seri_ref(lapus_pemilik_id, NULL)"),
    ("tulis_nilai_ref", "lk.nilai_seri_referensi",
     "lk.boleh_tulis_seri_ref((SELECT s.lapus_pemilik_id FROM lk.seri_referensi s WHERE s.id = seri_id),"
     " wilayah_kode)"),
]
PARAM_V08 = ('{"ambang_persen": {"qtq_volume": 30, "yoy_volume": 30, "qtq_implisit": 30, "yoy_implisit": 30},'
             ' "kalibrasi": "tetap", "p95": {"tahun_awal": 2019, "tahun_akhir": 2025, "min_titik": 8,'
             ' "batas_bawah_persen": null}, "per_lapus": {}}')


def upgrade() -> None:
    op.execute("ALTER TABLE lk.item ADD COLUMN padanan_teks text")
    op.execute("""
CREATE TABLE lk.seri_item (
  item_id       bigint   NOT NULL REFERENCES lk.item(id) ON DELETE CASCADE,
  jenis_seri    text     NOT NULL,
  urutan        smallint NOT NULL DEFAULT 0,
  satuan        text,
  label         text,
  catatan       text,
  lokasi_sumber text,
  teks_tautan   text,
  PRIMARY KEY (item_id, jenis_seri)
)""")
    op.execute("COMMENT ON TABLE lk.seri_item IS 'Satu baris templat = satu seri item: satuan, label, catatan, lokasi"
               " sumber, teks asli kolom Tautan/Rumus, urutan baris. Nilai di lk.nilai_item, tautan di"
               " lk.tautan_seri.'")
    op.execute("ALTER TABLE lk.seri_referensi DROP CONSTRAINT seri_referensi_jenis_check")
    op.execute("ALTER TABLE lk.seri_referensi ADD CONSTRAINT seri_referensi_jenis_check CHECK (jenis IN"
               " ('indeks_harga','indeks_produksi','indeks_nilai','pdrb_td2010','lainnya','harga'))")
    op.execute("ALTER TABLE lk.hasil_validasi ADD COLUMN jenis_seri text")
    op.execute("ALTER TABLE lk.hasil_validasi ADD COLUMN tingkat text NOT NULL DEFAULT 'peringatan'"
               " CHECK (tingkat IN ('info','peringatan','blokir_ajukan','blokir_kunci'))")
    op.execute("ALTER TABLE lk.hasil_validasi ADD COLUMN kunci text")
    op.execute("""
CREATE TABLE lk.konfirmasi_validasi (
  putaran_id        bigint  NOT NULL REFERENCES lk.putaran(id) ON DELETE CASCADE,
  wilayah_kode      char(4) NOT NULL REFERENCES ref.wilayah(kode),
  lapus_id          integer NOT NULL REFERENCES ref.lapus(id),
  kode_validasi     text    NOT NULL REFERENCES ref.validasi(kode),
  kunci             text    NOT NULL,
  alasan            text    NOT NULL CHECK (length(trim(alasan)) >= 10),
  dikonfirmasi_oleh bigint  REFERENCES sec.pengguna(id),
  dikonfirmasi_pada timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (putaran_id, wilayah_kode, lapus_id, kode_validasi, kunci)
)""")
    for t in ("seri_item", "konfirmasi_validasi"):
        op.execute(f"GRANT SELECT ON lk.{t} TO app_ro")
        op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON lk.{t} TO app_rw")
    op.execute("CREATE TRIGGER trg_konfirmasi_validasi_kunci BEFORE INSERT OR UPDATE OR DELETE"
               " ON lk.konfirmasi_validasi FOR EACH ROW EXECUTE FUNCTION lk.tolak_jika_terkunci()")
    for t in ("lk.seri_item", "lk.konfirmasi_validasi", "lk.seri_referensi"):
        op.execute(f"CREATE TRIGGER trg_audit AFTER INSERT OR UPDATE OR DELETE ON {t}"
                   " FOR EACH ROW EXECUTE FUNCTION audit.catat()")

    for t, nama in (("seri_item", "seri"), ("tautan_seri", "tautan")):
        op.execute(f"ALTER TABLE lk.{t} ENABLE ROW LEVEL SECURITY")
        op.execute(f"CREATE POLICY baca_{nama} ON lk.{t} FOR SELECT USING ({BACA})")
    op.execute("ALTER TABLE lk.konfirmasi_validasi ENABLE ROW LEVEL SECURITY")
    op.execute(f"CREATE POLICY baca_konfirmasi ON lk.konfirmasi_validasi FOR SELECT USING ({BACA})")
    op.execute("ALTER TABLE lk.seri_referensi ADD COLUMN lapus_pemilik_id integer REFERENCES ref.lapus(id)")
    op.execute(BOLEH_TULIS_SERI_REF)
    for t, nama in (("seri_referensi", "seri_ref"), ("nilai_seri_referensi", "nilai_ref")):
        op.execute(f"ALTER TABLE lk.{t} ENABLE ROW LEVEL SECURITY")
        op.execute(f"CREATE POLICY baca_{nama} ON lk.{t} FOR SELECT USING ({BACA})")
    # Kebijakan tulis per perintah (bukan FOR ALL): FOR ALL juga berlaku pada SELECT sehingga fungsi izin
    # (SECURITY DEFINER, bersubkueri) dievaluasi per baris pada setiap baca. Hak baca tidak berubah (baca_*).
    for nama, tabel, _ in KEBIJAKAN_TULIS[:4]:
        op.execute(f"DROP POLICY {nama} ON {tabel}")
    for nama, tabel, ekspr in KEBIJAKAN_TULIS:
        op.execute(f"CREATE POLICY {nama}_i ON {tabel} FOR INSERT WITH CHECK ({ekspr})")
        op.execute(f"CREATE POLICY {nama}_u ON {tabel} FOR UPDATE USING ({ekspr}) WITH CHECK ({ekspr})")
        op.execute(f"CREATE POLICY {nama}_d ON {tabel} FOR DELETE USING ({ekspr})")

    op.execute("""UPDATE ref.validasi SET parameter = '{"boleh_konfirmasi": true}' WHERE kode = 'V05'""")
    op.execute("""UPDATE ref.validasi SET parameter = '{"toleransi": 0.5}' WHERE kode = 'V06'""")
    op.execute(f"UPDATE ref.validasi SET parameter = '{PARAM_V08}' WHERE kode = 'V08'")
    op.execute("""UPDATE ref.validasi SET parameter = '{"ambang_persen": 1}' WHERE kode = 'V11'""")


def downgrade() -> None:
    raise NotImplementedError("Gunakan make db-reset untuk kembali ke versi sebelumnya.")
