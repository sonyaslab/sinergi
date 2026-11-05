"""Master tahun dasar. Hapus = arsip bila sudah dipakai (lapus berdata, putaran, item, penugasan)."""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import Connection, text

from ..app.deps import butuh_izin, koneksi
from .umum import hapus_atau_nonaktifkan, pesan_hapus, rapikan, sql_hapus, tidak_ada, tidak_valid

router = APIRouter(prefix="/api", tags=["master"])
KELOLA = Depends(butuh_izin("master.kelola"))

Status = Literal["rencana", "paralel", "produksi", "arsip"]
Klasifikasi = Literal["KBLI2020", "KBLI2025"]
_KOLOM = ("id, kode, tahun_dasar, status, klasifikasi, tahun_awal_seri, tahun_baseline_eks, keterangan,"
          " jangkar_dari_data")
# Urutan pemilih: produksi -> paralel -> rencana -> arsip (dari kolom status, bukan kode TD).
_URUT_STATUS = "CASE status WHEN 'produksi' THEN 0 WHEN 'paralel' THEN 1 WHEN 'rencana' THEN 2 ELSE 3 END"


class TahunDasarIn(BaseModel):
    kode: str = Field(pattern=r"^TD\d{4}$", description="mis. TD2025")
    tahun_dasar: int = Field(ge=2000, le=2100)
    status: Status = "rencana"
    klasifikasi: Klasifikasi
    tahun_awal_seri: int = Field(ge=2000, le=2100)
    tahun_baseline_eks: int = Field(ge=2000, le=2100)
    keterangan: str | None = None
    jangkar_dari_data: bool = True
    salin_pohon_dari: int | None = Field(default=None, description="id tahun dasar sumber pohon lapus (opsional)")


class TahunDasarUbah(BaseModel):
    status: Status | None = None
    tahun_awal_seri: int | None = Field(default=None, ge=2000, le=2100)
    tahun_baseline_eks: int | None = Field(default=None, ge=2000, le=2100)
    keterangan: str | None = None
    jangkar_dari_data: bool | None = None


def _cek_tahun(conn: Connection, awal: int, baseline: int) -> None:
    if awal > baseline:
        raise tidak_valid("Tahun awal seri tidak boleh sesudah tahun baseline.")
    lo, hi = conn.execute(text("SELECT min(tahun), max(tahun) FROM ref.periode")).one()
    if not (lo <= awal <= hi and lo <= baseline <= hi):
        raise tidak_valid(f"Tahun harus di antara {lo} dan {hi} (tabel periode).")


@router.get("/tahun-dasar")
def daftar(conn: Connection = Depends(koneksi)) -> list[dict]:
    rows = conn.execute(text(f"SELECT {_KOLOM} FROM ref.tahun_dasar ORDER BY {_URUT_STATUS}, tahun_dasar DESC"))
    return [dict(r) for r in rows.mappings()]


def salin_pohon(conn: Connection, dari: int, ke: int) -> int:
    """Salin pohon lapus + keanggotaan kelompok dari tahun dasar `dari` ke `ke` (urutan, induk, jenis, migas)."""
    n = conn.execute(text(
        "INSERT INTO ref.lapus (tahun_dasar_id, kode, nama, level, urutan, jenis, kode_lk_bps, is_migas, aktif)"
        " SELECT :ke, kode, nama, level, urutan, jenis, kode_lk_bps, is_migas, aktif FROM ref.lapus"
        " WHERE tahun_dasar_id = :dari"), {"dari": dari, "ke": ke}).rowcount
    conn.execute(text(
        "UPDATE ref.lapus b SET induk_id = bi.id FROM ref.lapus a JOIN ref.lapus ai ON ai.id = a.induk_id"
        " JOIN ref.lapus bi ON bi.tahun_dasar_id = :ke AND bi.kode = ai.kode"
        " WHERE a.tahun_dasar_id = :dari AND b.tahun_dasar_id = :ke AND b.kode = a.kode"), {"dari": dari, "ke": ke})
    conn.execute(text(
        "INSERT INTO ref.lapus_kelompok (kelompok_id, anggota_id)"
        " SELECT bk.id, ba.id FROM ref.lapus_kelompok lk JOIN ref.lapus k ON k.id = lk.kelompok_id"
        " JOIN ref.lapus a ON a.id = lk.anggota_id"
        " JOIN ref.lapus bk ON bk.tahun_dasar_id = :ke AND bk.kode = k.kode"
        " JOIN ref.lapus ba ON ba.tahun_dasar_id = :ke AND ba.kode = a.kode"
        " WHERE k.tahun_dasar_id = :dari"), {"dari": dari, "ke": ke})
    return n


@router.post("/tahun-dasar", status_code=201)
def tambah(data: TahunDasarIn, conn: Connection = Depends(koneksi), _=KELOLA) -> dict:
    _cek_tahun(conn, data.tahun_awal_seri, data.tahun_baseline_eks)
    if data.salin_pohon_dari is not None and conn.execute(
            text("SELECT 1 FROM ref.tahun_dasar WHERE id = :i"), {"i": data.salin_pohon_dari}).first() is None:
        raise tidak_ada("Tahun dasar sumber pohon")
    r = conn.execute(text(
        "INSERT INTO ref.tahun_dasar (kode, tahun_dasar, status, klasifikasi, tahun_awal_seri, tahun_baseline_eks,"
        " keterangan, jangkar_dari_data) VALUES (:kode, :td, :st, :kl, :aw, :bs, :ket, :jd)"
        f" RETURNING {_KOLOM}"),
        {"kode": data.kode, "td": data.tahun_dasar, "st": data.status, "kl": data.klasifikasi,
         "aw": data.tahun_awal_seri, "bs": data.tahun_baseline_eks, "ket": rapikan(data.keterangan) or None,
         "jd": data.jangkar_dari_data}).mappings().one()
    hasil = dict(r)
    if data.salin_pohon_dari is not None:
        hasil["lapus_disalin"] = salin_pohon(conn, data.salin_pohon_dari, r["id"])
    return hasil


@router.patch("/tahun-dasar/{td_id}")
def ubah(td_id: int, data: TahunDasarUbah, conn: Connection = Depends(koneksi), _=KELOLA) -> dict:
    lama = conn.execute(text(f"SELECT {_KOLOM} FROM ref.tahun_dasar WHERE id = :i"), {"i": td_id}).mappings().first()
    if lama is None:
        raise tidak_ada("Tahun dasar")
    baru = {**dict(lama), **data.model_dump(exclude_unset=True)}
    if "keterangan" in data.model_fields_set:
        baru["keterangan"] = rapikan(data.keterangan) or None
    _cek_tahun(conn, baru["tahun_awal_seri"], baru["tahun_baseline_eks"])
    r = conn.execute(text(
        "UPDATE ref.tahun_dasar SET status = :status, tahun_awal_seri = :tahun_awal_seri,"
        " tahun_baseline_eks = :tahun_baseline_eks, keterangan = :keterangan, jangkar_dari_data = :jangkar_dari_data"
        f" WHERE id = :id RETURNING {_KOLOM}"), baru).mappings().one()
    return dict(r)


@router.delete("/tahun-dasar/{td_id}")
def hapus(td_id: int, conn: Connection = Depends(koneksi), _=KELOLA) -> dict:
    def _hapus(c: Connection) -> int:
        # Pohon tanpa data ikut terhapus; bila ada data (item, putaran, penugasan, hasil) FK menolak -> arsip.
        p = {"i": td_id}
        c.execute(text("DELETE FROM ref.lapus_kelompok WHERE kelompok_id IN"
                       " (SELECT id FROM ref.lapus WHERE tahun_dasar_id = :i)"), p)
        c.execute(text("DELETE FROM ref.konkordansi_lapus WHERE lapus_asal_id IN (SELECT id FROM ref.lapus"
                       " WHERE tahun_dasar_id = :i) OR lapus_tujuan_id IN (SELECT id FROM ref.lapus"
                       " WHERE tahun_dasar_id = :i)"), p)
        c.execute(text("DELETE FROM ref.lapus WHERE tahun_dasar_id = :i"), p)
        return c.execute(text("DELETE FROM ref.tahun_dasar WHERE id = :i"), p).rowcount

    h = hapus_atau_nonaktifkan(conn, _hapus, sql_hapus(
        "UPDATE ref.tahun_dasar SET status = 'arsip' WHERE id = :i", i=td_id), "Tahun dasar")
    r = pesan_hapus("Tahun dasar", h)
    if h == "dinonaktifkan":
        r["pesan"] = "Tahun dasar sudah dipakai data, jadi diarsipkan (baca saja)."
    return r
