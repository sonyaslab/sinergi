"""Worker antrean hitung.

F0: kerangka proses dan koneksi saja. Pekerjaan TIDAK diambil sebelum mesin hitung (F2) terpasang, agar job tetap
berstatus 'menunggu' dan tidak ada hasil palsu. Worker bekerja atas nama pengguna sistem `sistem.worker`.
"""
from __future__ import annotations

import logging
import signal
import time

from sqlalchemy import text

from ..app import db

log = logging.getLogger("sinergi.worker")
JEDA_DETIK = 5
_berhenti = False


def _stop(*_: object) -> None:
    global _berhenti
    _berhenti = True


def id_pengguna_worker() -> int:
    with db.engine_rw().connect() as conn:
        return conn.execute(text("SELECT id FROM sec.pengguna WHERE username = 'sistem.worker'")).scalar_one()


def jumlah_menunggu() -> int:
    with db.transaksi(id_pengguna_worker(), alasan="worker") as conn:
        return conn.execute(text("SELECT count(*) FROM lk.antrean_hitung WHERE status = 'menunggu'")).scalar_one()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    log.info("Worker SINERGI aktif (F0: mesin hitung belum terpasang; job tidak diambil).")
    terakhir = float("-inf")  # lapor segera pada iterasi pertama
    while not _berhenti:
        if time.monotonic() - terakhir > 300:
            try:
                log.info("Antrean menunggu: %d job", jumlah_menunggu())
            except Exception as e:  # noqa: BLE001 - worker tidak boleh mati karena DB sementara tidak tersedia
                log.warning("Basis data belum siap: %s", type(e).__name__)
            terakhir = time.monotonic()
        time.sleep(JEDA_DETIK)


if __name__ == "__main__":
    main()
