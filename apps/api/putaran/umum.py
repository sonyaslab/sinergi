"""Utilitas bersama F4 (putaran, status lapus, penyesuaian): muat putaran, cek terbuka/terkunci, label periode."""
from __future__ import annotations

from sqlalchemy import Connection, text

from ..app.galat import GalatSinergi
from ..master.umum import tidak_ada

BERDATA = ("daun", "top", "sop")


def label(u: int) -> str:
    return f"Q{u % 4 + 1}-{u // 4}"


def ambil_putaran(conn: Connection, putaran_id: int) -> dict:
    r = conn.execute(text(
        "SELECT p.id, p.tahun_dasar_id, p.nama, p.jenis, p.status, p.tahun, p.triwulan, p.nomor, p.catatan,"
        " p.tanggal_cutoff, p.tanggal_cutoff IS NOT NULL AND now() > p.tanggal_cutoff AS lewat_cutoff,"
        " p.sumber_putaran_id, p.dibuka_pada, p.dikunci_pada, pa.urut AS awal, pz.urut AS akhir, t.kode AS td_kode,"
        " t.tahun_awal_seri, t.tahun_baseline_eks, t.jangkar_dari_data FROM lk.putaran p"
        " JOIN ref.periode pa ON pa.id = p.periode_awal_id JOIN ref.periode pz ON pz.id = p.periode_akhir_id"
        " JOIN ref.tahun_dasar t ON t.id = p.tahun_dasar_id WHERE p.id = :p"), {"p": putaran_id}).mappings().first()
    if r is None:
        raise tidak_ada("Putaran")
    return dict(r)


def pastikan_terbuka(p: dict) -> None:
    if p["status"] == "terkunci":
        raise GalatSinergi(423, "PUTARAN_TERKUNCI", "Putaran sudah dikunci. Perubahan tidak dapat disimpan.")


def lapus_td(conn: Connection, td: int, lapus_id: int) -> dict:
    r = conn.execute(text("SELECT id, kode, nama, jenis, induk_id, level, urutan FROM ref.lapus WHERE id = :l"
                          " AND tahun_dasar_id = :td"), {"l": lapus_id, "td": td}).mappings().first()
    if r is None:
        raise tidak_ada("Lapus")
    return dict(r)


def boleh_tulis(conn: Connection, wilayah: str, lapus_id: int) -> bool:
    return bool(conn.execute(text("SELECT lk.boleh_tulis(CAST(:w AS char(4)), :l)"),
                             {"w": wilayah, "l": lapus_id}).scalar())


def cek_tulis(conn: Connection, wilayah: str, lapus_id: int) -> None:
    if not boleh_tulis(conn, wilayah, lapus_id):
        raise GalatSinergi(403, "TIDAK_DITUGASKAN", "Lapus/wilayah ini tidak ditugaskan kepada Anda.")


def setel_alasan(conn: Connection, alasan: str | None) -> None:
    """Alasan perubahan untuk trigger audit (dan syarat kunci/buka kunci/cut-off) di transaksi berjalan."""
    if alasan:
        conn.execute(text("SELECT set_config('app.alasan', :a, true)"), {"a": alasan[:500]})


def peta_periode(conn: Connection) -> dict[int, int]:
    """urut -> id ref.periode."""
    return {int(u): int(i) for u, i in conn.execute(text("SELECT urut, id FROM ref.periode"))}
