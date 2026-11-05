"""Muat masukan mesin hitung satu (putaran, wilayah) dari basis data (koneksi app_rw dengan konteks pengguna).

Hanya penyesuaian yang mengubah angka (ref.jenis_penyesuaian.ubah_angka) dan berstatus sesuai `status_adj`:
angka resmi = ('disetujui',) (keputusan 8a); pratinjau layar = ('draf', 'diajukan', 'disetujui').
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from sqlalchemy import Connection, text

from ..engine import DataLapus, Item, KonfigTD, Lapus, MasukanWilayah, Penyesuaian, Sumbu, Tautan
from ..engine.model import GalatMesin

STATUS_RESMI = ("disetujui",)
STATUS_PRATINJAU = ("draf", "diajukan", "disetujui")


@dataclass
class InfoPutaran:
    id: int
    tahun_dasar_id: int
    status: str
    awal: int
    akhir: int


def info_putaran(conn: Connection, putaran_id: int) -> InfoPutaran:
    r = conn.execute(text(
        "SELECT p.id, p.tahun_dasar_id, p.status, pa.urut AS awal, pz.urut AS akhir FROM lk.putaran p"
        " JOIN ref.periode pa ON pa.id = p.periode_awal_id JOIN ref.periode pz ON pz.id = p.periode_akhir_id"
        " WHERE p.id = :p"), {"p": putaran_id}).mappings().first()
    if r is None:
        raise GalatMesin(f"Putaran {putaran_id} tidak ada.")
    return InfoPutaran(r["id"], r["tahun_dasar_id"], r["status"], r["awal"], r["akhir"])


def muat(conn: Connection, putaran_id: int, wilayah: str,
         status_adj: tuple[str, ...] = STATUS_RESMI) -> tuple[MasukanWilayah, InfoPutaran]:
    pu = info_putaran(conn, putaran_id)
    q = {"p": putaran_id, "w": wilayah, "td": pu.tahun_dasar_id}
    td = conn.execute(text("SELECT tahun_baseline_eks, jangkar_dari_data FROM ref.tahun_dasar WHERE id = :td"),
                      q).one()
    konfig = KonfigTD(int(td[0]), bool(td[1]))

    anggota: dict[int, list[int]] = defaultdict(list)
    for k, a in conn.execute(text(
            "SELECT k.kelompok_id, k.anggota_id FROM ref.lapus_kelompok k JOIN ref.lapus a ON a.id = k.anggota_id"
            " WHERE a.tahun_dasar_id = :td AND a.aktif ORDER BY a.urutan"), q):
        anggota[k].append(a)
    pohon = [Lapus(r.id, r.kode, r.jenis, r.induk_id, r.urutan, r.is_migas, tuple(anggota.get(r.id, ())))
             for r in conn.execute(text(
                 "SELECT id, kode, jenis, induk_id, urutan, is_migas FROM ref.lapus"
                 " WHERE tahun_dasar_id = :td AND aktif ORDER BY urutan"), q)]

    item_dari = ("FROM lk.item i WHERE i.tahun_dasar_id = :td AND i.wilayah_kode = :w"
                 " AND i.metode_kode IN ('REV','EKS','DEF')")
    items: dict[int, Item] = {}
    lapus_item: dict[int, int] = {}
    for r in conn.execute(text(
            "SELECT i.id, i.lapus_id, i.metode_kode, i.jenis_indeks, pm.urut AS mulai, ps.urut AS selesai"
            " FROM lk.item i LEFT JOIN ref.periode pm ON pm.id = i.periode_mulai_id"
            " LEFT JOIN ref.periode ps ON ps.id = i.periode_selesai_id"
            " WHERE i.tahun_dasar_id = :td AND i.wilayah_kode = :w AND i.metode_kode IN ('REV','EKS','DEF')"
            " ORDER BY i.lapus_id, i.metode_kode, i.nomor"), q):
        items[r.id] = Item(r.id, r.metode_kode, r.jenis_indeks, mulai=r.mulai, selesai=r.selesai)
        lapus_item[r.id] = r.lapus_id

    for iid, seri, u, x in conn.execute(text(
            "SELECT n.item_id, n.jenis_seri, p.urut, n.nilai::float8 FROM lk.nilai_item n"
            " JOIN ref.periode p ON p.id = n.periode_id"
            " WHERE n.putaran_id = :p AND n.status_sel = 'isi' AND n.nilai IS NOT NULL"
            f" AND n.item_id IN (SELECT i.id {item_dari})"), q):
        items[iid].seri.setdefault(seri, {})[u] = x
    for iid, kode, x in conn.execute(text(
            "SELECT item_id, kode, nilai::float8 FROM lk.parameter_item"
            f" WHERE putaran_id = :p AND item_id IN (SELECT i.id {item_dari})"), q):
        items[iid].parameter[kode] = x
    taut: dict[int, list[Tautan]] = defaultdict(list)
    for r in conn.execute(text(
            "SELECT t.item_id, t.jenis_seri, t.sumber, t.rumus, s.kode AS seri_ref, t.lapus_sumber_ids, t.besaran,"
            " t.faktor::float8 AS faktor FROM lk.tautan_seri t LEFT JOIN lk.seri_referensi s ON s.id = t.seri_id"
            f" WHERE t.item_id IN (SELECT i.id {item_dari}) ORDER BY t.item_id, t.jenis_seri"), q):
        taut[r.item_id].append(Tautan(r.jenis_seri, r.sumber, r.rumus, r.seri_ref, tuple(r.lapus_sumber_ids or ()),
                                      r.besaran, r.faktor))
    for iid, ts in taut.items():
        items[iid].tautan = tuple(ts)

    referensi: dict[str, dict[int, float]] = defaultdict(dict)
    for kode, u, x in conn.execute(text(
            "SELECT s.kode, p.urut, n.nilai::float8 FROM lk.nilai_seri_referensi n"
            " JOIN lk.seri_referensi s ON s.id = n.seri_id JOIN ref.periode p ON p.id = n.periode_id"
            " WHERE n.putaran_id = :p AND n.wilayah_kode = :w"), q):
        referensi[kode][u] = x

    data: dict[int, DataLapus] = defaultdict(DataLapus)
    for iid, it in items.items():
        data[lapus_item[iid]].item.append(it)
    for r in conn.execute(text(
            "SELECT a.lapus_id, a.tahap, a.metode_kode, a.jenis_kode, a.harga, p.urut, a.nilai::float8 AS nilai"
            " FROM lk.penyesuaian a JOIN ref.periode p ON p.id = a.periode_id"
            " JOIN ref.jenis_penyesuaian j ON j.kode = a.jenis_kode"
            " WHERE a.putaran_id = :p AND a.wilayah_kode = :w AND j.ubah_angka AND a.status = ANY(:st)"
            " ORDER BY a.id"), {**q, "st": list(status_adj)}):
        data[r.lapus_id].penyesuaian.append(Penyesuaian(r.tahap, r.jenis_kode, r.harga, r.urut, r.nilai, r.metode_kode))

    return MasukanWilayah(konfig, Sumbu(pu.awal, pu.akhir), pohon, dict(data), dict(referensi)), pu
