"""Pohon lapangan usaha per tahun dasar = format baris tabel pokok.

Aturan urutan: `ref.lapus.urutan` selalu hasil penelusuran depth-first pohon (anak tepat di bawah induknya), dengan
urutan antarsaudara yang diatur admin (seret/naik-turun). Setiap tambah/pindah/hapus menyusun ulang urutan, sehingga
`lk.v_tabel_pokok` langsung mengikuti tanpa mengubah kode. `level` dihitung dari kedalaman pohon.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import Connection, text

from ..app.deps import butuh_izin, koneksi
from .umum import hapus_atau_nonaktifkan, pesan_hapus, rapikan, sql_hapus, tidak_ada, tidak_valid

router = APIRouter(prefix="/api", tags=["master"])
KELOLA = Depends(butuh_izin("master.kelola"))

Jenis = Literal["kategori", "sub", "daun", "kelompok", "ntb", "top", "sop", "topsop", "pdrb", "pdrb_nonmigas"]
TOTAL = {"ntb", "top", "sop", "topsop", "pdrb", "pdrb_nonmigas"}
TANPA_INDUK = TOTAL | {"kelompok", "kategori"}
BISA_INDUK = {"kategori", "sub"}
BERITEM = {"daun", "top", "sop"}  # baris yang boleh punya item data dasar (TOP/SOP: keputusan metodologi)
LEVEL_MAKS = 4
POLA_KODE = r"^[A-Za-z0-9][A-Za-z0-9.,]{0,19}$"

_KOLOM = "id, tahun_dasar_id, kode, nama, induk_id, level, urutan, jenis, kode_lk_bps, is_migas, aktif"


class LapusIn(BaseModel):
    kode: str = Field(pattern=POLA_KODE)
    nama: str = Field(min_length=1, max_length=300)
    jenis: Jenis
    induk_id: int | None = None
    kode_lk_bps: str | None = Field(default=None, max_length=20)
    is_migas: bool = False
    sesudah_id: int | None = Field(default=None, description="letakkan sesudah saudara ini; kosong = paling akhir")


class LapusUbah(BaseModel):
    kode: str | None = Field(default=None, pattern=POLA_KODE)
    nama: str | None = Field(default=None, min_length=1, max_length=300)
    jenis: Jenis | None = None
    induk_id: int | None = None
    kode_lk_bps: str | None = Field(default=None, max_length=20)
    is_migas: bool | None = None
    aktif: bool | None = None


class UrutanIn(BaseModel):
    induk_id: int | None = None
    anak: list[int] = Field(min_length=1)


class AnggotaIn(BaseModel):
    anggota_ids: list[int]


# ------------------------------------------------------------------ bantu
def ambil(conn: Connection, lapus_id: int) -> dict:
    r = conn.execute(text(f"SELECT {_KOLOM} FROM ref.lapus WHERE id = :i"), {"i": lapus_id}).mappings().first()
    if r is None:
        raise tidak_ada("Lapus")
    return dict(r)


def _ada(conn: Connection, sql: str, **p: object) -> bool:
    return conn.execute(text(f"SELECT EXISTS ({sql})"), p).scalar_one()


def punya_anak(conn: Connection, lapus_id: int, hanya_aktif: bool = False) -> bool:
    return _ada(conn, "SELECT 1 FROM ref.lapus WHERE induk_id = :i" + (" AND aktif" if hanya_aktif else ""),
                i=lapus_id)


def punya_item(conn: Connection, lapus_id: int) -> bool:
    return _ada(conn, "SELECT 1 FROM lk.item WHERE lapus_id = :i", i=lapus_id)


def keturunan(conn: Connection, lapus_id: int) -> set[int]:
    rows = conn.execute(text(
        "WITH RECURSIVE t AS (SELECT id FROM ref.lapus WHERE induk_id = :i"
        " UNION ALL SELECT l.id FROM ref.lapus l JOIN t ON l.induk_id = t.id) SELECT id FROM t"), {"i": lapus_id})
    return {r[0] for r in rows}


def _cek_struktur(conn: Connection, td_id: int, jenis: str, induk_id: int | None, lapus_id: int | None) -> None:
    if induk_id is None:
        if jenis == "sub":
            raise tidak_valid("Subkategori wajib punya induk (kategori atau subkategori).")
        return
    if jenis in TANPA_INDUK:
        raise tidak_valid(f"Baris jenis '{jenis}' tidak boleh punya induk.")
    induk = ambil(conn, induk_id)
    if induk["tahun_dasar_id"] != td_id:
        raise tidak_valid("Induk harus dari tahun dasar yang sama.")
    if induk["jenis"] not in BISA_INDUK:
        raise tidak_valid(f"Induk '{induk['kode']}' berjenis {induk['jenis']}; induk harus kategori atau subkategori.")
    if not induk["aktif"]:
        raise tidak_valid(f"Induk '{induk['kode']}' nonaktif.")
    if lapus_id is not None and (induk_id == lapus_id or induk_id in keturunan(conn, lapus_id)):
        raise tidak_valid("Induk tidak boleh lapus itu sendiri atau turunannya.")


def susun_ulang(conn: Connection, td_id: int, saudara: tuple[int | None, list[int]] | None = None) -> int:
    """Hitung ulang `urutan` (DFS) dan `level` seluruh pohon tahun dasar. Kembalikan jumlah baris yang berubah."""
    rows = conn.execute(text("SELECT id, induk_id, urutan, level, jenis FROM ref.lapus WHERE tahun_dasar_id = :t"
                             " ORDER BY urutan"), {"t": td_id}).all()
    info = {r.id: r for r in rows}
    anak: dict[int | None, list[int]] = defaultdict(list)
    for r in rows:
        anak[r.induk_id].append(r.id)
    if saudara is not None:
        induk, ids = saudara
        if len(set(ids)) != len(ids) or set(ids) != set(anak.get(induk, [])):
            raise tidak_valid("Daftar urutan harus memuat semua saudara pada induk yang sama, tanpa duplikat.")
        anak[induk] = list(ids)

    urut: list[int] = []
    level: dict[int, int] = {}

    def dfs(induk: int | None, lv_induk: int) -> None:
        for i in anak.get(induk, []):
            lv = (0 if info[i].jenis in TOTAL else 1) if induk is None else lv_induk + 1
            if lv > LEVEL_MAKS:
                raise tidak_valid(f"Kedalaman pohon maksimal {LEVEL_MAKS} tingkat.")
            level[i] = lv
            urut.append(i)
            dfs(i, lv)

    dfs(None, 0)
    if len(urut) != len(rows):
        raise tidak_valid("Pohon lapus tidak konsisten (ada siklus induk).")
    ubah = [(i, k + 1, level[i]) for k, i in enumerate(urut) if info[i].urutan != k + 1 or info[i].level != level[i]]
    if not ubah:
        return 0
    ids = [u[0] for u in ubah]
    # UNIQUE (tahun_dasar_id, urutan) tidak deferrable: geser dulu ke rentang sementara, lalu ke nilai akhir.
    conn.execute(text("UPDATE ref.lapus SET urutan = urutan + 100000 WHERE id = ANY(:ids)"), {"ids": ids})
    conn.execute(text(
        "UPDATE ref.lapus l SET urutan = v.u, level = v.lv FROM"
        " (SELECT unnest(CAST(:ids AS int[])) AS id, unnest(CAST(:us AS int[])) AS u,"
        "  unnest(CAST(:lvs AS int[])) AS lv) v WHERE l.id = v.id"),
        {"ids": ids, "us": [u[1] for u in ubah], "lvs": [u[2] for u in ubah]})
    return len(ubah)


def _urutan_akhir(conn: Connection, td_id: int) -> int:
    return conn.execute(text("SELECT coalesce(max(urutan), 0) + 1 FROM ref.lapus WHERE tahun_dasar_id = :t"),
                        {"t": td_id}).scalar_one()


def _saudara(conn: Connection, td_id: int, induk_id: int | None) -> list[int]:
    return [r[0] for r in conn.execute(text(
        "SELECT id FROM ref.lapus WHERE tahun_dasar_id = :t AND induk_id IS NOT DISTINCT FROM :i ORDER BY urutan"),
        {"t": td_id, "i": induk_id})]


# ------------------------------------------------------------------ endpoint
@router.get("/tahun-dasar/{td_id}/lapus")
def daftar(td_id: int, conn: Connection = Depends(koneksi)) -> list[dict]:
    rows = conn.execute(text(
        f"SELECT {', '.join('l.' + k for k in _KOLOM.split(', '))},"
        " coalesce((SELECT array_agg(k.anggota_id ORDER BY a.urutan) FROM ref.lapus_kelompok k"
        "   JOIN ref.lapus a ON a.id = k.anggota_id WHERE k.kelompok_id = l.id), '{}') AS anggota,"
        " (SELECT count(*) FROM lk.item i WHERE i.lapus_id = l.id) AS jumlah_item"
        " FROM ref.lapus l WHERE l.tahun_dasar_id = :t ORDER BY l.urutan"), {"t": td_id}).mappings().all()
    return [dict(r) for r in rows]


@router.post("/tahun-dasar/{td_id}/lapus", status_code=201)
def tambah(td_id: int, data: LapusIn, conn: Connection = Depends(koneksi), _=KELOLA) -> dict:
    if conn.execute(text("SELECT 1 FROM ref.tahun_dasar WHERE id = :t"), {"t": td_id}).first() is None:
        raise tidak_ada("Tahun dasar")
    _cek_struktur(conn, td_id, data.jenis, data.induk_id, None)
    if data.induk_id is not None and data.jenis == "daun" and punya_item(conn, data.induk_id):
        raise tidak_valid("Induk sudah punya item data dasar.")
    lid = conn.execute(text(
        "INSERT INTO ref.lapus (tahun_dasar_id, kode, nama, induk_id, level, urutan, jenis, kode_lk_bps, is_migas)"
        " VALUES (:t, :kode, :nama, :induk, 1, :urut, :jenis, :lk, :migas) RETURNING id"),
        {"t": td_id, "kode": data.kode.strip(), "nama": rapikan(data.nama), "induk": data.induk_id,
         "urut": _urutan_akhir(conn, td_id), "jenis": data.jenis, "lk": rapikan(data.kode_lk_bps) or None,
         "migas": data.is_migas}).scalar_one()
    saudara = None
    if data.sesudah_id is not None:
        ids = [i for i in _saudara(conn, td_id, data.induk_id) if i != lid]
        if data.sesudah_id not in ids:
            raise tidak_valid("Posisi 'sesudah' harus saudara pada induk yang sama.")
        ids.insert(ids.index(data.sesudah_id) + 1, lid)
        saudara = (data.induk_id, ids)
    susun_ulang(conn, td_id, saudara)
    return ambil(conn, lid)


@router.patch("/lapus/{lapus_id}")
def ubah(lapus_id: int, data: LapusUbah, conn: Connection = Depends(koneksi), _=KELOLA) -> dict:
    lama = ambil(conn, lapus_id)
    f = data.model_fields_set
    jenis = data.jenis if "jenis" in f and data.jenis is not None else lama["jenis"]
    induk_id = data.induk_id if "induk_id" in f else lama["induk_id"]
    if jenis != lama["jenis"]:
        if jenis not in BISA_INDUK and punya_anak(conn, lapus_id):
            raise tidak_valid("Lapus ini punya sub-lapus; pindahkan atau hapus dulu sebelum mengubah jenisnya.")
        if lama["jenis"] in BERITEM and jenis not in BERITEM and punya_item(conn, lapus_id):
            raise tidak_valid("Lapus ini sudah punya item data dasar; jenisnya tidak dapat diubah.")
        if lama["jenis"] == "kelompok" and _ada(conn, "SELECT 1 FROM ref.lapus_kelompok WHERE kelompok_id = :i",
                                                 i=lapus_id):
            raise tidak_valid("Kosongkan anggota kelompok dulu sebelum mengubah jenisnya.")
    if jenis != lama["jenis"] or induk_id != lama["induk_id"]:
        _cek_struktur(conn, lama["tahun_dasar_id"], jenis, induk_id, lapus_id)
    aktif = data.aktif if "aktif" in f and data.aktif is not None else lama["aktif"]
    if not aktif and lama["aktif"] and punya_anak(conn, lapus_id, hanya_aktif=True):
        raise tidak_valid("Nonaktifkan sub-lapus lebih dulu.")
    if aktif and not lama["aktif"] and induk_id is not None and not ambil(conn, induk_id)["aktif"]:
        raise tidak_valid("Aktifkan induknya lebih dulu.")
    pindah = induk_id != lama["induk_id"]
    conn.execute(text(
        "UPDATE ref.lapus SET kode = :kode, nama = :nama, jenis = :jenis, induk_id = :induk, kode_lk_bps = :lk,"
        " is_migas = :migas, aktif = :aktif, urutan = CASE WHEN :pindah THEN :akhir ELSE urutan END WHERE id = :i"),
        {"kode": (data.kode or lama["kode"]).strip(), "nama": rapikan(data.nama) or lama["nama"], "jenis": jenis,
         "induk": induk_id, "lk": (rapikan(data.kode_lk_bps) or None) if "kode_lk_bps" in f else lama["kode_lk_bps"],
         "migas": data.is_migas if data.is_migas is not None else lama["is_migas"], "aktif": aktif,
         "pindah": pindah, "akhir": _urutan_akhir(conn, lama["tahun_dasar_id"]), "i": lapus_id})
    susun_ulang(conn, lama["tahun_dasar_id"])
    return ambil(conn, lapus_id)


@router.put("/tahun-dasar/{td_id}/lapus/urutan")
def atur_urutan(td_id: int, data: UrutanIn, conn: Connection = Depends(koneksi), _=KELOLA) -> dict:
    n = susun_ulang(conn, td_id, (data.induk_id, data.anak))
    return {"baris_berubah": n}


@router.delete("/lapus/{lapus_id}")
def hapus(lapus_id: int, conn: Connection = Depends(koneksi), _=KELOLA) -> dict:
    lama = ambil(conn, lapus_id)
    if punya_anak(conn, lapus_id):
        raise tidak_valid("Lapus ini punya sub-lapus; hapus atau pindahkan sub-lapus lebih dulu.")
    nonaktif = sql_hapus("UPDATE ref.lapus SET aktif = false WHERE id = :i", i=lapus_id)
    # Rujukan tanpa foreign key (tautan HASIL_LAPUS/MARGIN, riwayat status, antrean) juga dihitung "dipakai".
    dipakai_lain = _ada(conn, "SELECT 1 FROM lk.tautan_seri WHERE :i = ANY(lapus_sumber_ids)"
                              " UNION ALL SELECT 1 FROM lk.riwayat_status WHERE lapus_id = :i"
                              " UNION ALL SELECT 1 FROM lk.antrean_hitung WHERE lapus_id = :i", i=lapus_id)
    if dipakai_lain:
        nonaktif(conn)
        return pesan_hapus("Lapus", "dinonaktifkan")

    def _hapus(c: Connection) -> int:
        c.execute(text("DELETE FROM ref.konkordansi_lapus WHERE lapus_asal_id = :i OR lapus_tujuan_id = :i"),
                  {"i": lapus_id})
        return c.execute(text("DELETE FROM ref.lapus WHERE id = :i"), {"i": lapus_id}).rowcount

    h = hapus_atau_nonaktifkan(conn, _hapus, nonaktif, "Lapus")
    susun_ulang(conn, lama["tahun_dasar_id"])
    return pesan_hapus("Lapus", h)


@router.put("/lapus/{kelompok_id}/anggota")
def atur_anggota(kelompok_id: int, data: AnggotaIn, conn: Connection = Depends(koneksi), _=KELOLA) -> dict:
    k = ambil(conn, kelompok_id)
    if k["jenis"] != "kelompok":
        raise tidak_valid("Anggota hanya dapat diatur pada baris berjenis kelompok.")
    ids = list(dict.fromkeys(data.anggota_ids))
    anggota = [ambil(conn, i) for i in ids]
    for a in anggota:
        if a["tahun_dasar_id"] != k["tahun_dasar_id"]:
            raise tidak_valid(f"Anggota '{a['kode']}' berasal dari tahun dasar lain.")
        if a["jenis"] == "kelompok" or a["jenis"] in TOTAL:
            raise tidak_valid(f"'{a['kode']}' ({a['jenis']}) tidak dapat menjadi anggota kelompok.")
    for a in anggota:  # cegah hitung ganda: induk dan turunannya tidak boleh sama-sama anggota
        if keturunan(conn, a["id"]) & set(ids):
            raise tidak_valid(f"'{a['kode']}' dan sub-lapusnya tidak boleh sama-sama menjadi anggota (hitung ganda).")
    conn.execute(text("DELETE FROM ref.lapus_kelompok WHERE kelompok_id = :k AND NOT (anggota_id = ANY(:ids))"),
                 {"k": kelompok_id, "ids": ids})
    conn.execute(text("INSERT INTO ref.lapus_kelompok (kelompok_id, anggota_id) SELECT :k, unnest(CAST(:ids AS int[]))"
                      " ON CONFLICT DO NOTHING"), {"k": kelompok_id, "ids": ids})
    return {"kelompok_id": kelompok_id, "anggota": [a["kode"] for a in anggota]}
