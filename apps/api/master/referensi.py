"""Master referensi: konkordansi lapus, katalog komoditas, satuan, sumber data, wilayah."""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import Connection, text

from ..app.deps import butuh_izin, koneksi
from .umum import hapus_atau_nonaktifkan, pesan_hapus, rapikan, sql_hapus, tidak_ada, tidak_valid

router = APIRouter(prefix="/api", tags=["master"])
KELOLA = Depends(butuh_izin("master.kelola"))
TOLERANSI_BOBOT = 1e-9


# =============================================================== konkordansi
class KonkordansiIn(BaseModel):
    lapus_asal_id: int
    lapus_tujuan_id: int
    bobot: float | None = Field(default=None, ge=0, le=1)
    catatan: str | None = None


class KonkordansiUbah(BaseModel):
    bobot: float | None = Field(default=None, ge=0, le=1)
    catatan: str | None = None


def _cek_bobot(conn: Connection, asal_id: int) -> None:
    jml = conn.execute(text("SELECT coalesce(sum(bobot), 0) FROM ref.konkordansi_lapus WHERE lapus_asal_id = :a"),
                       {"a": asal_id}).scalar_one()
    if float(jml) > 1 + TOLERANSI_BOBOT:
        raise tidak_valid(f"Jumlah bobot untuk lapus asal ini menjadi {float(jml):.4f}; tidak boleh lebih dari 1.")


@router.get("/konkordansi")
def daftar_konkordansi(asal_td: int | None = None, tujuan_td: int | None = None,
                       conn: Connection = Depends(koneksi)) -> dict:
    rows = conn.execute(text(
        "SELECT k.id, k.lapus_asal_id, a.kode AS kode_asal, a.nama AS nama_asal, ta.kode AS td_asal,"
        " k.lapus_tujuan_id, b.kode AS kode_tujuan, b.nama AS nama_tujuan, tb.kode AS td_tujuan, k.bobot, k.catatan"
        " FROM ref.konkordansi_lapus k JOIN ref.lapus a ON a.id = k.lapus_asal_id"
        " JOIN ref.lapus b ON b.id = k.lapus_tujuan_id JOIN ref.tahun_dasar ta ON ta.id = a.tahun_dasar_id"
        " JOIN ref.tahun_dasar tb ON tb.id = b.tahun_dasar_id"
        " WHERE (CAST(:at AS int) IS NULL OR a.tahun_dasar_id = :at)"
        "   AND (CAST(:tt AS int) IS NULL OR b.tahun_dasar_id = :tt)"
        " ORDER BY a.urutan, b.urutan"), {"at": asal_td, "tt": tujuan_td}).mappings().all()
    ringkas: dict[str, dict] = {}
    for r in rows:
        x = ringkas.setdefault(r["kode_asal"], {"jumlah_tujuan": 0, "jumlah_bobot": 0.0, "bobot_kosong": 0})
        x["jumlah_tujuan"] += 1
        if r["bobot"] is None:
            x["bobot_kosong"] += 1
        else:
            x["jumlah_bobot"] += float(r["bobot"])
    for x in ringkas.values():
        # 1:1 tanpa bobot dianggap penuh; 1:N wajib berbobot (laporan jembatan memakai jumlah kategori bila kosong).
        x["lengkap"] = x["bobot_kosong"] == 0 and abs(x["jumlah_bobot"] - 1) <= 1e-6
    return {"baris": [dict(r) | {"bobot": None if r["bobot"] is None else float(r["bobot"])} for r in rows],
            "ringkasan_asal": ringkas}


@router.post("/konkordansi", status_code=201)
def tambah_konkordansi(data: KonkordansiIn, conn: Connection = Depends(koneksi), _=KELOLA) -> dict:
    td = conn.execute(text("SELECT (SELECT tahun_dasar_id FROM ref.lapus WHERE id = :a),"
                           " (SELECT tahun_dasar_id FROM ref.lapus WHERE id = :b)"),
                      {"a": data.lapus_asal_id, "b": data.lapus_tujuan_id}).one()
    if td[0] is None or td[1] is None:
        raise tidak_ada("Lapus asal/tujuan")
    if td[0] == td[1]:
        raise tidak_valid("Lapus asal dan tujuan harus dari tahun dasar yang berbeda.")
    kid = conn.execute(text(
        "INSERT INTO ref.konkordansi_lapus (lapus_asal_id, lapus_tujuan_id, bobot, catatan)"
        " VALUES (:a, :b, :w, :c) RETURNING id"),
        {"a": data.lapus_asal_id, "b": data.lapus_tujuan_id, "w": data.bobot,
         "c": rapikan(data.catatan) or None}).scalar_one()
    _cek_bobot(conn, data.lapus_asal_id)
    return {"id": kid}


@router.patch("/konkordansi/{kid}")
def ubah_konkordansi(kid: int, data: KonkordansiUbah, conn: Connection = Depends(koneksi), _=KELOLA) -> dict:
    f = data.model_fields_set
    r = conn.execute(text(
        "UPDATE ref.konkordansi_lapus SET bobot = CASE WHEN :ub THEN CAST(:w AS numeric) ELSE bobot END,"
        " catatan = CASE WHEN :uc THEN :c ELSE catatan END WHERE id = :i RETURNING lapus_asal_id"),
        {"ub": "bobot" in f, "w": data.bobot, "uc": "catatan" in f, "c": rapikan(data.catatan) or None,
         "i": kid}).first()
    if r is None:
        raise tidak_ada("Konkordansi")
    _cek_bobot(conn, r[0])
    return {"id": kid}


@router.delete("/konkordansi/{kid}")
def hapus_konkordansi(kid: int, conn: Connection = Depends(koneksi), _=KELOLA) -> dict:
    if conn.execute(text("DELETE FROM ref.konkordansi_lapus WHERE id = :i"), {"i": kid}).rowcount == 0:
        raise tidak_ada("Konkordansi")
    return pesan_hapus("Konkordansi", "dihapus")


# =============================================================== katalog komoditas
class KatalogIn(BaseModel):
    nama_baku: str = Field(min_length=1, max_length=200)
    sinonim: list[str] = []
    satuan_kode: str | None = None
    kbli: str | None = Field(default=None, max_length=10)
    catatan: str | None = None


class KatalogUbah(BaseModel):
    nama_baku: str | None = Field(default=None, min_length=1, max_length=200)
    sinonim: list[str] | None = None
    satuan_kode: str | None = None
    kbli: str | None = Field(default=None, max_length=10)
    catatan: str | None = None
    aktif: bool | None = None


_KOLOM_KAT = "id, nama_baku, sinonim, satuan_kode, kbli, catatan, aktif"


def _sinonim(nama: str, daftar: list[str]) -> list[str]:
    hasil: dict[str, str] = {}
    for s in daftar:
        s = rapikan(s)
        if s and s.lower() != nama.lower():
            hasil.setdefault(s.lower(), s)
    return list(hasil.values())


def _cek_nama_katalog(conn: Connection, nama: str, sinonim: list[str], kecuali: int | None) -> None:
    semua = [nama, *sinonim]
    r = conn.execute(text(
        "SELECT nama_baku FROM ref.katalog_komoditas WHERE id IS DISTINCT FROM :k AND"
        " (lower(nama_baku) = ANY(:n) OR EXISTS (SELECT 1 FROM unnest(sinonim) s WHERE lower(s) = ANY(:n)))"
        " LIMIT 1"), {"k": kecuali, "n": [x.lower() for x in semua]}).first()
    if r is not None:
        raise tidak_valid(f"Nama atau sinonim sudah dipakai komoditas baku '{r[0]}'.")


@router.get("/katalog")
def daftar_katalog(q: str | None = Query(default=None, max_length=100), conn: Connection = Depends(koneksi)) -> list:
    rows = conn.execute(text(
        f"SELECT {_KOLOM_KAT} FROM ref.katalog_komoditas WHERE CAST(:q AS text) IS NULL"
        " OR nama_baku ILIKE '%' || :q || '%'"
        " OR EXISTS (SELECT 1 FROM unnest(sinonim) s WHERE s ILIKE '%' || :q || '%')"
        " ORDER BY nama_baku LIMIT 500"), {"q": rapikan(q) or None}).mappings().all()
    return [dict(r) for r in rows]


@router.post("/katalog", status_code=201)
def tambah_katalog(data: KatalogIn, conn: Connection = Depends(koneksi), _=KELOLA) -> dict:
    nama = rapikan(data.nama_baku)
    sin = _sinonim(nama, data.sinonim)
    _cek_nama_katalog(conn, nama, sin, None)
    r = conn.execute(text(
        "INSERT INTO ref.katalog_komoditas (nama_baku, sinonim, satuan_kode, kbli, catatan)"
        f" VALUES (:n, :s, :sat, :kbli, :c) RETURNING {_KOLOM_KAT}"),
        {"n": nama, "s": sin, "sat": data.satuan_kode or None, "kbli": rapikan(data.kbli) or None,
         "c": rapikan(data.catatan) or None}).mappings().one()
    return dict(r)


@router.patch("/katalog/{kid}")
def ubah_katalog(kid: int, data: KatalogUbah, conn: Connection = Depends(koneksi), _=KELOLA) -> dict:
    lama = conn.execute(text(f"SELECT {_KOLOM_KAT} FROM ref.katalog_komoditas WHERE id = :i"),
                        {"i": kid}).mappings().first()
    if lama is None:
        raise tidak_ada("Komoditas")
    f = data.model_fields_set
    nama = rapikan(data.nama_baku) if data.nama_baku else lama["nama_baku"]
    sin = _sinonim(nama, data.sinonim if data.sinonim is not None else lama["sinonim"])
    _cek_nama_katalog(conn, nama, sin, kid)
    r = conn.execute(text(
        "UPDATE ref.katalog_komoditas SET nama_baku = :n, sinonim = :s, satuan_kode = :sat, kbli = :kbli,"
        f" catatan = :c, aktif = :a WHERE id = :i RETURNING {_KOLOM_KAT}"),
        {"n": nama, "s": sin, "i": kid,
         "sat": (data.satuan_kode or None) if "satuan_kode" in f else lama["satuan_kode"],
         "kbli": (rapikan(data.kbli) or None) if "kbli" in f else lama["kbli"],
         "c": (rapikan(data.catatan) or None) if "catatan" in f else lama["catatan"],
         "a": data.aktif if data.aktif is not None else lama["aktif"]}).mappings().one()
    return dict(r)


@router.delete("/katalog/{kid}")
def hapus_katalog(kid: int, conn: Connection = Depends(koneksi), _=KELOLA) -> dict:
    h = hapus_atau_nonaktifkan(conn, sql_hapus("DELETE FROM ref.katalog_komoditas WHERE id = :i", i=kid),
                               sql_hapus("UPDATE ref.katalog_komoditas SET aktif = false WHERE id = :i", i=kid),
                               "Komoditas")
    return pesan_hapus("Komoditas", h)


# =============================================================== satuan
class SatuanIn(BaseModel):
    kode: str = Field(min_length=1, max_length=30)
    nama: str = Field(min_length=1, max_length=100)


class SatuanUbah(BaseModel):
    nama: str | None = Field(default=None, min_length=1, max_length=100)
    aktif: bool | None = None


@router.get("/satuan")
def daftar_satuan(conn: Connection = Depends(koneksi)) -> list[dict]:
    return [dict(r) for r in conn.execute(text("SELECT kode, nama, aktif FROM ref.satuan ORDER BY kode")).mappings()]


@router.post("/satuan", status_code=201)
def tambah_satuan(data: SatuanIn, conn: Connection = Depends(koneksi), _=KELOLA) -> dict:
    r = conn.execute(text("INSERT INTO ref.satuan (kode, nama) VALUES (:k, :n) RETURNING kode, nama, aktif"),
                     {"k": rapikan(data.kode), "n": rapikan(data.nama)}).mappings().one()
    return dict(r)


@router.patch("/satuan/{kode}")
def ubah_satuan(kode: str, data: SatuanUbah, conn: Connection = Depends(koneksi), _=KELOLA) -> dict:
    r = conn.execute(text("UPDATE ref.satuan SET nama = coalesce(:n, nama), aktif = coalesce(:a, aktif)"
                          " WHERE kode = :k RETURNING kode, nama, aktif"),
                     {"n": rapikan(data.nama) or None, "a": data.aktif, "k": kode}).mappings().first()
    if r is None:
        raise tidak_ada("Satuan")
    return dict(r)


@router.delete("/satuan/{kode}")
def hapus_satuan(kode: str, conn: Connection = Depends(koneksi), _=KELOLA) -> dict:
    h = hapus_atau_nonaktifkan(conn, sql_hapus("DELETE FROM ref.satuan WHERE kode = :k", k=kode),
                               sql_hapus("UPDATE ref.satuan SET aktif = false WHERE kode = :k", k=kode), "Satuan")
    return pesan_hapus("Satuan", h)


# =============================================================== sumber data
class SumberIn(BaseModel):
    nama: str = Field(min_length=1, max_length=200)
    instansi: str | None = None
    keterangan: str | None = None


class SumberUbah(BaseModel):
    nama: str | None = Field(default=None, min_length=1, max_length=200)
    instansi: str | None = None
    keterangan: str | None = None
    aktif: bool | None = None


_KOLOM_SUMBER = "id, nama, instansi, keterangan, aktif"


@router.get("/sumber-data")
def daftar_sumber(conn: Connection = Depends(koneksi)) -> list[dict]:
    rows = conn.execute(text(f"SELECT {_KOLOM_SUMBER} FROM ref.sumber_data ORDER BY nama")).mappings()
    return [dict(r) for r in rows]


@router.post("/sumber-data", status_code=201)
def tambah_sumber(data: SumberIn, conn: Connection = Depends(koneksi), _=KELOLA) -> dict:
    r = conn.execute(text(f"INSERT INTO ref.sumber_data (nama, instansi, keterangan) VALUES (:n, :i, :k)"
                          f" RETURNING {_KOLOM_SUMBER}"),
                     {"n": rapikan(data.nama), "i": rapikan(data.instansi) or None,
                      "k": rapikan(data.keterangan) or None}).mappings().one()
    return dict(r)


@router.patch("/sumber-data/{sid}")
def ubah_sumber(sid: int, data: SumberUbah, conn: Connection = Depends(koneksi), _=KELOLA) -> dict:
    f = data.model_fields_set
    r = conn.execute(text(
        "UPDATE ref.sumber_data SET nama = coalesce(:n, nama), aktif = coalesce(:a, aktif),"
        " instansi = CASE WHEN :ui THEN :i ELSE instansi END, keterangan = CASE WHEN :uk THEN :k ELSE keterangan END"
        f" WHERE id = :id RETURNING {_KOLOM_SUMBER}"),
        {"n": rapikan(data.nama) or None, "a": data.aktif, "ui": "instansi" in f, "i": rapikan(data.instansi) or None,
         "uk": "keterangan" in f, "k": rapikan(data.keterangan) or None, "id": sid}).mappings().first()
    if r is None:
        raise tidak_ada("Sumber data")
    return dict(r)


@router.delete("/sumber-data/{sid}")
def hapus_sumber(sid: int, conn: Connection = Depends(koneksi), _=KELOLA) -> dict:
    h = hapus_atau_nonaktifkan(conn, sql_hapus("DELETE FROM ref.sumber_data WHERE id = :i", i=sid),
                               sql_hapus("UPDATE ref.sumber_data SET aktif = false WHERE id = :i", i=sid),
                               "Sumber data")
    return pesan_hapus("Sumber data", h)


# =============================================================== wilayah
LevelWilayah = Literal["provinsi", "kabupaten", "kota"]


class WilayahIn(BaseModel):
    kode: str = Field(pattern=r"^\d{4}$")
    nama: str = Field(min_length=1, max_length=100)
    level: LevelWilayah
    induk: str | None = Field(default=None, pattern=r"^\d{4}$")
    urutan: int = Field(default=0, ge=0, le=999)


class WilayahUbah(BaseModel):
    nama: str | None = Field(default=None, min_length=1, max_length=100)
    level: LevelWilayah | None = None
    induk: str | None = Field(default=None, pattern=r"^\d{4}$")
    urutan: int | None = Field(default=None, ge=0, le=999)
    aktif: bool | None = None


_KOLOM_WIL = "kode, nama, level, induk, urutan, aktif"


@router.get("/wilayah")
def daftar_wilayah(conn: Connection = Depends(koneksi)) -> list[dict]:
    rows = conn.execute(text(f"SELECT {_KOLOM_WIL} FROM ref.wilayah ORDER BY urutan, kode")).mappings()
    return [dict(r) for r in rows]


@router.post("/wilayah", status_code=201)
def tambah_wilayah(data: WilayahIn, conn: Connection = Depends(koneksi), _=KELOLA) -> dict:
    if data.induk == data.kode:
        raise tidak_valid("Induk wilayah tidak boleh dirinya sendiri.")
    r = conn.execute(text(f"INSERT INTO ref.wilayah ({_KOLOM_WIL}) VALUES (:kode, :nama, :level, :induk, :urutan,"
                          f" true) RETURNING {_KOLOM_WIL}"), data.model_dump() | {"nama": rapikan(data.nama)})
    return dict(r.mappings().one())


@router.patch("/wilayah/{kode}")
def ubah_wilayah(kode: str, data: WilayahUbah, conn: Connection = Depends(koneksi), _=KELOLA) -> dict:
    f = data.model_fields_set
    if data.induk == kode:
        raise tidak_valid("Induk wilayah tidak boleh dirinya sendiri.")
    r = conn.execute(text(
        "UPDATE ref.wilayah SET nama = coalesce(:nama, nama), level = coalesce(:level, level),"
        " urutan = coalesce(:urutan, urutan), aktif = coalesce(:aktif, aktif),"
        f" induk = CASE WHEN :ui THEN :induk ELSE induk END WHERE kode = :kode RETURNING {_KOLOM_WIL}"),
        {"nama": rapikan(data.nama) or None, "level": data.level, "urutan": data.urutan, "aktif": data.aktif,
         "ui": "induk" in f, "induk": data.induk, "kode": kode}).mappings().first()
    if r is None:
        raise tidak_ada("Wilayah")
    return dict(r)


@router.delete("/wilayah/{kode}")
def hapus_wilayah(kode: str, conn: Connection = Depends(koneksi), _=KELOLA) -> dict:
    h = hapus_atau_nonaktifkan(conn, sql_hapus("DELETE FROM ref.wilayah WHERE kode = :k", k=kode),
                               sql_hapus("UPDATE ref.wilayah SET aktif = false WHERE kode = :k", k=kode), "Wilayah")
    return pesan_hapus("Wilayah", h)
