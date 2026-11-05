"""F1 Master data: hak tulis master, RLS master & hak akses, audit semua tabel master, nonaktif, keputusan metodologi.

- app_rw boleh INSERT/UPDATE/DELETE tabel master (hapus = nonaktifkan bila dipakai data, diputuskan di API).
- RLS: tulis ref.* hanya dengan izin master.kelola; tulis sec.peran/peran_izin/pengguna_peran dan lk.penugasan hanya
  dengan izin pengguna.kelola. Baca tetap terbuka (pembatasan baca di API).
- Audit: trigger pada tabel master yang belum diaudit; sec.pengguna diaudit tanpa hash sandi/rahasia TOTP dan tanpa
  pembukuan login (sudah dicatat aplikasi sebagai LOGIN/AKUN_TERKUNCI).
- Kolom aktif: ref.satuan, ref.sumber_data, ref.wilayah, sec.peran (peran nonaktif tidak memberi izin).
- ref.tahun_dasar.jangkar_dari_data: TD2025 = true (jangkar boleh dihitung dari data tahun dasar), TD2010 = false
  (jangkar wajib diisi; tahun baseline hanya titik awal rantai EKS). Dipakai mesin hitung F2.
- Baris PDRB.NM (PDRB tanpa migas) untuk TD2025; rumus PDRB - Σ NTB lapus is_migas (mesin F2).

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-05
"""
from __future__ import annotations

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

REF_MASTER = ["tahun_dasar", "wilayah", "lapus", "lapus_kelompok", "konkordansi_lapus", "katalog_komoditas", "satuan",
              "sumber_data", "validasi"]
AKSES = ["sec.peran", "sec.peran_izin", "sec.pengguna_peran", "lk.penugasan"]

IZIN_NAMA_DAFTAR = [
    ("master.kelola", "Kelola master data (tahun dasar, lapus, katalog, wilayah)"),
    ("pengguna.kelola", "Kelola pengguna, peran, dan penugasan"),
    ("putaran.kelola", "Buka dan atur putaran"),
    ("putaran.kunci", "Kunci putaran"),
    ("putaran.buka_kunci", "Buka kunci putaran"),
    ("data_dasar.isi", "Isi data dasar"),
    ("data_dasar.impor", "Impor templat data dasar"),
    ("item.tambah", "Tambah komoditas/rincian"),
    ("metode.pilih", "Pilih metode"),
    ("biaya_antara.isi", "Isi biaya antara"),
    ("penyesuaian.usul", "Usulkan adjustment"),
    ("penyesuaian.putus", "Putuskan adjustment"),
    ("lk.ajukan", "Ajukan LK"),
    ("lk.setujui", "Setujui atau kembalikan LK"),
    ("simulasi.edit", "Ubah simulasi akhir"),
    ("tabel_pokok.lihat", "Lihat tabel pokok"),
    ("dashboard.lihat", "Lihat dashboard"),
    ("ekspor.tabel_pokok", "Ekspor tabel pokok"),
    ("audit.lihat", "Lihat jejak audit"),
    ("data.tulis_semua", "Tulis data semua lapus dan wilayah"),
    ("rilis.impor", "Impor angka rilis"),
]
IZIN_NAMA = ", ".join(f"('{k}','{v}')" for k, v in IZIN_NAMA_DAFTAR)

# Teks fungsi HARUS sama persis dengan db/schema.sql (diuji tests/rls/test_skema_sinkron.py).
PUNYA_IZIN = """CREATE OR REPLACE FUNCTION sec.punya_izin(p_izin text) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = sec, pg_temp AS $$
  SELECT EXISTS (
    SELECT 1 FROM sec.pengguna_peran pp
    JOIN sec.peran pr ON pr.id = pp.peran_id AND pr.aktif
    JOIN sec.peran_izin pi ON pi.peran_id = pp.peran_id
    JOIN sec.pengguna u ON u.id = pp.pengguna_id AND u.aktif
    WHERE pp.pengguna_id = sec.uid() AND pi.izin_kode = p_izin)
$$;"""

CATAT_PENGGUNA = """CREATE OR REPLACE FUNCTION audit.catat_pengguna() RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER
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
END $$;"""


def upgrade() -> None:
    # Kolom baru
    op.execute("ALTER TABLE ref.tahun_dasar ADD COLUMN jangkar_dari_data boolean NOT NULL DEFAULT true")
    op.execute("UPDATE ref.tahun_dasar SET jangkar_dari_data = false WHERE kode = 'TD2010'")
    op.execute("COMMENT ON COLUMN ref.tahun_dasar.jangkar_dari_data IS 'true: jangkar (H_TD/IH_TD/RKA_TD DEF) boleh "
               "dihitung dari data tahun baseline bila kosong (TD2025); false: jangkar wajib diisi (TD2010, V03)'")
    for t in ("ref.wilayah", "ref.satuan", "ref.sumber_data", "sec.peran"):
        op.execute(f"ALTER TABLE {t} ADD COLUMN aktif boolean NOT NULL DEFAULT true")

    # Peran nonaktif tidak memberi izin
    op.execute(PUNYA_IZIN)

    # Hak tulis master (pembatasan per izin lewat RLS di bawah)
    op.execute("GRANT INSERT, UPDATE ON ref.tahun_dasar, ref.wilayah TO app_rw")
    op.execute("GRANT DELETE ON ref.tahun_dasar, ref.wilayah, ref.lapus, ref.lapus_kelompok, ref.konkordansi_lapus,"
               " ref.katalog_komoditas, ref.satuan, ref.sumber_data TO app_rw")

    # RLS master
    for t in REF_MASTER:
        op.execute(f"ALTER TABLE ref.{t} ENABLE ROW LEVEL SECURITY")
        op.execute(f"CREATE POLICY baca ON ref.{t} FOR SELECT USING (true)")
        op.execute(f"CREATE POLICY kelola ON ref.{t} FOR ALL USING (sec.punya_izin('master.kelola'))"
                   " WITH CHECK (sec.punya_izin('master.kelola'))")
    for t in AKSES:
        op.execute(f"ALTER TABLE {t} ENABLE ROW LEVEL SECURITY")
        op.execute(f"CREATE POLICY baca ON {t} FOR SELECT USING (true)")
        op.execute(f"CREATE POLICY kelola ON {t} FOR ALL USING (sec.punya_izin('pengguna.kelola'))"
                   " WITH CHECK (sec.punya_izin('pengguna.kelola'))")

    # Audit semua tabel master
    for t in ("ref.tahun_dasar", "ref.wilayah", "ref.lapus_kelompok", "ref.katalog_komoditas", "ref.satuan",
              "ref.sumber_data", "ref.validasi", "sec.peran"):
        op.execute(f"CREATE TRIGGER trg_audit AFTER INSERT OR UPDATE OR DELETE ON {t}"
                   " FOR EACH ROW EXECUTE FUNCTION audit.catat()")
    op.execute(CATAT_PENGGUNA)
    op.execute("CREATE TRIGGER trg_audit AFTER INSERT OR UPDATE OR DELETE ON sec.pengguna"
               " FOR EACH ROW EXECUTE FUNCTION audit.catat_pengguna()")

    # Nama izin yang mudah dibaca (kode tetap; dipakai layar Peran & Izin)
    op.execute("UPDATE sec.izin i SET nama = x.nama FROM (VALUES " + IZIN_NAMA + ") AS x(kode, nama)"
               " WHERE i.kode = x.kode")

    # Baris PDRB tanpa migas untuk TD2025 (keputusan metodologi; rumus di mesin F2)
    op.execute("INSERT INTO ref.lapus (tahun_dasar_id, kode, nama, level, urutan, jenis, is_migas, kode_lk_bps)"
               " VALUES ((SELECT id FROM ref.tahun_dasar WHERE kode='TD2025'),'PDRB.NM','PDRB Tanpa Migas',0,102,"
               "'pdrb_nonmigas',false,NULL)")


def downgrade() -> None:
    raise NotImplementedError("Gunakan make db-reset untuk kembali ke versi sebelumnya.")
