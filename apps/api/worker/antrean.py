"""Antrean hitung (lk.antrean_hitung) tanpa Redis: `SELECT … FOR UPDATE SKIP LOCKED`.

Satu job = hitung ulang satu (putaran, wilayah) penuh (cepat: < 1 detik per wilayah), sehingga graf dependensi
dan semua baris agregat selalu konsisten. Job lain yang menunggu untuk (putaran, wilayah) yang sama dan sudah
terlihat saat job diproses ikut ditandai selesai (digabung). Pesan galat tidak memuat angka PDRB.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from sqlalchemy import Connection, text

from ..app import db
from ..data_dasar import validasi_db
from ..engine import GalatMesin, HasilWilayah, hitung_wilayah
from .muat import STATUS_PRATINJAU, muat
from .tulis import tulis

log = logging.getLogger("sinergi.worker")
MACET_MENIT = 15  # job 'proses' lebih lama dari ini dianggap worker mati dan diambil ulang


@dataclass
class Job:
    id: int
    putaran_id: int
    wilayah_kode: str
    lapus_id: int | None


def antrekan(conn: Connection, putaran_id: int, wilayah: str, lapus_id: int | None, alasan: str) -> int | None:
    """Masukkan job hitung (dipanggil endpoint simpan data/item/penyesuaian). Tidak menggandakan job menunggu."""
    return conn.execute(text(
        "INSERT INTO lk.antrean_hitung (putaran_id, wilayah_kode, lapus_id, alasan)"
        " SELECT :p, :w, :l, :a WHERE NOT EXISTS (SELECT 1 FROM lk.antrean_hitung"
        "  WHERE putaran_id = :p AND wilayah_kode = :w AND status = 'menunggu') RETURNING id"),
        {"p": putaran_id, "w": wilayah, "l": lapus_id, "a": alasan}).scalar()


def ambil(conn: Connection) -> Job | None:
    r = conn.execute(text(
        "UPDATE lk.antrean_hitung SET status = 'proses', mulai_pada = now(), pesan = NULL"
        " WHERE id = (SELECT id FROM lk.antrean_hitung WHERE status = 'menunggu'"
        f"  OR (status = 'proses' AND mulai_pada < now() - interval '{MACET_MENIT} minutes')"
        "  ORDER BY dibuat_pada, id FOR UPDATE SKIP LOCKED LIMIT 1)"
        " RETURNING id, putaran_id, wilayah_kode, lapus_id")).first()
    return None if r is None else Job(r.id, r.putaran_id, r.wilayah_kode.strip(), r.lapus_id)


def hitung_dan_tulis(conn: Connection, putaran_id: int, wilayah: str) -> dict[str, int]:
    conn.execute(text("SELECT pg_advisory_xact_lock(hashtextextended('hitung:' || :p || ':' || :w, 0))"),
                 {"p": putaran_id, "w": wilayah})
    m, pu = muat(conn, putaran_id, wilayah)
    h = hitung_wilayah(m)
    n = tulis(conn, pu, wilayah, m, h)
    n["hasil_validasi"] = validasi_db.jalankan(conn, putaran_id, wilayah, pu.awal, pu.akhir, m, h)
    return n


def pratinjau(conn: Connection, putaran_id: int, wilayah: str) -> HasilWilayah:
    """Hitung dengan penyesuaian draf/diajukan untuk layar LK Hitung. TIDAK disimpan (keputusan 8a)."""
    m, _ = muat(conn, putaran_id, wilayah, STATUS_PRATINJAU)
    return hitung_wilayah(m)


def _tandai(uid: int, job: Job, status: str, pesan: str) -> None:
    with db.transaksi(uid, alasan=f"worker: job {job.id} {status}") as c:
        c.execute(text("UPDATE lk.antrean_hitung SET status = :s, selesai_pada = now(), pesan = :m WHERE id = :id"),
                  {"s": status, "m": pesan, "id": job.id})


def _sqlstate(e: BaseException) -> str | None:
    """SQLSTATE dari galat psycopg langsung (COPY) atau yang dibungkus SQLAlchemy."""
    for x in (e, getattr(e, "orig", None)):
        kode = getattr(x, "sqlstate", None)
        if kode:
            return str(kode)
    return None


def proses_satu(uid: int) -> Job | None:
    """Ambil dan proses satu job. Kembalikan job yang diproses, atau None bila antrean kosong."""
    with db.transaksi(uid, alasan="worker: ambil job") as c:
        job = ambil(c)
    if job is None:
        return None
    try:
        with db.transaksi(uid, alasan=f"hitung otomatis (job {job.id})") as c:
            gabung = [r[0] for r in c.execute(text(
                "SELECT id FROM lk.antrean_hitung WHERE putaran_id = :p AND wilayah_kode = :w"
                " AND status = 'menunggu' AND id <> :id FOR UPDATE SKIP LOCKED"),
                {"p": job.putaran_id, "w": job.wilayah_kode, "id": job.id})]
            n = hitung_dan_tulis(c, job.putaran_id, job.wilayah_kode)
            pesan = f"{n['hasil_lapus']} baris hasil lapus, {n['hasil_validasi']} temuan validasi"
            c.execute(text("UPDATE lk.antrean_hitung SET status = 'selesai', selesai_pada = now(),"
                           " pesan = CASE WHEN id = :id THEN :m ELSE 'digabung ke job ' || :id END"
                           " WHERE id = ANY(:ids)"), {"id": job.id, "m": pesan, "ids": [job.id, *gabung]})
        log.info("Job %d selesai (putaran %d, wilayah %s, %d job digabung)", job.id, job.putaran_id,
                 job.wilayah_kode, len(gabung))
    except GalatMesin as e:
        _tandai(uid, job, "gagal", str(e))
        log.warning("Job %d gagal: %s", job.id, e)
    except Exception as e:  # noqa: BLE001 - worker tidak boleh mati; rincian di log (tanpa angka)
        kode = _sqlstate(e)
        if kode == "P0423":
            pesan = "Putaran terkunci; hasil tidak diubah."
        elif kode:
            pesan = f"Galat basis data ({kode})."
        else:
            pesan = "Galat internal mesin hitung."
        _tandai(uid, job, "gagal", pesan)
        if kode:
            log.warning("Job %d gagal: %s", job.id, pesan)
        else:
            log.exception("Job %d gagal (galat internal)", job.id)
    return job


def proses_semua(uid: int, maks: int = 1000) -> int:
    """Kuras antrean (dipakai `python -m sinergi_api.worker --sekali` dan uji)."""
    n = 0
    while n < maks and proses_satu(uid) is not None:
        n += 1
    return n
