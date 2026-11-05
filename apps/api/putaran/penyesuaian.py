"""Penyesuaian (adjustment) tiga tahap: METODE (ADJ1/ADJ2/SC), REKON (ADJ3/ADJ4/CT), SIMULASI (SIM_NTB).

Status: draf -> diajukan (ikut AJUKAN lapus; simulasi langsung diputus) -> disetujui / ditolak. Hanya `disetujui`
masuk angka resmi (keputusan 8a). Mengubah nilai/alasan penyesuaian mengembalikannya ke draf; penyesuaian METODE/REKON
yang berubah mengembalikan lapusnya ke draf (keputusan 19). Alasan wajib min. 10 karakter (trigger, kecuali CT).
Bantuan input target (target NTB / output / laju y-on-y / implisit) dibalik dari rumus docs/02 §6 pada pratinjau
(draf + diajukan + disetujui) tanpa penyesuaian yang sedang diisi (keputusan 18; modul `target`).
"""
from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import Connection, text

from ..app.deps import Pengguna, butuh_izin, koneksi, pengguna_aktif
from ..app.galat import GalatSinergi
from ..engine import hitung_wilayah
from ..master.umum import rapikan, tidak_ada, tidak_valid
from ..worker.antrean import antrekan
from ..worker.muat import STATUS_PRATINJAU, muat
from .status import tandai_ubah
from .target import GalatTarget, Rincian, mode_untuk, nilai_penyesuaian
from .umum import BERDATA, ambil_putaran, cek_tulis, label, lapus_td, pastikan_terbuka

router = APIRouter(prefix="/api", tags=["penyesuaian"])
PUTUS = Depends(butuh_izin("penyesuaian.putus"))


# ======================================================================== baca
@router.get("/penyesuaian/jenis")
def jenis(conn: Connection = Depends(koneksi), _: Pengguna = Depends(pengguna_aktif)) -> list[dict]:
    """Jenis penyesuaian (master) beserta cara isi yang tersedia per harga."""
    return [dict(r) | {"mode": {h: mode_untuk(r["kode"], h) for h in ("CP", "K")}} for r in conn.execute(text(
        "SELECT kode, tahap, nama, ubah_angka, wajib_alasan FROM ref.jenis_penyesuaian ORDER BY"
        " array_position(ARRAY['METODE','REKON','SIMULASI'], tahap), kode")).mappings()]


@router.get("/penyesuaian")
def daftar(putaran_id: int, wilayah: str | None = None, lapus_id: int | None = None, tahap: str | None = None,
           status: str | None = None, conn: Connection = Depends(koneksi),
           _: Pengguna = Depends(pengguna_aktif)) -> list[dict]:
    rows = conn.execute(text(
        "SELECT a.id, trim(a.wilayah_kode) AS wilayah, a.lapus_id, l.kode AS kode_lapus, l.nama AS nama_lapus,"
        " a.tahap, a.metode_kode AS metode, a.jenis_kode AS jenis, j.nama AS nama_jenis, j.ubah_angka, a.harga,"
        " pe.urut AS periode, a.nilai::float8 AS nilai, a.alasan, a.status, a.diusulkan_pada,"
        " u1.nama AS diusulkan_oleh, a.diputus_pada, u2.nama AS diputus_oleh, a.catatan_putusan FROM lk.penyesuaian a"
        " JOIN ref.lapus l ON l.id = a.lapus_id JOIN ref.periode pe ON pe.id = a.periode_id"
        " JOIN ref.jenis_penyesuaian j ON j.kode = a.jenis_kode LEFT JOIN sec.pengguna u1 ON u1.id = a.diusulkan_oleh"
        " LEFT JOIN sec.pengguna u2 ON u2.id = a.diputus_oleh WHERE a.putaran_id = :p"
        " AND (CAST(:w AS text) IS NULL OR a.wilayah_kode = :w) AND (CAST(:l AS int) IS NULL OR a.lapus_id = :l)"
        " AND (CAST(:t AS text) IS NULL OR a.tahap = :t) AND (CAST(:s AS text) IS NULL OR a.status = :s)"
        " ORDER BY l.urutan, array_position(ARRAY['METODE','REKON','SIMULASI'], a.tahap), a.metode_kode,"
        " a.jenis_kode, a.harga, pe.urut"),
        {"p": putaran_id, "w": wilayah, "l": lapus_id, "t": tahap, "s": status}).mappings().all()
    return [dict(r) | {"label_periode": label(r["periode"])} for r in rows]


# ======================================================================== isi (nilai atau target)
class AdjIn(BaseModel):
    putaran_id: int
    wilayah: str = Field(min_length=4, max_length=4)
    lapus_id: int
    tahap: Literal["METODE", "REKON", "SIMULASI"]
    metode: Literal["REV", "EKS", "DEF"] | None = None
    jenis: str = Field(min_length=2, max_length=20)
    harga: Literal["CP", "K"]
    periode: int
    mode: Literal["nilai", "target_ntb", "target_output", "target_laju", "target_implisit"] = "nilai"
    target: float
    alasan: str | None = Field(default=None, max_length=500)


def _cek_izin(pengguna: Pengguna, tahap: str) -> None:
    perlu = ("simulasi.edit",) if tahap == "SIMULASI" else ("penyesuaian.usul", "penyesuaian.putus")
    if not pengguna.punya(*perlu):
        raise GalatSinergi(403, "TIDAK_BERHAK", "Anda tidak memiliki izin untuk tindakan ini.")


def _siapkan(conn: Connection, data: AdjIn, pengguna: Pengguna) -> dict:
    _cek_izin(pengguna, data.tahap)
    p = ambil_putaran(conn, data.putaran_id)
    pastikan_terbuka(p)
    lap = lapus_td(conn, p["tahun_dasar_id"], data.lapus_id)
    if lap["jenis"] not in BERDATA:
        raise tidak_valid("Penyesuaian hanya pada lapus berdata (daun, TOP, SOP); agregat = jumlah lapus berdata.")
    tahap = conn.execute(text("SELECT tahap FROM ref.jenis_penyesuaian WHERE kode = :k"), {"k": data.jenis}).scalar()
    if tahap != data.tahap:
        raise tidak_valid(f"Jenis {data.jenis} tidak berlaku pada tahap {data.tahap}.")
    if (data.tahap == "METODE") != (data.metode is not None):
        raise tidak_valid("Metode wajib diisi untuk tahap METODE (dan hanya untuk tahap itu).")
    if not p["awal"] <= data.periode <= p["akhir"]:
        raise tidak_valid("Periode di luar cakupan putaran ini.")
    if data.tahap != "SIMULASI" and not pengguna.punya("penyesuaian.putus"):
        cek_tulis(conn, data.wilayah, data.lapus_id)
    return p


def _hitung(conn: Connection, data: AdjIn, p: dict) -> Rincian:
    """Nilai penyesuaian dari mode/target pada pratinjau (draf+diajukan+disetujui) tanpa kunci yang sedang diisi."""
    m, _ = muat(conn, data.putaran_id, data.wilayah, STATUS_PRATINJAU)
    d = m.data.get(data.lapus_id)
    if d is not None:
        d.penyesuaian = [a for a in d.penyesuaian if not (
            a.tahap == data.tahap and a.jenis == data.jenis and a.harga == data.harga and a.periode == data.periode
            and (a.metode or None) == data.metode)]
    h = hitung_wilayah(m)
    hl = h.lapus.get(data.lapus_id)
    if hl is None:
        if data.mode == "nilai":
            return Rincian(data.target)
        raise GalatTarget("Lapus ini belum punya hasil hitung; isi nilai langsung.")
    t = h.sumbu.i(data.periode)
    t4 = h.sumbu.i(data.periode - 4) if data.periode - 4 >= p["awal"] else None
    dasar = None
    if data.tahap == "METODE":
        dasar, hasil = hl.metode[data.metode or ""]
    elif data.jenis == "ADJ3":
        hasil, dasar = hl.tahap["POST"], hl.tahap["PRE"]
    elif data.tahap == "REKON":
        hasil = hl.tahap["BENC"]
    else:
        hasil = hl.tahap["FINAL"]
    return nilai_penyesuaian(data.jenis, data.harga, data.mode, data.target, t, t4, hasil, dasar)


def _rincian(r: Rincian, data: AdjIn) -> dict[str, Any]:
    return {"nilai": r.nilai, "target_ntb": r.target_ntb, "target_output": r.target_output,
            "ntb_sebelum": r.ntb_sebelum, "output_sebelum": r.output_sebelum, "mode": data.mode,
            "label_periode": label(data.periode)}


def _galat_target(e: GalatTarget) -> GalatSinergi:
    return GalatSinergi(422, "TARGET_TIDAK_DAPAT", str(e))


@router.post("/penyesuaian/hitung")
def pratinjau_nilai(data: AdjIn, conn: Connection = Depends(koneksi),
                    pengguna: Pengguna = Depends(pengguna_aktif)) -> dict:
    """Pratinjau dialog: nilai penyesuaian dari target (tidak disimpan)."""
    p = _siapkan(conn, data, pengguna)
    try:
        return _rincian(_hitung(conn, data, p), data)
    except GalatTarget as e:
        raise _galat_target(e) from e


@router.post("/penyesuaian", status_code=201)
def simpan(data: AdjIn, conn: Connection = Depends(koneksi), pengguna: Pengguna = Depends(pengguna_aktif)) -> dict:
    """Simpan penyesuaian (upsert per kunci). Nilai dari target dihitung di server. Status kembali ke draf."""
    p = _siapkan(conn, data, pengguna)
    try:
        r = _hitung(conn, data, p) if data.mode != "nilai" else Rincian(data.target)
    except GalatTarget as e:
        raise _galat_target(e) from e
    alasan = rapikan(data.alasan) or None
    q = {"p": data.putaran_id, "w": data.wilayah, "l": data.lapus_id, "t": data.tahap, "m": data.metode,
         "j": data.jenis, "h": data.harga, "u": data.periode, "v": r.nilai, "a": alasan}
    if alasan:
        conn.execute(text("SELECT set_config('app.alasan', :a, true)"), q)
    ada = conn.execute(text(
        "SELECT a.id FROM lk.penyesuaian a JOIN ref.periode pe ON pe.id = a.periode_id WHERE a.putaran_id = :p"
        " AND a.wilayah_kode = :w AND a.lapus_id = :l AND a.tahap = :t AND a.metode_kode IS NOT DISTINCT FROM :m"
        " AND a.jenis_kode = :j AND a.harga = :h AND pe.urut = :u"), q).scalar()
    if ada is None:
        aid = conn.execute(text(
            "INSERT INTO lk.penyesuaian (putaran_id, wilayah_kode, lapus_id, tahap, metode_kode, jenis_kode, harga,"
            " periode_id, nilai, alasan, status, diusulkan_oleh) SELECT :p, :w, :l, :t, :m, :j, :h, pe.id, :v, :a,"
            " 'draf', sec.uid() FROM ref.periode pe WHERE pe.urut = :u RETURNING id"), q).scalar_one()
    else:
        aid = ada
        conn.execute(text(
            "UPDATE lk.penyesuaian SET nilai = :v, alasan = :a, status = 'draf', diusulkan_oleh = sec.uid(),"
            " diusulkan_pada = now(), diputus_oleh = NULL, diputus_pada = NULL, catatan_putusan = NULL"
            " WHERE id = :id"), {**q, "id": ada})
    if data.tahap != "SIMULASI":
        tandai_ubah(conn, data.putaran_id, [(data.wilayah, data.lapus_id)], f"penyesuaian {data.jenis}")
    antrekan(conn, data.putaran_id, data.wilayah, data.lapus_id, f"penyesuaian {data.jenis}")
    return {"id": aid, **_rincian(r, data), "status": "draf",
            "pesan": "Penyesuaian tersimpan sebagai draf (masuk angka resmi setelah disetujui)."}


@router.delete("/penyesuaian/{adj_id}")
def hapus(adj_id: int, conn: Connection = Depends(koneksi), pengguna: Pengguna = Depends(pengguna_aktif)) -> dict:
    a = conn.execute(text("SELECT putaran_id, trim(wilayah_kode) AS w, lapus_id, tahap, jenis_kode FROM lk.penyesuaian"
                          " WHERE id = :i"), {"i": adj_id}).mappings().first()
    if a is None:
        raise tidak_ada("Penyesuaian")
    _cek_izin(pengguna, a["tahap"])
    pastikan_terbuka(ambil_putaran(conn, a["putaran_id"]))
    if a["tahap"] != "SIMULASI" and not pengguna.punya("penyesuaian.putus"):
        cek_tulis(conn, a["w"], a["lapus_id"])
    conn.execute(text("DELETE FROM lk.penyesuaian WHERE id = :i"), {"i": adj_id})
    if a["tahap"] != "SIMULASI":
        tandai_ubah(conn, a["putaran_id"], [(a["w"], a["lapus_id"])], f"hapus penyesuaian {a['jenis_kode']}")
    antrekan(conn, a["putaran_id"], a["w"], a["lapus_id"], "hapus penyesuaian")
    return {"pesan": "Penyesuaian dihapus."}


# ======================================================================== putus
class PutusIn(BaseModel):
    putaran_id: int
    id: list[int] = Field(min_length=1, max_length=5000)
    keputusan: Literal["setujui", "tolak"]
    catatan: str | None = Field(default=None, max_length=500)


def putus_penyesuaian(conn: Connection, putaran_id: int, ids: list[int], keputusan: str, catatan: str | None) -> int:
    """Setujui/tolak: METODE/REKON harus `diajukan`; SIMULASI boleh `draf`/`diajukan`. Kembalikan jumlah baris."""
    pastikan_terbuka(ambil_putaran(conn, putaran_id))
    c = rapikan(catatan)
    if keputusan == "tolak" and len(c) < 10:
        raise tidak_valid("Alasan penolakan wajib diisi (min. 10 karakter).")
    rows = conn.execute(text(
        "SELECT id, trim(wilayah_kode) AS w, lapus_id, tahap, status FROM lk.penyesuaian WHERE putaran_id = :p"
        " AND id = ANY(:i)"), {"p": putaran_id, "i": ids}).mappings().all()
    if len(rows) != len(set(ids)):
        raise tidak_ada("Penyesuaian")
    salah = [r for r in rows if r["status"] not in (("draf", "diajukan") if r["tahap"] == "SIMULASI"
                                                       else ("diajukan",))]
    if salah:
        raise GalatSinergi(409, "STATUS_PENYESUAIAN", f"{len(salah)} penyesuaian belum diajukan atau sudah diputus.")
    conn.execute(text(
        "UPDATE lk.penyesuaian SET status = :st, diputus_oleh = sec.uid(), diputus_pada = now(), catatan_putusan = :c"
        " WHERE id = ANY(:i)"), {"st": "disetujui" if keputusan == "setujui" else "ditolak", "c": c or None,
                                 "i": [r["id"] for r in rows]})
    for w in sorted({r["w"] for r in rows}):
        antrekan(conn, putaran_id, w, None, "putusan penyesuaian")
    return len(rows)


@router.post("/penyesuaian/putus")
def putus(data: PutusIn, conn: Connection = Depends(koneksi), _: Pengguna = PUTUS) -> dict:
    n = putus_penyesuaian(conn, data.putaran_id, data.id, data.keputusan, data.catatan)
    return {"jumlah": n, "pesan": f"{n} penyesuaian {'disetujui' if data.keputusan == 'setujui' else 'ditolak'}."}
