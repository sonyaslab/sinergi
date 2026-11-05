"""Layar LK Hitung NTB (per lapus) dan Kompilasi & Simulasi (lapus x triwulan).

Angka resmi dibaca dari lk.hasil_* (hanya penyesuaian disetujui). Sakelar pratinjau menghitung di memori dengan
penyesuaian draf/diajukan/disetujui (`antrean.pratinjau`), TIDAK disimpan, dan dilabeli "PRATINJAU – belum resmi"
di layar (keputusan 8a; tidak pernah dipakai tabel pokok/dashboard/ekspor).
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import Connection, text

from ..app.deps import Pengguna, butuh_izin, koneksi
from ..engine import Empat, HasilWilayah
from ..master.umum import tidak_valid
from ..worker.antrean import pratinjau as hitung_pratinjau
from .penyesuaian import putus_penyesuaian
from .status import status_sekarang
from .umum import BERDATA, ambil_putaran, boleh_tulis, label, lapus_td, pastikan_terbuka

router = APIRouter(prefix="/api", tags=["hasil"])
BACA = Depends(butuh_izin("data_dasar.isi", "lk.setujui", "simulasi.edit", "penyesuaian.usul", "penyesuaian.putus"))
Empat4 = list[float]


def _periode(p: dict) -> list[dict]:
    return [{"urut": u, "label": label(u)} for u in range(p["awal"], p["akhir"] + 1)]


def _empat(e: Empat, h: HasilWilayah, p: dict) -> dict[str, Empat4]:
    return {str(u): [e.out_cp[h.sumbu.i(u)], e.gva_cp[h.sumbu.i(u)], e.out_k[h.sumbu.i(u)], e.gva_k[h.sumbu.i(u)]]
            for u in range(p["awal"], p["akhir"] + 1)}


# ======================================================================== LK Hitung (satu lapus)
@router.get("/hasil/lapus/{lapus_id}")
def hasil_lapus(lapus_id: int, putaran_id: int, wilayah: str, pratinjau: bool = False,
                conn: Connection = Depends(koneksi), _: Pengguna = BACA) -> dict:
    """Ringkasan PR -> PRE -> POST -> BENC (-> FINAL) per metode dan item, penyesuaian, status, temuan validasi.

    Nilai per periode = [output ADHB, NTB ADHB, output ADHK, NTB ADHK].
    """
    p = ambil_putaran(conn, putaran_id)
    lap = lapus_td(conn, p["tahun_dasar_id"], lapus_id)
    if lap["jenis"] not in BERDATA:
        raise tidak_valid("LK Hitung hanya untuk lapus berdata (daun, TOP, SOP).")
    q = {"p": putaran_id, "w": wilayah, "l": lapus_id, "td": p["tahun_dasar_id"]}
    item = [dict(r) for r in conn.execute(text(
        "SELECT i.id, i.metode_kode AS metode, i.nomor, i.nama, i.status, i.satuan_kode, pm.urut AS mulai,"
        " ps.urut AS selesai FROM lk.item i LEFT JOIN ref.periode pm ON pm.id = i.periode_mulai_id"
        " LEFT JOIN ref.periode ps ON ps.id = i.periode_selesai_id WHERE i.tahun_dasar_id = :td"
        " AND i.wilayah_kode = :w AND i.lapus_id = :l AND i.metode_kode IN ('REV','EKS','DEF')"
        " ORDER BY array_position(ARRAY['REV','EKS','DEF'], i.metode_kode), i.nomor"), q).mappings()]
    tahap: dict[str, dict[str, Empat4]] = {}
    metode: dict[str, dict[str, dict[str, Empat4]]] = {}
    per_item: dict[int, dict[str, Empat4]] = defaultdict(dict)
    if pratinjau:
        h = hitung_pratinjau(conn, putaran_id, wilayah)
        hl = h.lapus.get(lapus_id)
        if hl is not None:
            tahap = {k: _empat(e, h, p) for k, e in hl.tahap.items()}
            dipakai = {i["metode"] for i in item}
            for m, (pr, pre) in hl.metode.items():
                d_pr, d_pre = _empat(pr, h, p), _empat(pre, h, p)
                if m in dipakai or d_pr != d_pre:  # sama dengan tulis.py: metode berisi item atau penyesuaian
                    metode[m] = {"pr": d_pr, "pre": d_pre}
            for iid, e in hl.item.items():
                per_item[iid] = _empat(e, h, p)
    else:
        for th, u, *v in conn.execute(text(
                "SELECT h.tahap, pe.urut, h.out_cp::float8, h.gva_cp::float8, h.out_k::float8, h.gva_k::float8"
                " FROM lk.hasil_lapus h JOIN ref.periode pe ON pe.id = h.periode_id WHERE h.putaran_id = :p"
                " AND h.wilayah_kode = :w AND h.lapus_id = :l"), q):
            tahap.setdefault(th, {})[str(u)] = list(v)
        for m, u, *v in conn.execute(text(
                "SELECT h.metode_kode, pe.urut, h.out_cp_pr::float8, h.gva_cp_pr::float8, h.out_k_pr::float8,"
                " h.gva_k_pr::float8, h.out_cp_pre::float8, h.gva_cp_pre::float8, h.out_k_pre::float8,"
                " h.gva_k_pre::float8 FROM lk.hasil_metode h JOIN ref.periode pe ON pe.id = h.periode_id"
                " WHERE h.putaran_id = :p AND h.wilayah_kode = :w AND h.lapus_id = :l"), q):
            d = metode.setdefault(m, {"pr": {}, "pre": {}})
            d["pr"][str(u)], d["pre"][str(u)] = list(v[:4]), list(v[4:])
        for iid, u, *v in conn.execute(text(
                "SELECT h.item_id, pe.urut, h.out_cp::float8, h.gva_cp::float8, h.out_k::float8, h.gva_k::float8"
                " FROM lk.hasil_item h JOIN ref.periode pe ON pe.id = h.periode_id WHERE h.putaran_id = :p"
                " AND h.item_id = ANY(:i)"), {**q, "i": [i["id"] for i in item]}):
            per_item[iid][str(u)] = list(v)
    for it in item:
        it["nilai"] = per_item.get(it["id"], {})
    temuan = [dict(r) for r in conn.execute(text(
        "SELECT h.kode_validasi AS kode, h.tingkat, h.item_id, h.jenis_seri, pe.urut AS periode, h.pesan,"
        " h.dikonfirmasi_oleh IS NOT NULL AS dikonfirmasi FROM lk.hasil_validasi h"
        " LEFT JOIN ref.periode pe ON pe.id = h.periode_id WHERE h.putaran_id = :p AND h.wilayah_kode = :w"
        " AND h.lapus_id = :l ORDER BY array_position(ARRAY['blokir_kunci','blokir_ajukan','peringatan','info'],"
        " h.tingkat), h.kode_validasi, h.id"), q).mappings()]
    return {"putaran": {k: p[k] for k in ("id", "nama", "status", "awal", "akhir", "td_kode")},
            "lapus": lap, "periode": _periode(p), "pratinjau": pratinjau, "tahap": tahap, "metode": metode,
            "item": item, "status": status_sekarang(conn, putaran_id, wilayah, lapus_id), "validasi": temuan,
            "boleh_tulis": boleh_tulis(conn, wilayah, lapus_id)}


# ======================================================================== Kompilasi & Simulasi (lapus x triwulan)
@router.get("/kompilasi")
def kompilasi(putaran_id: int, wilayah: str, pratinjau: bool = False, conn: Connection = Depends(koneksi),
              _: Pengguna = BACA) -> dict:
    """Semua baris pohon (format tetap): NTB BENC (kompilasi) dan FINAL [ADHB, ADHK] per triwulan + isian SIM.

    Simulasi hanya diisi pada lapus berdata; baris agregat = jumlah lapus berdata (docs/02 §6).
    """
    p = ambil_putaran(conn, putaran_id)
    q = {"p": putaran_id, "w": wilayah, "td": p["tahun_dasar_id"]}
    baris = [dict(r) | {"berdata": r["jenis"] in BERDATA, "benc": {}, "final": {}} for r in conn.execute(text(
        "SELECT id, kode, nama, level, jenis, induk_id FROM ref.lapus WHERE tahun_dasar_id = :td AND aktif"
        " ORDER BY urutan"), q).mappings()]
    per = {b["id"]: b for b in baris}
    if pratinjau:
        h = hitung_pratinjau(conn, putaran_id, wilayah)
        for lid, hl in h.lapus.items():
            if lid not in per:
                continue
            for th in ("BENC", "FINAL"):
                if th in hl.tahap:
                    e = hl.tahap[th]
                    per[lid][th.lower()] = {str(u): [e.gva_cp[h.sumbu.i(u)], e.gva_k[h.sumbu.i(u)]]
                                            for u in range(p["awal"], p["akhir"] + 1)}
    else:
        for lid, th, u, cp, k in conn.execute(text(
                "SELECT h.lapus_id, h.tahap, pe.urut, h.gva_cp::float8, h.gva_k::float8 FROM lk.hasil_lapus h"
                " JOIN ref.periode pe ON pe.id = h.periode_id WHERE h.putaran_id = :p AND h.wilayah_kode = :w"
                " AND h.tahap IN ('BENC','FINAL')"), q):
            if lid in per:
                per[lid][th.lower()][str(u)] = [cp, k]
    sim = [dict(r) for r in conn.execute(text(
        "SELECT a.id, a.lapus_id, a.harga, pe.urut AS periode, a.nilai::float8 AS nilai, a.status, a.alasan,"
        " a.catatan_putusan FROM lk.penyesuaian a JOIN ref.periode pe ON pe.id = a.periode_id"
        " WHERE a.putaran_id = :p AND a.wilayah_kode = :w AND a.tahap = 'SIMULASI' ORDER BY a.lapus_id, pe.urut"),
        q).mappings()]
    antre = conn.execute(text("SELECT count(*) FROM lk.antrean_hitung WHERE putaran_id = :p AND wilayah_kode = :w"
                              " AND status IN ('menunggu','proses')"), q).scalar_one()
    return {"putaran": {k: p[k] for k in ("id", "nama", "status", "awal", "akhir", "td_kode")},
            "periode": _periode(p), "pratinjau": pratinjau, "baris": baris, "simulasi": sim,
            "antrean": int(antre)}


class SetujuiSimIn(BaseModel):
    putaran_id: int
    wilayah: str = Field(min_length=4, max_length=4)
    catatan: str | None = Field(default=None, max_length=500)


@router.post("/simulasi/setujui")
def setujui_simulasi(data: SetujuiSimIn, conn: Connection = Depends(koneksi),
                     _: Pengguna = Depends(butuh_izin("penyesuaian.putus"))) -> dict[str, Any]:
    """SETUJUI simulasi: semua SIM draf/diajukan satu wilayah disetujui (masuk tahap FINAL)."""
    pastikan_terbuka(ambil_putaran(conn, data.putaran_id))
    ids = [r[0] for r in conn.execute(text(
        "SELECT id FROM lk.penyesuaian WHERE putaran_id = :p AND wilayah_kode = :w AND tahap = 'SIMULASI'"
        " AND status IN ('draf','diajukan')"), {"p": data.putaran_id, "w": data.wilayah})]
    if not ids:
        return {"jumlah": 0, "pesan": "Tidak ada simulasi yang menunggu persetujuan."}
    n = putus_penyesuaian(conn, data.putaran_id, ids, "setujui", data.catatan or "simulasi disetujui")
    return {"jumlah": n, "pesan": f"{n} isian simulasi disetujui. Tahap FINAL dihitung ulang."}
