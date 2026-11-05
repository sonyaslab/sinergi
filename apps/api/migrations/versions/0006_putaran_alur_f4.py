"""F4 Putaran dan alur: cut-off, kunci/buka kunci beralasan, status lapus DIKECUALIKAN, RLS alur, biaya antara.

- lk.putaran.tanggal_cutoff: perubahan data dasar (nilai, jangkar, seri referensi) sesudah cut-off wajib beralasan
  (app.alasan >= 10 karakter; SQLSTATE P0428 -> HTTP 422) dan tercatat di audit (temuan E5).
- lk.putaran: RLS (baca semua; buka = putaran.kelola; ubah = putaran.kelola/kunci/buka_kunci). Trigger lk.cek_putaran:
  putaran terkunci tidak dapat diubah atau dihapus (P0423); masuk/keluar status terkunci wajib beralasan dan berizin
  (putaran.kunci / putaran.buka_kunci). Konteks tanpa pengguna aplikasi (pemilik, pemeliharaan) tidak diperiksa izin.
- lk.tolak_jika_terkunci: celah app.izin_buka_kunci dihapus (tidak dipakai aplikasi; buka kunci = ubah status
  putaran). Kunci dibaca di bawah advisory lock bersama per putaran; kunci putaran memegang advisory lock eksklusif,
  sehingga tidak ada tulis yang lolos di antara pemeriksaan syarat kunci dan perubahan status.
- lk.hasil_validasi dan lk.riwayat_status ikut ditolak saat putaran terkunci.
- lk.status_lapus menerima 'dikecualikan' (keputusan 2: V14 TOP/SOP dikecualikan admin, catatan wajib). Trigger
  lk.cek_status_lapus: disetujui hanya oleh lk.setujui; dikecualikan hanya oleh putaran.kelola; nihil/dikecualikan/
  dikembalikan wajib catatan >= 10 karakter.
- lk.penyesuaian: trigger lk.cek_putus_penyesuaian: status disetujui/ditolak (atau mengubah nilai/alasan
  penyesuaian yang sudah diputus) hanya oleh pemegang izin penyesuaian.putus.
- RLS lk.status_lapus, lk.riwayat_status, lk.struktur_biaya (operator lapus yang ditugaskan, pemeriksa).

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-05
"""
from __future__ import annotations

from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None

BACA = "sec.uid() IS NOT NULL OR current_user = 'app_ro'"
# Teks fungsi HARUS sama persis dengan db/schema.sql (diuji tests/rls/test_skema_sinkron.py).
FUNGSI = [
    """CREATE OR REPLACE FUNCTION lk.tolak_jika_terkunci() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE v_status text; v_pid bigint;
BEGIN
  v_pid := CASE WHEN TG_OP = 'DELETE' THEN OLD.putaran_id ELSE NEW.putaran_id END;
  -- Advisory lock bersama: kunci putaran (eksklusif) menunggu semua tulis yang sedang berjalan selesai.
  PERFORM pg_advisory_xact_lock_shared(hashtextextended('putaran:' || v_pid, 0));
  SELECT status INTO v_status FROM lk.putaran WHERE id = v_pid;
  IF v_status = 'terkunci' THEN
    RAISE EXCEPTION 'Putaran % terkunci', v_pid USING ERRCODE = 'P0423';
  END IF;
  RETURN CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END;
END $$;""",
    """CREATE OR REPLACE FUNCTION lk.cek_cutoff() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE v_cutoff timestamptz; v_pid bigint;
BEGIN
  v_pid := CASE WHEN TG_OP = 'DELETE' THEN OLD.putaran_id ELSE NEW.putaran_id END;
  SELECT tanggal_cutoff INTO v_cutoff FROM lk.putaran WHERE id = v_pid;
  IF v_cutoff IS NOT NULL AND now() > v_cutoff
     AND coalesce(length(trim(current_setting('app.alasan', true))), 0) < 10 THEN
    RAISE EXCEPTION 'Putaran sudah melewati cut-off; perubahan data dasar wajib beralasan (min. 10 karakter)'
      USING ERRCODE = 'P0428';
  END IF;
  RETURN CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END;
END $$;""",
    """CREATE OR REPLACE FUNCTION lk.cek_putaran() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    IF OLD.status = 'terkunci' THEN
      RAISE EXCEPTION 'Putaran % terkunci', OLD.id USING ERRCODE = 'P0423';
    END IF;
    RETURN OLD;
  END IF;
  IF OLD.status = 'terkunci' AND NEW.status = 'terkunci' THEN
    RAISE EXCEPTION 'Putaran % terkunci', OLD.id USING ERRCODE = 'P0423';
  END IF;
  IF (OLD.status = 'terkunci') <> (NEW.status = 'terkunci') AND sec.uid() IS NOT NULL THEN
    IF coalesce(length(trim(current_setting('app.alasan', true))), 0) < 10 THEN
      RAISE EXCEPTION 'Kunci dan buka kunci putaran wajib beralasan (min. 10 karakter)'
        USING ERRCODE = 'check_violation';
    END IF;
    IF NEW.status = 'terkunci' AND NOT sec.punya_izin('putaran.kunci') THEN
      RAISE EXCEPTION 'Tidak berhak mengunci putaran' USING ERRCODE = 'insufficient_privilege';
    END IF;
    IF OLD.status = 'terkunci' AND NOT sec.punya_izin('putaran.buka_kunci') THEN
      RAISE EXCEPTION 'Tidak berhak membuka kunci putaran' USING ERRCODE = 'insufficient_privilege';
    END IF;
  END IF;
  RETURN NEW;
END $$;""",
    """CREATE OR REPLACE FUNCTION lk.cek_status_lapus() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE v_baru boolean;
BEGIN
  v_baru := TG_OP = 'INSERT' OR OLD.status IS DISTINCT FROM NEW.status;
  IF v_baru AND NEW.status IN ('nihil','dikecualikan','dikembalikan')
     AND coalesce(length(trim(NEW.catatan)), 0) < 10 THEN
    RAISE EXCEPTION 'Catatan wajib diisi (min. 10 karakter)' USING ERRCODE = 'check_violation';
  END IF;
  IF v_baru AND sec.uid() IS NOT NULL THEN
    IF NEW.status = 'disetujui' AND NOT sec.punya_izin('lk.setujui') THEN
      RAISE EXCEPTION 'Tidak berhak menyetujui lapus' USING ERRCODE = 'insufficient_privilege';
    END IF;
    IF NEW.status = 'dikecualikan' AND NOT sec.punya_izin('putaran.kelola') THEN
      RAISE EXCEPTION 'Status DIKECUALIKAN hanya oleh admin' USING ERRCODE = 'insufficient_privilege';
    END IF;
  END IF;
  RETURN NEW;
END $$;""",
    """CREATE OR REPLACE FUNCTION lk.cek_putus_penyesuaian() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF sec.uid() IS NULL OR sec.punya_izin('penyesuaian.putus') THEN
    RETURN NEW;
  END IF;
  IF NEW.status IN ('disetujui','ditolak') AND (TG_OP = 'INSERT' OR OLD.status IS DISTINCT FROM NEW.status
     OR OLD.nilai IS DISTINCT FROM NEW.nilai OR OLD.alasan IS DISTINCT FROM NEW.alasan) THEN
    RAISE EXCEPTION 'Penyesuaian yang sudah diputus hanya dapat diubah pemegang izin memutus'
      USING ERRCODE = 'insufficient_privilege';
  END IF;
  RETURN NEW;
END $$;""",
]
# (nama kebijakan, tabel, ekspresi tulis) — per perintah (bukan FOR ALL; lihat migrasi 0005).
KEBIJAKAN_TULIS = [
    ("tulis_status", "lk.status_lapus", "lk.boleh_tulis(wilayah_kode, lapus_id) OR sec.punya_izin('lk.setujui')"
                                        " OR sec.punya_izin('penyesuaian.putus') OR sec.punya_izin('putaran.kelola')"),
    ("tulis_biaya", "lk.struktur_biaya", "lk.boleh_tulis(wilayah_kode, lapus_id) OR sec.punya_izin('lk.setujui')"),
]
UBAH_PUTARAN = ("sec.punya_izin('putaran.kelola') OR sec.punya_izin('putaran.kunci')"
                " OR sec.punya_izin('putaran.buka_kunci')")


def upgrade() -> None:
    op.execute("ALTER TABLE lk.putaran ADD COLUMN tanggal_cutoff timestamptz")
    op.execute("ALTER TABLE lk.status_lapus DROP CONSTRAINT status_lapus_status_check")
    op.execute("ALTER TABLE lk.status_lapus ADD CONSTRAINT status_lapus_status_check CHECK (status IN"
               " ('belum','draf','diajukan','disetujui','dikembalikan','nihil','dikecualikan'))")
    for f in FUNGSI:
        op.execute(f)

    op.execute("CREATE TRIGGER trg_putaran_cek BEFORE UPDATE OR DELETE ON lk.putaran"
               " FOR EACH ROW EXECUTE FUNCTION lk.cek_putaran()")
    op.execute("CREATE TRIGGER trg_status_lapus_cek BEFORE INSERT OR UPDATE ON lk.status_lapus"
               " FOR EACH ROW EXECUTE FUNCTION lk.cek_status_lapus()")
    op.execute("CREATE TRIGGER trg_penyesuaian_putus BEFORE INSERT OR UPDATE ON lk.penyesuaian"
               " FOR EACH ROW EXECUTE FUNCTION lk.cek_putus_penyesuaian()")
    for t in ("hasil_validasi", "riwayat_status"):
        op.execute(f"CREATE TRIGGER trg_{t}_kunci BEFORE INSERT OR UPDATE OR DELETE ON lk.{t}"
                   " FOR EACH ROW EXECUTE FUNCTION lk.tolak_jika_terkunci()")
    for t in ("nilai_item", "parameter_item", "nilai_seri_referensi"):
        op.execute(f"CREATE TRIGGER trg_{t}_cutoff BEFORE INSERT OR UPDATE OR DELETE ON lk.{t}"
                   " FOR EACH ROW EXECUTE FUNCTION lk.cek_cutoff()")

    # RLS putaran: metadata putaran boleh dibaca siapa pun (dipakai trigger kunci/cut-off pada setiap konteks).
    op.execute("ALTER TABLE lk.putaran ENABLE ROW LEVEL SECURITY")
    op.execute("CREATE POLICY baca_putaran ON lk.putaran FOR SELECT USING (true)")
    op.execute("CREATE POLICY tulis_putaran_i ON lk.putaran FOR INSERT WITH CHECK (sec.punya_izin('putaran.kelola'))")
    op.execute(f"CREATE POLICY tulis_putaran_u ON lk.putaran FOR UPDATE USING ({UBAH_PUTARAN})"
               f" WITH CHECK ({UBAH_PUTARAN})")
    op.execute("CREATE POLICY tulis_putaran_d ON lk.putaran FOR DELETE USING (sec.punya_izin('putaran.kelola'))")

    for nama, tabel, ekspr in KEBIJAKAN_TULIS:
        op.execute(f"ALTER TABLE {tabel} ENABLE ROW LEVEL SECURITY")
        op.execute(f"CREATE POLICY baca_{nama[6:]} ON {tabel} FOR SELECT USING ({BACA})")
        op.execute(f"CREATE POLICY {nama}_i ON {tabel} FOR INSERT WITH CHECK ({ekspr})")
        op.execute(f"CREATE POLICY {nama}_u ON {tabel} FOR UPDATE USING ({ekspr}) WITH CHECK ({ekspr})")
        op.execute(f"CREATE POLICY {nama}_d ON {tabel} FOR DELETE USING ({ekspr})")
    op.execute("ALTER TABLE lk.riwayat_status ENABLE ROW LEVEL SECURITY")
    op.execute(f"CREATE POLICY baca_riwayat ON lk.riwayat_status FOR SELECT USING ({BACA})")
    op.execute(f"CREATE POLICY tulis_riwayat_i ON lk.riwayat_status FOR INSERT WITH CHECK ({KEBIJAKAN_TULIS[0][2]})")


def downgrade() -> None:
    raise NotImplementedError("Gunakan make db-reset untuk kembali ke versi sebelumnya.")
