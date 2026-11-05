"""Tulis hasil mesin ke lk.hasil_item, lk.hasil_metode, lk.hasil_lapus (satu transaksi, ganti seluruh wilayah).

Hanya periode putaran yang ditulis (sumbu hitung boleh lebih lebar karena mencakup tahun baseline).
Putaran terkunci ditolak trigger basis data (SQLSTATE P0423).
"""
from __future__ import annotations

from sqlalchemy import Connection, text

from ..engine import HasilWilayah, MasukanWilayah
from ..engine.model import METODE_HITUNG
from .muat import InfoPutaran


def _peta_periode(conn: Connection, awal: int, akhir: int) -> dict[int, int]:
    return {u: pid for pid, u in conn.execute(
        text("SELECT id, urut FROM ref.periode WHERE urut BETWEEN :a AND :b"), {"a": awal, "b": akhir})}


def tulis(conn: Connection, pu: InfoPutaran, wilayah: str, m: MasukanWilayah, h: HasilWilayah) -> dict[str, int]:
    q = {"p": pu.id, "w": wilayah, "td": pu.tahun_dasar_id}
    conn.execute(text("DELETE FROM lk.hasil_lapus WHERE putaran_id = :p AND wilayah_kode = :w"), q)
    conn.execute(text("DELETE FROM lk.hasil_metode WHERE putaran_id = :p AND wilayah_kode = :w"), q)
    conn.execute(text("DELETE FROM lk.hasil_item h USING lk.item i WHERE h.putaran_id = :p AND i.id = h.item_id"
                      " AND i.wilayah_kode = :w AND i.tahun_dasar_id = :td"), q)
    per = _peta_periode(conn, pu.awal, pu.akhir)
    sb = h.sumbu
    idx = [(per[u], sb.i(u)) for u in range(pu.awal, pu.akhir + 1)]
    raw = conn.connection.driver_connection
    assert raw is not None
    n = {"hasil_lapus": 0, "hasil_metode": 0, "hasil_item": 0}
    with raw.cursor() as cur:
        with cur.copy("COPY lk.hasil_lapus (putaran_id, wilayah_kode, lapus_id, periode_id, tahap, out_cp, gva_cp,"
                      " out_k, gva_k, versi_mesin, hash_input) FROM STDIN") as cp:
            for lid, hl in h.lapus.items():
                for tahap, e in hl.tahap.items():
                    for pid, t in idx:
                        cp.write_row((pu.id, wilayah, lid, pid, tahap, e.out_cp[t], e.gva_cp[t], e.out_k[t],
                                      e.gva_k[t], h.versi_mesin, hl.hash_input))
                        n["hasil_lapus"] += 1
        with cur.copy("COPY lk.hasil_metode (putaran_id, wilayah_kode, lapus_id, metode_kode, periode_id,"
                      " out_cp_pr, gva_cp_pr, out_k_pr, gva_k_pr, out_cp_pre, gva_cp_pre, out_k_pre, gva_k_pre)"
                      " FROM STDIN") as cp:
            for lid, hl in h.lapus.items():
                d = m.data.get(lid)
                if d is None or not hl.metode:
                    continue
                dipakai = {i.metode for i in d.item} | {a.metode for a in d.penyesuaian if a.tahap == "METODE"}
                for mt in METODE_HITUNG:
                    if mt not in dipakai:
                        continue
                    pr, pre = hl.metode[mt]
                    for pid, t in idx:
                        cp.write_row((pu.id, wilayah, lid, mt, pid, pr.out_cp[t], pr.gva_cp[t], pr.out_k[t],
                                      pr.gva_k[t], pre.out_cp[t], pre.gva_cp[t], pre.out_k[t], pre.gva_k[t]))
                        n["hasil_metode"] += 1
        with cur.copy("COPY lk.hasil_item (putaran_id, item_id, periode_id, out_cp, gva_cp, out_k, gva_k)"
                      " FROM STDIN") as cp:
            for hl in h.lapus.values():
                for iid, e in hl.item.items():
                    for pid, t in idx:
                        cp.write_row((pu.id, iid, pid, e.out_cp[t], e.gva_cp[t], e.out_k[t], e.gva_k[t]))
                        n["hasil_item"] += 1
    return n
