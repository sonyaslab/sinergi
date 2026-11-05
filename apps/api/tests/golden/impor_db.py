"""Alur templat terisi lewat importer sungguhan: API impor (pratinjau -> terapkan) -> worker -> lk.hasil_lapus.

Dipakai test_golden.py (data rahasia golden/) dan test_golden_alur.py (data palsu). Tidak mencetak angka.
"""
from __future__ import annotations

from pathlib import Path

from sinergi_api.worker.antrean import proses_semua
from tests.conftest import tanpa_uid


def impor_dan_hitung(klien, h: dict, putaran: int, berkas: Path, uid_worker: int) -> dict:
    data = berkas.read_bytes()
    hd = {**tanpa_uid(h), "Content-Type": "application/octet-stream"}
    r = klien.post(f"/api/impor/templat?putaran_id={putaran}&nama={berkas.name}&setujui_penyesuaian=true",
                   content=data, headers=hd)
    assert r.status_code == 200, r.text
    p = r.json()
    galat = [f"{x.get('sheet')} baris {x.get('baris')} {x.get('kolom') or ''}: {x['teks']}" for x in p["pesan"]
             if x["tingkat"] == "galat"]
    assert not galat, "templat terisi masuk dengan galat format:\n" + "\n".join(galat[:30])
    r = klien.post(f"/api/impor/{p['impor_id']}/terapkan", content=data, headers=hd)
    assert r.status_code == 200, r.text
    proses_semua(uid_worker)
    return p


def benc_db(admin_conn, putaran: int, wilayah: str) -> dict[str, dict[int, tuple]]:
    out: dict[str, dict[int, tuple]] = {}
    for kode, u, *x in admin_conn.execute(
            "SELECT l.kode, p.urut, h.out_cp::float8, h.gva_cp::float8, h.out_k::float8, h.gva_k::float8"
            " FROM lk.hasil_lapus h JOIN ref.lapus l ON l.id = h.lapus_id JOIN ref.periode p ON p.id = h.periode_id"
            " WHERE h.putaran_id = %s AND h.wilayah_kode = %s AND h.tahap = 'BENC' AND l.jenis IN ('daun','top','sop')",
            (putaran, wilayah)).fetchall():
        out.setdefault(kode, {})[u] = tuple(x)
    return out
