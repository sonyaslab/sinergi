"""Putaran: buka (salin dari putaran sumber), cakupan periode, cut-off, kunci / buka kunci (beralasan), bandingkan.

- Buka = putaran baru `terbuka` dengan cakupan [periode awal, triwulan berjalan]. Bila ada sumber (tahun dasar sama),
  disalin: nilai data dasar, jangkar, seri referensi, konfirmasi validasi, dan penyesuaian (kecuali ditolak) yang
  SEMUANYA menjadi draf (keputusan 21). Item, seri item, dan tautan milik tahun dasar (dipakai bersama). Status
  lapus dimulai dari 'belum'.
- Kunci (putaran.kunci, alasan wajib): advisory lock eksklusif, lalu syarat untuk setiap wilayah yang punya item atau
  penyesuaian: V13–V15 lolos, semua lapus berdata yang punya item/penyesuaian disetujui, simulasi sudah diputus, dan
  antrean hitung kosong (keputusan 20). Setelah terkunci semua tulis ditolak (423, trigger).
- Buka kunci hanya putaran.buka_kunci dengan alasan; tercatat di audit (trigger lk.cek_putaran).
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import Connection, text

from ..app.deps import Pengguna, butuh_izin, koneksi, pengguna_aktif
from ..app.galat import GalatSinergi
from ..data_dasar import validasi_db
from ..master.umum import rapikan, tidak_ada, tidak_valid
from ..worker.antrean import antrekan
from .umum import ambil_putaran, label, setel_alasan

router = APIRouter(prefix="/api", tags=["putaran"])
KELOLA = Depends(butuh_izin("putaran.kelola"))


def _ringkas(r: dict) -> dict:
    return r | {"label_awal": label(r["awal"]), "label_akhir": label(r["akhir"])}


# ======================================================================== baca
@router.get("/putaran")
def daftar_putaran(tahun_dasar_id: int | None = None, conn: Connection = Depends(koneksi),
                   _: Pengguna = Depends(pengguna_aktif)) -> list[dict]:
    rows = conn.execute(text(
        "SELECT p.id, p.tahun_dasar_id, t.kode AS tahun_dasar, p.nama, p.jenis, p.status, p.tahun, p.triwulan,"
        " p.nomor, p.catatan, p.tanggal_cutoff, p.tanggal_cutoff IS NOT NULL AND now() > p.tanggal_cutoff"
        " AS lewat_cutoff, p.sumber_putaran_id, s.nama AS sumber, p.dibuka_pada, u1.nama AS dibuka_oleh,"
        " p.dikunci_pada, u2.nama AS dikunci_oleh, pa.urut AS awal, pz.urut AS akhir FROM lk.putaran p"
        " JOIN ref.tahun_dasar t ON t.id = p.tahun_dasar_id JOIN ref.periode pa ON pa.id = p.periode_awal_id"
        " JOIN ref.periode pz ON pz.id = p.periode_akhir_id LEFT JOIN lk.putaran s ON s.id = p.sumber_putaran_id"
        " LEFT JOIN sec.pengguna u1 ON u1.id = p.dibuka_oleh LEFT JOIN sec.pengguna u2 ON u2.id = p.dikunci_oleh"
        " WHERE CAST(:td AS int) IS NULL OR p.tahun_dasar_id = :td"
        " ORDER BY p.tahun DESC, p.triwulan DESC, p.nomor DESC, p.id DESC"), {"td": tahun_dasar_id}).mappings().all()
    return [_ringkas(dict(r)) for r in rows]


# ======================================================================== buka (+ salin)
class BukaIn(BaseModel):
    tahun_dasar_id: int
    tahun: int = Field(ge=2010, le=2045)
    triwulan: int = Field(ge=1, le=4)
    nomor: int | None = Field(default=None, ge=0, le=999)
    nama: str = Field(min_length=2, max_length=100)
    jenis: Literal["BACKCAST", "REGULER", "REVISI", "RILIS"]
    periode_awal: int  # urut; periode akhir = (tahun, triwulan) = triwulan berjalan
    tanggal_cutoff: datetime | None = None
    sumber_putaran_id: int | None = None
    catatan: str | None = Field(default=None, max_length=500)


SALIN = [  # (tabel, kolom) — disalin apa adanya ke putaran baru (putaran_id diganti)
    ("lk.nilai_item", "item_id, jenis_seri, periode_id, nilai, status_sel, catatan, diubah_oleh, diubah_pada"),
    ("lk.parameter_item", "item_id, kode, nilai, alasan, diubah_oleh, diubah_pada"),
    ("lk.nilai_seri_referensi", "seri_id, wilayah_kode, periode_id, nilai, diubah_oleh, diubah_pada"),
    ("lk.konfirmasi_validasi", "wilayah_kode, lapus_id, kode_validasi, kunci, alasan, dikonfirmasi_oleh,"
                               " dikonfirmasi_pada"),
]


@router.post("/putaran", status_code=201)
def buka(data: BukaIn, conn: Connection = Depends(koneksi), _: Pengguna = KELOLA) -> dict:
    td = conn.execute(text("SELECT id, tahun_awal_seri FROM ref.tahun_dasar WHERE id = :td"),
                      {"td": data.tahun_dasar_id}).first()
    if td is None:
        raise tidak_ada("Tahun dasar")
    akhir = data.tahun * 4 + data.triwulan - 1
    if not td.tahun_awal_seri * 4 <= data.periode_awal <= akhir:
        raise tidak_valid("Periode awal harus antara awal seri tahun dasar dan triwulan berjalan.")
    sumber = None
    if data.sumber_putaran_id is not None:
        sumber = conn.execute(text("SELECT id, tahun_dasar_id, nama FROM lk.putaran WHERE id = :s"),
                              {"s": data.sumber_putaran_id}).first()
        if sumber is None:
            raise tidak_ada("Putaran sumber")
        if sumber.tahun_dasar_id != data.tahun_dasar_id:
            raise tidak_valid("Putaran sumber harus pada tahun dasar yang sama.")
    nomor = data.nomor if data.nomor is not None else conn.execute(text(
        "SELECT coalesce(max(nomor), -1) + 1 FROM lk.putaran WHERE tahun_dasar_id = :td AND tahun = :y"
        " AND triwulan = :q"), {"td": data.tahun_dasar_id, "y": data.tahun, "q": data.triwulan}).scalar_one()
    setel_alasan(conn, f"buka putaran {rapikan(data.nama)}" + (f" (salin dari {sumber.nama})" if sumber else ""))
    pid = conn.execute(text(
        "INSERT INTO lk.putaran (tahun_dasar_id, tahun, triwulan, nomor, nama, jenis, status, periode_awal_id,"
        " periode_akhir_id, sumber_putaran_id, dibuka_oleh, dibuka_pada, catatan, tanggal_cutoff)"
        " SELECT :td, :y, :q, :n, :nama, :j, 'terbuka', pa.id, pz.id, :s, sec.uid(), now(), :c, :cut"
        " FROM ref.periode pa, ref.periode pz WHERE pa.urut = :awal AND pz.urut = :akhir RETURNING id"),
        {"td": data.tahun_dasar_id, "y": data.tahun, "q": data.triwulan, "n": nomor, "nama": rapikan(data.nama),
         "j": data.jenis, "s": data.sumber_putaran_id, "c": rapikan(data.catatan) or None, "cut": data.tanggal_cutoff,
         "awal": data.periode_awal, "akhir": akhir}).scalar_one()
    jumlah: dict[str, int] = {}
    if sumber is not None:
        q = {"s": sumber.id, "b": pid}
        for tabel, kolom in SALIN:
            jumlah[tabel.split(".")[1]] = conn.execute(text(
                f"INSERT INTO {tabel} (putaran_id, {kolom}) SELECT :b, {kolom} FROM {tabel} WHERE putaran_id = :s"),
                q).rowcount
        jumlah["penyesuaian"] = conn.execute(text(
            "INSERT INTO lk.penyesuaian (putaran_id, wilayah_kode, lapus_id, tahap, metode_kode, jenis_kode, harga,"
            " periode_id, nilai, alasan, status, diusulkan_oleh, diusulkan_pada) SELECT :b, wilayah_kode, lapus_id,"
            " tahap, metode_kode, jenis_kode, harga, periode_id, nilai, alasan, 'draf', diusulkan_oleh, diusulkan_pada"
            " FROM lk.penyesuaian WHERE putaran_id = :s AND status <> 'ditolak'"), q).rowcount
    wil = [r[0].strip() for r in conn.execute(text(
        "SELECT DISTINCT wilayah_kode FROM lk.item WHERE tahun_dasar_id = :td AND metode_kode IN ('REV','EKS','DEF')"),
        {"td": data.tahun_dasar_id})]
    for w in wil:
        antrekan(conn, pid, w, None, "buka putaran")
    return {"id": pid, "nomor": nomor, "disalin": jumlah,
            "pesan": f"Putaran {rapikan(data.nama)} dibuka" + (f", disalin dari {sumber.nama}." if sumber else ".")}


class UbahIn(BaseModel):
    nama: str | None = Field(default=None, min_length=2, max_length=100)
    catatan: str | None = Field(default=None, max_length=500)
    tanggal_cutoff: datetime | None = None


@router.patch("/putaran/{putaran_id}")
def ubah(putaran_id: int, data: UbahIn, conn: Connection = Depends(koneksi), _: Pengguna = KELOLA) -> dict:
    p = ambil_putaran(conn, putaran_id)
    if p["status"] == "terkunci":
        raise GalatSinergi(423, "PUTARAN_TERKUNCI", "Putaran sudah dikunci. Perubahan tidak dapat disimpan.")
    f = data.model_fields_set
    if not f:
        raise tidak_valid("Tidak ada perubahan.")
    conn.execute(text(
        "UPDATE lk.putaran SET nama = CASE WHEN :un THEN :n ELSE nama END,"
        " catatan = CASE WHEN :uc THEN :c ELSE catatan END,"
        " tanggal_cutoff = CASE WHEN :ut THEN CAST(:t AS timestamptz) ELSE tanggal_cutoff END WHERE id = :p"),
        {"un": "nama" in f and data.nama is not None, "n": rapikan(data.nama), "uc": "catatan" in f,
         "c": rapikan(data.catatan) or None, "ut": "tanggal_cutoff" in f, "t": data.tanggal_cutoff, "p": putaran_id})
    return {"pesan": "Putaran diperbarui."}


# ======================================================================== kunci
def wilayah_diperiksa(conn: Connection, p: dict) -> list[str]:
    """Wilayah yang ikut syarat kunci: punya item REV/EKS/DEF, penyesuaian, atau status lapus pada putaran ini."""
    return sorted(r[0].strip() for r in conn.execute(text(
        "SELECT wilayah_kode FROM lk.item WHERE tahun_dasar_id = :td AND metode_kode IN ('REV','EKS','DEF')"
        " UNION SELECT wilayah_kode FROM lk.penyesuaian WHERE putaran_id = :p"
        " UNION SELECT wilayah_kode FROM lk.status_lapus WHERE putaran_id = :p AND status <> 'belum'"),
        {"td": p["tahun_dasar_id"], "p": p["id"]}))


def syarat_kunci(conn: Connection, p: dict) -> dict:
    blokir: list[dict] = []
    wil = wilayah_diperiksa(conn, p)
    for w in wil:
        for b in validasi_db.ringkasan_kunci(conn, p["id"], w)["blokir"]:
            blokir.append({"wilayah": w, **b})
        for r in conn.execute(text(
                "SELECT l.kode, coalesce(s.status, 'belum') AS status FROM ref.lapus l LEFT JOIN lk.status_lapus s"
                " ON s.putaran_id = :p AND s.wilayah_kode = :w AND s.lapus_id = l.id"
                " WHERE l.tahun_dasar_id = :td AND l.aktif AND l.jenis IN ('daun','top','sop')"
                " AND coalesce(s.status, 'belum') <> 'disetujui'"
                " AND (EXISTS (SELECT 1 FROM lk.item i WHERE i.tahun_dasar_id = :td AND i.wilayah_kode = :w"
                "   AND i.lapus_id = l.id AND i.metode_kode IN ('REV','EKS','DEF'))"
                "  OR EXISTS (SELECT 1 FROM lk.penyesuaian a WHERE a.putaran_id = :p AND a.wilayah_kode = :w"
                "   AND a.lapus_id = l.id AND a.tahap IN ('METODE','REKON') AND a.status <> 'ditolak'))"
                " ORDER BY l.urutan"), {"p": p["id"], "w": w, "td": p["tahun_dasar_id"]}).mappings():
            blokir.append({"wilayah": w, "kode": "STATUS", "kode_lapus": r["kode"],
                           "pesan": f"Lapus {r['kode']} berstatus {r['status']}; harus disetujui."})
        n = conn.execute(text(
            "SELECT count(*) FROM lk.penyesuaian WHERE putaran_id = :p AND wilayah_kode = :w AND tahap = 'SIMULASI'"
            " AND status IN ('draf','diajukan')"), {"p": p["id"], "w": w}).scalar_one()
        if n:
            blokir.append({"wilayah": w, "kode": "SIMULASI", "kode_lapus": "-",
                           "pesan": f"{n} isian simulasi belum diputus."})
    n = conn.execute(text("SELECT count(*) FROM lk.antrean_hitung WHERE putaran_id = :p"
                          " AND status IN ('menunggu','proses')"), {"p": p["id"]}).scalar_one()
    if n:
        blokir.append({"wilayah": "-", "kode": "ANTREAN", "kode_lapus": "-",
                       "pesan": "Hitung ulang masih berjalan; tunggu sampai selesai."})
    return {"wilayah": wil, "blokir": blokir, "boleh_kunci": not blokir}


@router.get("/putaran/{putaran_id}/syarat-kunci")
def lihat_syarat(putaran_id: int, conn: Connection = Depends(koneksi),
                 _: Pengguna = Depends(butuh_izin("putaran.kunci", "lk.setujui", "putaran.kelola"))) -> dict:
    return syarat_kunci(conn, ambil_putaran(conn, putaran_id))


class AlasanIn(BaseModel):
    alasan: str = Field(min_length=10, max_length=500)


@router.post("/putaran/{putaran_id}/kunci")
def kunci(putaran_id: int, data: AlasanIn, conn: Connection = Depends(koneksi),
          _: Pengguna = Depends(butuh_izin("putaran.kunci"))) -> dict:
    p = ambil_putaran(conn, putaran_id)
    if p["status"] == "terkunci":
        raise GalatSinergi(409, "SUDAH_TERKUNCI", "Putaran sudah terkunci.")
    # Eksklusif: menunggu tulis yang berjalan selesai; tulis baru menunggu keputusan kunci (lk.tolak_jika_terkunci).
    conn.execute(text("SELECT pg_advisory_xact_lock(hashtextextended('putaran:' || :p, 0))"), {"p": putaran_id})
    s = syarat_kunci(conn, p)
    if not s["boleh_kunci"]:
        raise GalatSinergi(409, "SYARAT_KUNCI", f"Putaran belum dapat dikunci: {len(s['blokir'])} syarat belum"
                           " terpenuhi.", s["blokir"][:200])
    setel_alasan(conn, rapikan(data.alasan))
    conn.execute(text("UPDATE lk.putaran SET status = 'terkunci', dikunci_oleh = sec.uid(), dikunci_pada = now()"
                      " WHERE id = :p"), {"p": putaran_id})
    return {"status": "terkunci", "pesan": f"Putaran {p['nama']} dikunci. Semua perubahan kini ditolak."}


@router.post("/putaran/{putaran_id}/buka-kunci")
def buka_kunci(putaran_id: int, data: AlasanIn, conn: Connection = Depends(koneksi),
               _: Pengguna = Depends(butuh_izin("putaran.buka_kunci"))) -> dict:
    p = ambil_putaran(conn, putaran_id)
    if p["status"] != "terkunci":
        raise GalatSinergi(409, "TIDAK_TERKUNCI", "Putaran tidak terkunci.")
    setel_alasan(conn, rapikan(data.alasan))
    conn.execute(text("UPDATE lk.putaran SET status = 'terbuka' WHERE id = :p"), {"p": putaran_id})
    return {"status": "terbuka", "pesan": f"Kunci putaran {p['nama']} dibuka. Perubahan tercatat di audit."}


# ======================================================================== bandingkan dua putaran
def _dua(conn: Connection, a: int, b: int) -> tuple[dict, dict]:
    pa, pb = ambil_putaran(conn, a), ambil_putaran(conn, b)
    if pa["tahun_dasar_id"] != pb["tahun_dasar_id"]:
        raise tidak_valid("Hanya putaran pada tahun dasar yang sama yang dapat dibandingkan.")
    return pa, pb


def _info(p: dict) -> dict:
    return {k: p[k] for k in ("id", "nama", "status", "awal", "akhir")} | {"label_awal": label(p["awal"]),
                                                                           "label_akhir": label(p["akhir"])}


@router.get("/putaran/{a}/banding/{b}")
def banding(a: int, b: int, wilayah: str, conn: Connection = Depends(koneksi),
            _: Pengguna = Depends(pengguna_aktif)) -> dict:
    """Bandingkan putaran a (lama) dan b (baru) satu wilayah: NTB FINAL [ADHB, ADHK] per lapus x triwulan (laju dan
    selisih dihitung di layar), jumlah sel data dasar / jangkar / penyesuaian yang berbeda per lapus."""
    pa, pb = _dua(conn, a, b)
    q = {"a": a, "b": b, "w": wilayah, "td": pa["tahun_dasar_id"]}
    baris = [dict(r) | {"a": {}, "b": {}, "data": {"baru": 0, "hilang": 0, "berubah": 0}, "jangkar": 0,
                        "penyesuaian": 0} for r in conn.execute(text(
                            "SELECT id, kode, nama, level, jenis FROM ref.lapus WHERE tahun_dasar_id = :td AND aktif"
                            " ORDER BY urutan"), q).mappings()]
    per = {r["id"]: r for r in baris}
    for pid, kunci_ in ((a, "a"), (b, "b")):
        for lid, u, cp, k in conn.execute(text(
                "SELECT h.lapus_id, pe.urut, h.gva_cp::float8, h.gva_k::float8 FROM lk.hasil_lapus h"
                " JOIN ref.periode pe ON pe.id = h.periode_id WHERE h.putaran_id = :p AND h.wilayah_kode = :w"
                " AND h.tahap = 'FINAL'"),
                {"p": pid, "w": wilayah}):
            if lid in per:
                per[lid][kunci_][str(u)] = [cp, k]
    for lid, baru, hilang, berubah in conn.execute(text(
            "SELECT i.lapus_id, count(*) FILTER (WHERE x.item_id IS NULL), count(*) FILTER (WHERE y.item_id IS NULL),"
            " count(*) FILTER (WHERE x.item_id IS NOT NULL AND y.item_id IS NOT NULL)"
            " FROM (SELECT * FROM lk.nilai_item WHERE putaran_id = :a) x FULL JOIN"
            " (SELECT * FROM lk.nilai_item WHERE putaran_id = :b) y ON y.item_id = x.item_id"
            " AND y.jenis_seri = x.jenis_seri AND y.periode_id = x.periode_id"
            " JOIN lk.item i ON i.id = coalesce(x.item_id, y.item_id) WHERE i.wilayah_kode = :w"
            " AND (x.item_id IS NULL OR y.item_id IS NULL OR x.nilai IS DISTINCT FROM y.nilai"
            "  OR x.status_sel <> y.status_sel) GROUP BY i.lapus_id"), q):
        if lid in per:
            per[lid]["data"] = {"baru": baru, "hilang": hilang, "berubah": berubah}
    for lid, n in conn.execute(text(
            "SELECT i.lapus_id, count(*) FROM (SELECT * FROM lk.parameter_item WHERE putaran_id = :a) x"
            " FULL JOIN (SELECT * FROM lk.parameter_item WHERE putaran_id = :b) y ON y.item_id = x.item_id"
            " AND y.kode = x.kode JOIN lk.item i ON i.id = coalesce(x.item_id, y.item_id) WHERE i.wilayah_kode = :w"
            " AND x.nilai IS DISTINCT FROM y.nilai GROUP BY i.lapus_id"), q):
        if lid in per:
            per[lid]["jangkar"] = n
    for lid, n in conn.execute(text(
            "SELECT coalesce(x.lapus_id, y.lapus_id), count(*) FROM"
            " (SELECT * FROM lk.penyesuaian WHERE putaran_id = :a AND wilayah_kode = :w) x FULL JOIN"
            " (SELECT * FROM lk.penyesuaian WHERE putaran_id = :b AND wilayah_kode = :w) y"
            " ON y.lapus_id = x.lapus_id AND y.tahap = x.tahap AND y.metode_kode IS NOT DISTINCT FROM x.metode_kode"
            " AND y.jenis_kode = x.jenis_kode AND y.harga = x.harga AND y.periode_id = x.periode_id"
            " WHERE x.id IS NULL OR y.id IS NULL OR x.nilai IS DISTINCT FROM y.nilai OR x.status <> y.status"
            " GROUP BY 1"), q):
        if lid in per:
            per[lid]["penyesuaian"] = n
    awal, akhir = min(pa["awal"], pb["awal"]), max(pa["akhir"], pb["akhir"])
    return {"a": _info(pa), "b": _info(pb), "periode": [{"urut": u, "label": label(u)}
                                                        for u in range(awal, akhir + 1)], "baris": baris}


@router.get("/putaran/{a}/banding/{b}/data")
def banding_data(a: int, b: int, wilayah: str, lapus_id: int, conn: Connection = Depends(koneksi),
                 _: Pengguna = Depends(pengguna_aktif)) -> list[dict]:
    """Rincian sel data dasar yang berbeda (lama -> baru) untuk satu lapus."""
    _dua(conn, a, b)
    rows = conn.execute(text(
        "SELECT i.id AS item_id, i.metode_kode AS metode, i.nomor, i.nama, coalesce(x.jenis_seri, y.jenis_seri)"
        " AS seri, pe.urut AS periode, x.nilai::float8 AS lama, y.nilai::float8 AS baru, x.status_sel AS status_lama,"
        " y.status_sel AS status_baru FROM (SELECT * FROM lk.nilai_item WHERE putaran_id = :a) x FULL JOIN"
        " (SELECT * FROM lk.nilai_item WHERE putaran_id = :b) y ON y.item_id = x.item_id AND y.jenis_seri ="
        " x.jenis_seri AND y.periode_id = x.periode_id JOIN lk.item i ON i.id = coalesce(x.item_id, y.item_id)"
        " JOIN ref.periode pe ON pe.id = coalesce(x.periode_id, y.periode_id) WHERE i.wilayah_kode = :w"
        " AND i.lapus_id = :l AND (x.item_id IS NULL OR y.item_id IS NULL OR x.nilai IS DISTINCT FROM y.nilai"
        "  OR x.status_sel <> y.status_sel) ORDER BY i.metode_kode, i.nomor, seri, pe.urut LIMIT 5000"),
        {"a": a, "b": b, "w": wilayah, "l": lapus_id}).mappings().all()
    return [dict(r) | {"label_periode": label(r["periode"])} for r in rows]
