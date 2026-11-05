"""Status lapus per (putaran, wilayah, lapus): belum -> draf -> diajukan -> disetujui / dikembalikan; NIHIL (daun tanpa
item, V13) dan DIKECUALIKAN (TOP/SOP tanpa item, admin, V14; keputusan 2).

- Setiap perubahan data dasar, item, jangkar, tautan, atau penyesuaian METODE/REKON sebuah lapus mengembalikan statusnya
  ke draf (keputusan 19: persetujuan gugur dan tercatat di riwayat); penyesuaian yang sedang diajukan ikut kembali draf.
- AJUKAN diblokir temuan validasi `blokir_ajukan` yang belum dikonfirmasi (dihitung saat diminta, bukan dari hasil
  worker yang mungkin belum diperbarui). Penyesuaian draf lapus itu ikut diajukan.
- SETUJUI hanya bila semua penyesuaian yang diajukan sudah diputus (atau diputus sekaligus lewat opsi).
Pesan tidak memuat angka PDRB.
"""
from __future__ import annotations

from collections.abc import Iterable
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import Connection, text

from ..app.deps import Pengguna, butuh_izin, koneksi, pengguna_aktif
from ..app.galat import GalatSinergi
from ..data_dasar import validasi_db
from ..master.umum import rapikan, tidak_valid
from ..worker.antrean import antrekan
from .umum import BERDATA, ambil_putaran, boleh_tulis, cek_tulis, lapus_td, pastikan_terbuka

router = APIRouter(prefix="/api", tags=["status-lapus"])
SELESAI = ("disetujui", "nihil", "dikecualikan")
NAMA = {"belum": "belum diisi", "draf": "draf", "diajukan": "diajukan", "disetujui": "disetujui",
        "dikembalikan": "dikembalikan", "nihil": "NIHIL", "dikecualikan": "DIKECUALIKAN"}


# ======================================================================== bantu (dipakai modul lain)
def status_sekarang(conn: Connection, putaran_id: int, wilayah: str, lapus_id: int) -> str:
    st = conn.execute(text("SELECT status FROM lk.status_lapus WHERE putaran_id = :p AND wilayah_kode = :w"
                           " AND lapus_id = :l"), {"p": putaran_id, "w": wilayah, "l": lapus_id}).scalar()
    return str(st or "belum")


def ubah_status(conn: Connection, putaran_id: int, wilayah: str, lapus_id: int, dari: str, ke: str,
                catatan: str | None) -> None:
    q = {"p": putaran_id, "w": wilayah, "l": lapus_id, "ke": ke, "dari": dari, "c": catatan}
    conn.execute(text(
        "INSERT INTO lk.status_lapus (putaran_id, wilayah_kode, lapus_id, status, diperbarui_oleh, diperbarui_pada,"
        " catatan) VALUES (:p, :w, :l, :ke, sec.uid(), now(), :c) ON CONFLICT (putaran_id, wilayah_kode, lapus_id)"
        " DO UPDATE SET status = EXCLUDED.status, diperbarui_oleh = EXCLUDED.diperbarui_oleh,"
        " diperbarui_pada = now(), catatan = EXCLUDED.catatan"), q)
    conn.execute(text("INSERT INTO lk.riwayat_status (putaran_id, wilayah_kode, lapus_id, dari, ke, oleh, catatan)"
                      " VALUES (:p, :w, :l, :dari, :ke, sec.uid(), :c)"), q)


def _adj_status(conn: Connection, putaran_id: int, wilayah: str, lapus_id: int, dari: str, ke: str) -> int:
    return conn.execute(text(
        "UPDATE lk.penyesuaian SET status = :ke WHERE putaran_id = :p AND wilayah_kode = :w AND lapus_id = :l"
        " AND tahap IN ('METODE','REKON') AND status = :dari"),
        {"p": putaran_id, "w": wilayah, "l": lapus_id, "dari": dari, "ke": ke}).rowcount


def tandai_ubah(conn: Connection, putaran_id: int, pasangan: Iterable[tuple[str, int]], sebab: str) -> list[int]:
    """Lapus yang datanya berubah kembali ke draf (keputusan 19). Kembalikan id lapus yang statusnya berubah."""
    pas = sorted({(w.strip(), int(lid)) for w, lid in pasangan})
    if not pas:
        return []
    rows = conn.execute(text(
        "SELECT x.w, x.l, coalesce(s.status, 'belum') FROM unnest(CAST(:w AS text[]), CAST(:l AS int[])) AS x(w, l)"
        " JOIN ref.lapus rl ON rl.id = x.l AND rl.jenis IN ('daun','top','sop')"
        " LEFT JOIN lk.status_lapus s ON s.putaran_id = :p AND s.wilayah_kode = x.w AND s.lapus_id = x.l"),
        {"p": putaran_id, "w": [a for a, _ in pas], "l": [b for _, b in pas]}).all()
    berubah = []
    for w, lid, st in rows:
        if st == "draf":
            continue
        catatan = f"Kembali ke draf: {sebab}" if st in ("diajukan", "disetujui", "nihil", "dikecualikan") else None
        ubah_status(conn, putaran_id, w, lid, st, "draf", catatan)
        if st == "diajukan":
            _adj_status(conn, putaran_id, w, lid, "diajukan", "draf")
        berubah.append(lid)
    return berubah


def jumlah_item(conn: Connection, td: int, wilayah: str, lapus_id: int) -> int:
    return int(conn.execute(text(
        "SELECT count(*) FROM lk.item WHERE tahun_dasar_id = :td AND wilayah_kode = :w AND lapus_id = :l"
        " AND metode_kode IN ('REV','EKS','DEF')"), {"td": td, "w": wilayah, "l": lapus_id}).scalar_one())


# ======================================================================== baca
@router.get("/status")
def daftar_status(putaran_id: int, wilayah: str, conn: Connection = Depends(koneksi),
                  _: Pengguna = Depends(pengguna_aktif)) -> dict:
    """Status semua lapus berdata satu wilayah: jumlah item, penyesuaian per status, temuan blokir ajukan."""
    p = ambil_putaran(conn, putaran_id)
    rows = conn.execute(text(
        "SELECT l.id, l.kode, l.nama, l.jenis, l.induk_id, l.urutan, coalesce(s.status, 'belum') AS status, s.catatan,"
        " s.diperbarui_pada, u.nama AS diperbarui_oleh,"
        " (SELECT count(*) FROM lk.item i WHERE i.tahun_dasar_id = :td AND i.wilayah_kode = :w AND i.lapus_id = l.id"
        "  AND i.metode_kode IN ('REV','EKS','DEF')) AS jumlah_item,"
        " (SELECT coalesce(jsonb_object_agg(x.status, x.n), '{}') FROM (SELECT a.status, count(*) AS n"
        "  FROM lk.penyesuaian a WHERE a.putaran_id = :p AND a.wilayah_kode = :w AND a.lapus_id = l.id"
        "  AND a.tahap IN ('METODE','REKON') GROUP BY a.status) x) AS penyesuaian,"
        " (SELECT count(*) FROM lk.hasil_validasi h WHERE h.putaran_id = :p AND h.wilayah_kode = :w"
        "  AND h.lapus_id = l.id AND h.tingkat = 'blokir_ajukan' AND h.dikonfirmasi_oleh IS NULL) AS blokir_ajukan,"
        " lk.boleh_tulis(CAST(:w AS char(4)), l.id) AS boleh_tulis"
        " FROM ref.lapus l LEFT JOIN lk.status_lapus s ON s.putaran_id = :p AND s.wilayah_kode = :w"
        " AND s.lapus_id = l.id LEFT JOIN sec.pengguna u ON u.id = s.diperbarui_oleh"
        " WHERE l.tahun_dasar_id = :td AND l.aktif AND l.jenis IN ('daun','top','sop') ORDER BY l.urutan"),
        {"p": putaran_id, "w": wilayah, "td": p["tahun_dasar_id"]}).mappings().all()
    return {"putaran": {"id": p["id"], "status": p["status"]}, "lapus": [dict(r) for r in rows]}


@router.get("/status/ringkasan")
def ringkasan_status(putaran_id: int, conn: Connection = Depends(koneksi),
                     _: Pengguna = Depends(pengguna_aktif)) -> dict:
    """Heatmap Beranda: status lapus berdata x wilayah (+ apakah lapus punya item di wilayah itu)."""
    p = ambil_putaran(conn, putaran_id)
    q = {"p": putaran_id, "td": p["tahun_dasar_id"]}
    lapus = [dict(r) for r in conn.execute(text(
        "SELECT id, kode, nama, jenis, induk_id FROM ref.lapus WHERE tahun_dasar_id = :td AND aktif"
        " AND jenis IN ('daun','top','sop') ORDER BY urutan"), q).mappings()]
    wilayah = [dict(r) for r in conn.execute(text(
        "SELECT kode, nama FROM ref.wilayah WHERE aktif ORDER BY urutan, kode")).mappings()]
    sel: dict[str, dict[str, dict]] = {w["kode"]: {} for w in wilayah}
    for w, lid, n in conn.execute(text(
            "SELECT wilayah_kode, lapus_id, count(*) FROM lk.item WHERE tahun_dasar_id = :td"
            " AND metode_kode IN ('REV','EKS','DEF') GROUP BY 1, 2"), q):
        sel.setdefault(w.strip(), {})[str(lid)] = {"status": "belum", "item": int(n)}
    for w, lid, st in conn.execute(text(
            "SELECT wilayah_kode, lapus_id, status FROM lk.status_lapus WHERE putaran_id = :p"), q):
        sel.setdefault(w.strip(), {}).setdefault(str(lid), {"item": 0})["status"] = st
    return {"putaran": {"id": p["id"], "nama": p["nama"], "status": p["status"]}, "lapus": lapus,
            "wilayah": wilayah, "sel": sel}


@router.get("/status/{lapus_id}/riwayat")
def riwayat(lapus_id: int, putaran_id: int, wilayah: str, conn: Connection = Depends(koneksi),
            _: Pengguna = Depends(pengguna_aktif)) -> list[dict]:
    return [dict(r) for r in conn.execute(text(
        "SELECT r.dari, r.ke, r.pada, r.catatan, u.nama AS oleh FROM lk.riwayat_status r"
        " LEFT JOIN sec.pengguna u ON u.id = r.oleh WHERE r.putaran_id = :p AND r.wilayah_kode = :w"
        " AND r.lapus_id = :l ORDER BY r.id DESC"), {"p": putaran_id, "w": wilayah, "l": lapus_id}).mappings()]


# ======================================================================== aksi
class AksiStatus(BaseModel):
    putaran_id: int
    wilayah: str = Field(min_length=4, max_length=4)
    catatan: str | None = Field(default=None, max_length=500)


class SetujuiIn(AksiStatus):
    putus_penyesuaian: Literal["setujui", "tolak"] | None = None


def _siapkan(conn: Connection, lapus_id: int, data: AksiStatus) -> tuple[dict, dict, str]:
    p = ambil_putaran(conn, data.putaran_id)
    pastikan_terbuka(p)
    lap = lapus_td(conn, p["tahun_dasar_id"], lapus_id)
    if lap["jenis"] not in BERDATA:
        raise tidak_valid("Status hanya untuk lapus berdata (daun, TOP, SOP).")
    return p, lap, status_sekarang(conn, data.putaran_id, data.wilayah, lapus_id)


def _catatan_wajib(c: str | None) -> str:
    c = rapikan(c)
    if len(c) < 10:
        raise tidak_valid("Catatan wajib diisi (min. 10 karakter).")
    return c


def _salah_status(st: str, aksi: str) -> GalatSinergi:
    return GalatSinergi(409, "STATUS_LAPUS", f"Lapus berstatus {NAMA.get(st, st)}; tidak dapat {aksi}.")


def _cek_validasi(conn: Connection, data: AksiStatus, lapus_id: int, aksi: str) -> None:
    ts, _, _ = validasi_db.temuan_langsung(conn, data.putaran_id, data.wilayah)
    bl = validasi_db.blokir(ts, "blokir_ajukan", lapus_id)
    if bl:
        raise GalatSinergi(409, "VALIDASI_BLOKIR",
                           f"{aksi} diblokir {len(bl)} temuan validasi. Perbaiki data atau konfirmasi temuan yang"
                           " boleh dikonfirmasi.", [{"kode": t.kode, "pesan": t.pesan} for t in bl[:50]])


@router.post("/status/{lapus_id}/ajukan")
def ajukan(lapus_id: int, data: AksiStatus, conn: Connection = Depends(koneksi),
           _: Pengguna = Depends(butuh_izin("lk.ajukan"))) -> dict:
    p, lap, st = _siapkan(conn, lapus_id, data)
    cek_tulis(conn, data.wilayah, lapus_id)
    if st not in ("belum", "draf", "dikembalikan"):
        raise _salah_status(st, "diajukan")
    if jumlah_item(conn, p["tahun_dasar_id"], data.wilayah, lapus_id) == 0:
        raise tidak_valid("Lapus belum punya item. Tandai NIHIL bila memang tidak ada kegiatan.")
    _cek_validasi(conn, data, lapus_id, "Pengajuan")
    ubah_status(conn, data.putaran_id, data.wilayah, lapus_id, st, "diajukan", rapikan(data.catatan) or None)
    n = _adj_status(conn, data.putaran_id, data.wilayah, lapus_id, "draf", "diajukan")
    return {"status": "diajukan", "penyesuaian_diajukan": n, "pesan": f"Lapus {lap['kode']} diajukan."}


@router.post("/status/{lapus_id}/setujui")
def setujui(lapus_id: int, data: SetujuiIn, conn: Connection = Depends(koneksi),
            _: Pengguna = Depends(butuh_izin("lk.setujui"))) -> dict:
    p, lap, st = _siapkan(conn, lapus_id, data)
    if st != "diajukan":
        raise _salah_status(st, "disetujui")
    q = {"p": data.putaran_id, "w": data.wilayah, "l": lapus_id}
    tunggu = int(conn.execute(text(
        "SELECT count(*) FROM lk.penyesuaian WHERE putaran_id = :p AND wilayah_kode = :w AND lapus_id = :l"
        " AND tahap IN ('METODE','REKON') AND status = 'diajukan'"), q).scalar_one())
    if tunggu and data.putus_penyesuaian is None:
        raise GalatSinergi(409, "PENYESUAIAN_BELUM_DIPUTUS",
                           f"Masih ada {tunggu} penyesuaian yang belum diputus. Putuskan dulu atau pilih"
                           " setujui/tolak sekaligus.", {"jumlah": tunggu})
    if tunggu:
        catatan = _catatan_wajib(data.catatan) if data.putus_penyesuaian == "tolak" else (
            rapikan(data.catatan) or "disetujui bersama persetujuan lapus")
        conn.execute(text(
            "UPDATE lk.penyesuaian SET status = :st, diputus_oleh = sec.uid(), diputus_pada = now(),"
            " catatan_putusan = :c WHERE putaran_id = :p AND wilayah_kode = :w AND lapus_id = :l"
            " AND tahap IN ('METODE','REKON') AND status = 'diajukan'"),
            {**q, "st": "disetujui" if data.putus_penyesuaian == "setujui" else "ditolak", "c": catatan})
    _cek_validasi(conn, data, lapus_id, "Persetujuan")
    ubah_status(conn, data.putaran_id, data.wilayah, lapus_id, st, "disetujui", rapikan(data.catatan) or None)
    if tunggu:
        antrekan(conn, data.putaran_id, data.wilayah, lapus_id, "putusan penyesuaian")
    return {"status": "disetujui", "penyesuaian_diputus": tunggu, "pesan": f"Lapus {lap['kode']} disetujui."}


@router.post("/status/{lapus_id}/kembalikan")
def kembalikan(lapus_id: int, data: AksiStatus, conn: Connection = Depends(koneksi),
               _: Pengguna = Depends(butuh_izin("lk.setujui"))) -> dict:
    _p, lap, st = _siapkan(conn, lapus_id, data)
    if st not in ("diajukan", "disetujui"):
        raise _salah_status(st, "dikembalikan")
    ubah_status(conn, data.putaran_id, data.wilayah, lapus_id, st, "dikembalikan", _catatan_wajib(data.catatan))
    _adj_status(conn, data.putaran_id, data.wilayah, lapus_id, "diajukan", "draf")
    return {"status": "dikembalikan", "pesan": f"Lapus {lap['kode']} dikembalikan ke operator."}


@router.post("/status/{lapus_id}/nihil")
def nihil(lapus_id: int, data: AksiStatus, conn: Connection = Depends(koneksi),
          pengguna: Pengguna = Depends(butuh_izin("lk.ajukan", "lk.setujui"))) -> dict:
    """NIHIL: daun tanpa kegiatan di wilayah ini (temuan S1, V13). TOP/SOP memakai DIKECUALIKAN (admin)."""
    p, lap, st = _siapkan(conn, lapus_id, data)
    if lap["jenis"] != "daun":
        raise tidak_valid("TOP/SOP tidak dapat ditandai NIHIL; pengecualian V14 hanya oleh admin (DIKECUALIKAN).")
    if not pengguna.punya("lk.setujui"):
        cek_tulis(conn, data.wilayah, lapus_id)
    if st not in ("belum", "draf", "dikembalikan"):
        raise _salah_status(st, "ditandai NIHIL")
    if jumlah_item(conn, p["tahun_dasar_id"], data.wilayah, lapus_id):
        raise tidak_valid("Lapus sudah punya item; tidak dapat ditandai NIHIL.")
    ubah_status(conn, data.putaran_id, data.wilayah, lapus_id, st, "nihil", _catatan_wajib(data.catatan))
    antrekan(conn, data.putaran_id, data.wilayah, lapus_id, "status NIHIL")
    return {"status": "nihil", "pesan": f"Lapus {lap['kode']} ditandai NIHIL."}


@router.post("/status/{lapus_id}/kecualikan")
def kecualikan(lapus_id: int, data: AksiStatus, conn: Connection = Depends(koneksi),
               _: Pengguna = Depends(butuh_izin("putaran.kelola"))) -> dict:
    """DIKECUALIKAN: TOP/SOP kosong dibebaskan dari V14 oleh admin dengan catatan (keputusan 2)."""
    p, lap, st = _siapkan(conn, lapus_id, data)
    if lap["jenis"] not in ("top", "sop"):
        raise tidak_valid("Pengecualian hanya untuk TOP/SOP (V14). Lapus lain memakai NIHIL.")
    if st not in ("belum", "draf", "dikembalikan"):
        raise _salah_status(st, "dikecualikan")
    if jumlah_item(conn, p["tahun_dasar_id"], data.wilayah, lapus_id):
        raise tidak_valid("TOP/SOP ini sudah punya item; tidak perlu dikecualikan.")
    ubah_status(conn, data.putaran_id, data.wilayah, lapus_id, st, "dikecualikan", _catatan_wajib(data.catatan))
    antrekan(conn, data.putaran_id, data.wilayah, lapus_id, "status DIKECUALIKAN")
    return {"status": "dikecualikan", "pesan": f"{lap['kode']} dikecualikan dari V14."}


@router.post("/status/{lapus_id}/batal")
def batal(lapus_id: int, data: AksiStatus, conn: Connection = Depends(koneksi),
          pengguna: Pengguna = Depends(pengguna_aktif)) -> dict:
    """Batalkan NIHIL/DIKECUALIKAN -> belum."""
    _, lap, st = _siapkan(conn, lapus_id, data)
    if st == "nihil":
        if not (pengguna.punya("lk.setujui") or (pengguna.punya("lk.ajukan")
                                                 and boleh_tulis(conn, data.wilayah, lapus_id))):
            raise GalatSinergi(403, "TIDAK_BERHAK", "Anda tidak memiliki izin untuk tindakan ini.")
    elif st == "dikecualikan":
        if not pengguna.punya("putaran.kelola"):
            raise GalatSinergi(403, "TIDAK_BERHAK", "Pengecualian hanya dapat dibatalkan admin.")
    else:
        raise _salah_status(st, "dibatalkan")
    ubah_status(conn, data.putaran_id, data.wilayah, lapus_id, st, "belum", rapikan(data.catatan) or None)
    antrekan(conn, data.putaran_id, data.wilayah, lapus_id, "batal status")
    return {"status": "belum", "pesan": f"Status {NAMA[st]} {lap['kode']} dibatalkan."}
