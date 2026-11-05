"""Worker antrean hitung SINERGI.

Mengambil job dari lk.antrean_hitung, menghitung ulang (putaran, wilayah) dengan mesin hitung, lalu menulis
lk.hasil_item, lk.hasil_metode, lk.hasil_lapus beserta versi_mesin dan hash_input. Bekerja atas nama pengguna
sistem `sistem.worker` (app_rw, RLS berlaku).

    python -m sinergi_api.worker            # layanan (loop)
    python -m sinergi_api.worker --sekali   # kuras antrean lalu keluar
"""
from __future__ import annotations

import argparse
import logging
import signal
import time

from sqlalchemy import text

from ..app import db
from ..engine import VERSI_MESIN
from .antrean import proses_satu, proses_semua

log = logging.getLogger("sinergi.worker")
JEDA_DETIK = 2
_berhenti = False


def _stop(*_: object) -> None:
    global _berhenti
    _berhenti = True


def id_pengguna_worker() -> int:
    with db.engine_rw().connect() as conn:
        return conn.execute(text("SELECT id FROM sec.pengguna WHERE username = 'sistem.worker'")).scalar_one()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="sinergi_api.worker")
    ap.add_argument("--sekali", action="store_true", help="kuras antrean lalu keluar")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    if a.sekali:
        n = proses_semua(id_pengguna_worker())
        log.info("%d job diproses", n)
        return 0
    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    log.info("Worker SINERGI aktif (mesin hitung versi %s).", VERSI_MESIN)
    uid: int | None = None
    while not _berhenti:
        try:
            uid = uid or id_pengguna_worker()
            if proses_satu(uid) is None:
                time.sleep(JEDA_DETIK)
        except Exception as e:  # noqa: BLE001 - worker tidak boleh mati karena DB sementara tidak tersedia
            log.warning("Basis data belum siap: %s", type(e).__name__)
            time.sleep(JEDA_DETIK * 5)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
