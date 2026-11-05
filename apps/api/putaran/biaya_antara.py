"""LK Biaya Antara tahun dasar (lk.struktur_biaya; hasil SE2026/SUT): output dan rincian BA per lapus atau item, rasio
KA otomatis (kolom terhitung), persetujuan, lalu Terapkan ke RKA_TD item (lk.parameter_item) untuk satu putaran.

Urutan cari rasio per item (hanya baris berstatus disetujui): baris item -> baris lapus item -> induk (subkategori,
kategori). Item REV/EKS/DEF pada lapus daun; TOP/SOP tidak punya konsumsi antara (keputusan 1). Terapkan mengubah
jangkar, sehingga lapus terdampak kembali ke draf (keputusan 19) dan dihitung ulang.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import Connection, text

from ..app.deps import Pengguna, butuh_izin, koneksi
from ..master.umum import rapikan, tidak_ada, tidak_valid
from ..worker.antrean import antrekan
from .status import tandai_ubah
from .umum import ambil_putaran, boleh_tulis, cek_tulis, pastikan_terbuka

router = APIRouter(prefix="/api", tags=["biaya-antara"])
ISI = Depends(butuh_izin("biaya_antara.isi"))
BACA = Depends(butuh_izin("biaya_antara.isi", "lk.setujui"))
BA = ("ba_bahan", "ba_energi", "ba_jasa", "ba_sewa", "ba_lainnya")
JENIS_POHON = ("kategori", "sub", "daun")


def _pohon(conn: Connection, td: int) -> dict[int, dict]:
    return {r["id"]: dict(r) for r in conn.execute(text(
        "SELECT id, kode, nama, jenis, level, induk_id, urutan FROM ref.lapus WHERE tahun_dasar_id = :td AND aktif"
        " ORDER BY urutan"), {"td": td}).mappings()}


def _subpohon(pohon: dict[int, dict], akar: int) -> list[int]:
    if akar not in pohon:
        raise tidak_ada("Lapus")
    if pohon[akar]["jenis"] not in JENIS_POHON:
        raise tidak_valid("Biaya antara diisi untuk kategori, subkategori, atau lapus daun (TOP/SOP tanpa KA).")
    anak: dict[int, list[int]] = defaultdict(list)
    for r in pohon.values():
        if r["induk_id"]:
            anak[r["induk_id"]].append(r["id"])
    out: list[int] = []

    def turun(i: int) -> None:
        out.append(i)
        for a in anak.get(i, []):
            turun(a)

    turun(akar)
    return [i for i in out if pohon[i]["jenis"] in JENIS_POHON]


def _item(conn: Connection, td: int, wilayah: str, lapus: list[int]) -> list[dict]:
    return [dict(r) for r in conn.execute(text(
        "SELECT i.id, i.lapus_id, l.kode AS kode_lapus, i.metode_kode AS metode, i.nomor, i.nama, i.status"
        " FROM lk.item i JOIN ref.lapus l ON l.id = i.lapus_id WHERE i.tahun_dasar_id = :td AND i.wilayah_kode = :w"
        " AND i.lapus_id = ANY(:l) AND i.metode_kode IN ('REV','EKS','DEF') AND l.jenis = 'daun'"
        " ORDER BY l.urutan, array_position(ARRAY['REV','EKS','DEF'], i.metode_kode), i.nomor"),
        {"td": td, "w": wilayah, "l": lapus}).mappings()]


@router.get("/struktur-biaya")
def daftar(tahun_dasar_id: int, wilayah: str, lapus_id: int, conn: Connection = Depends(koneksi),
           _: Pengguna = BACA) -> dict:
    pohon = _pohon(conn, tahun_dasar_id)
    ids = _subpohon(pohon, lapus_id)
    baris = [dict(r) for r in conn.execute(text(
        "SELECT s.id, s.lapus_id, s.item_id, s.output::float8 AS output, s.ba_bahan::float8 AS ba_bahan,"
        " s.ba_energi::float8 AS ba_energi, s.ba_jasa::float8 AS ba_jasa, s.ba_sewa::float8 AS ba_sewa,"
        " s.ba_lainnya::float8 AS ba_lainnya, s.ba_total_langsung::float8 AS ba_total_langsung,"
        " s.total_ba::float8 AS total_ba, s.rasio_ka::float8 AS rasio_ka, s.sumber, s.status, s.diubah_pada,"
        " u.nama AS diubah_oleh FROM lk.struktur_biaya s LEFT JOIN sec.pengguna u ON u.id = s.diubah_oleh"
        " WHERE s.tahun_dasar_id = :td AND s.wilayah_kode = :w AND s.lapus_id = ANY(:l)"),
        {"td": tahun_dasar_id, "w": wilayah, "l": ids}).mappings()]
    return {"lapus": [pohon[i] | {"boleh_tulis": boleh_tulis(conn, wilayah, i)} for i in ids],
            "item": _item(conn, tahun_dasar_id, wilayah, ids), "baris": baris}


class BiayaIn(BaseModel):
    tahun_dasar_id: int
    wilayah: str = Field(min_length=4, max_length=4)
    lapus_id: int
    item_id: int | None = None
    output: float | None = Field(default=None, ge=0)
    ba_bahan: float | None = Field(default=None, ge=0)
    ba_energi: float | None = Field(default=None, ge=0)
    ba_jasa: float | None = Field(default=None, ge=0)
    ba_sewa: float | None = Field(default=None, ge=0)
    ba_lainnya: float | None = Field(default=None, ge=0)
    ba_total_langsung: float | None = Field(default=None, ge=0)
    sumber: str = Field(default="SE2026", min_length=2, max_length=100)


@router.put("/struktur-biaya")
def simpan(data: BiayaIn, conn: Connection = Depends(koneksi), _: Pengguna = ISI) -> dict:
    """Simpan satu baris (lapus atau item). Mengubah angka mengembalikan status baris ke draf."""
    pohon = _pohon(conn, data.tahun_dasar_id)
    lap = pohon.get(data.lapus_id)
    if lap is None or lap["jenis"] not in JENIS_POHON:
        raise tidak_valid("Biaya antara diisi untuk kategori, subkategori, atau lapus daun (TOP/SOP tanpa KA).")
    if data.item_id is not None:
        it = conn.execute(text("SELECT lapus_id, trim(wilayah_kode) FROM lk.item WHERE id = :i AND tahun_dasar_id"
                               " = :td"), {"i": data.item_id, "td": data.tahun_dasar_id}).first()
        if it is None or it[0] != data.lapus_id or it[1] != data.wilayah:
            raise tidak_valid("Item tidak berada pada lapus dan wilayah ini.")
    cek_tulis(conn, data.wilayah, data.lapus_id)
    q: dict[str, Any] = data.model_dump() | {"sumber": rapikan(data.sumber)}
    r = conn.execute(text(
        "INSERT INTO lk.struktur_biaya (tahun_dasar_id, wilayah_kode, lapus_id, item_id, output, ba_bahan, ba_energi,"
        " ba_jasa, ba_sewa, ba_lainnya, ba_total_langsung, sumber, status, diubah_oleh, diubah_pada)"
        " VALUES (:tahun_dasar_id, :wilayah, :lapus_id, :item_id, :output, :ba_bahan, :ba_energi, :ba_jasa, :ba_sewa,"
        " :ba_lainnya, :ba_total_langsung, :sumber, 'draf', sec.uid(), now())"
        " ON CONFLICT (tahun_dasar_id, wilayah_kode, lapus_id, item_id) DO UPDATE SET output = EXCLUDED.output,"
        " ba_bahan = EXCLUDED.ba_bahan, ba_energi = EXCLUDED.ba_energi, ba_jasa = EXCLUDED.ba_jasa,"
        " ba_sewa = EXCLUDED.ba_sewa, ba_lainnya = EXCLUDED.ba_lainnya, ba_total_langsung = EXCLUDED.ba_total_langsung,"
        " sumber = EXCLUDED.sumber, status = 'draf', diubah_oleh = EXCLUDED.diubah_oleh, diubah_pada = now()"
        " RETURNING id, rasio_ka::float8"), q).one()
    peringatan = "Rasio KA lebih dari 1 (BA melebihi output); periksa kembali." if (r[1] or 0) > 1 else None
    return {"id": r[0], "rasio_ka": r[1], "peringatan": peringatan,
            "pesan": "Tersimpan sebagai draf; rasio dipakai setelah disetujui."}


@router.delete("/struktur-biaya/{sid}")
def hapus(sid: int, conn: Connection = Depends(koneksi), _: Pengguna = ISI) -> dict:
    r = conn.execute(text("SELECT trim(wilayah_kode), lapus_id FROM lk.struktur_biaya WHERE id = :i"),
                     {"i": sid}).first()
    if r is None:
        raise tidak_ada("Baris biaya antara")
    cek_tulis(conn, r[0], r[1])
    conn.execute(text("DELETE FROM lk.struktur_biaya WHERE id = :i"), {"i": sid})
    return {"pesan": "Baris biaya antara dihapus."}


class SetujuiIn(BaseModel):
    id: list[int] = Field(min_length=1, max_length=2000)
    setujui: bool = True


@router.post("/struktur-biaya/setujui")
def setujui(data: SetujuiIn, conn: Connection = Depends(koneksi),
            _: Pengguna = Depends(butuh_izin("lk.setujui"))) -> dict:
    n = conn.execute(text("UPDATE lk.struktur_biaya SET status = :s, diubah_oleh = sec.uid(), diubah_pada = now()"
                          " WHERE id = ANY(:i) AND rasio_ka IS NOT NULL"),
                     {"s": "disetujui" if data.setujui else "draf", "i": data.id}).rowcount
    return {"jumlah": n, "pesan": f"{n} baris {'disetujui' if data.setujui else 'dikembalikan ke draf'}"
            + ("" if n == len(set(data.id)) else " (baris tanpa output/BA dilewati)") + "."}


class TerapkanIn(BaseModel):
    putaran_id: int
    wilayah: str = Field(min_length=4, max_length=4)
    lapus_id: int
    hanya_kosong: bool = False
    terapkan: bool = False  # False = pratinjau


def rencana_rka(item: list[dict], pohon: dict[int, dict], per_item: dict[int, float], per_lapus: dict[int, float]
                ) -> list[tuple[dict, float | None, str | None]]:
    """(item, rasio, sumber) menurut urutan cari item -> lapus -> induk. Fungsi murni (diuji unit)."""
    out: list[tuple[dict, float | None, str | None]] = []
    for it in item:
        if it["id"] in per_item:
            out.append((it, per_item[it["id"]], "item"))
            continue
        lid: int | None = it["lapus_id"]
        hasil: tuple[float | None, str | None] = (None, None)
        langkah = 0
        while lid is not None:
            if lid in per_lapus:
                hasil = (per_lapus[lid], ("lapus " if langkah == 0 else "induk ") + pohon[lid]["kode"])
                break
            lid = pohon[lid]["induk_id"] if lid in pohon else None
            langkah += 1
        out.append((it, *hasil))
    return out


@router.post("/struktur-biaya/terapkan")
def terapkan(data: TerapkanIn, conn: Connection = Depends(koneksi), _: Pengguna = ISI) -> dict:
    """Pratinjau (terapkan=false) atau terapkan rasio KA disetujui ke RKA_TD item pada putaran ini."""
    p = ambil_putaran(conn, data.putaran_id)
    pastikan_terbuka(p)
    td = p["tahun_dasar_id"]
    pohon = _pohon(conn, td)
    ids = _subpohon(pohon, data.lapus_id)
    item = _item(conn, td, data.wilayah, ids)
    per_item: dict[int, float] = {}
    per_lapus: dict[int, float] = {}
    for lid, iid, r in conn.execute(text(
            "SELECT lapus_id, item_id, rasio_ka::float8 FROM lk.struktur_biaya WHERE tahun_dasar_id = :td"
            " AND wilayah_kode = :w AND status = 'disetujui' AND rasio_ka IS NOT NULL"),
            {"td": td, "w": data.wilayah}):
        if iid is None:
            per_lapus[lid] = r
        else:
            per_item[iid] = r
    lama = {i: v for i, v in conn.execute(text(
        "SELECT item_id, nilai::float8 FROM lk.parameter_item WHERE putaran_id = :p AND kode = 'RKA_TD'"
        " AND item_id = ANY(:i)"), {"p": data.putaran_id, "i": [i["id"] for i in item]})}
    tulis = {lid: boleh_tulis(conn, data.wilayah, lid) for lid in {i["lapus_id"] for i in item}}
    baris = []
    for it, baru, sumber in rencana_rka(item, pohon, per_item, per_lapus):
        lm = lama.get(it["id"])
        if baru is None:
            aksi = "tanpa_sumber"
        elif lm is not None and abs(lm - baru) <= 1e-12:
            aksi = "sama"
        elif data.hanya_kosong and lm is not None:
            aksi = "sudah_terisi"
        elif not tulis[it["lapus_id"]]:
            aksi = "tidak_ditugaskan"
        else:
            aksi = "ubah"
        baris.append(it | {"lama": lm, "baru": baru, "sumber": sumber, "aksi": aksi})
    ringkas: dict[str, int] = defaultdict(int)
    for b in baris:
        ringkas[b["aksi"]] += 1
    n = 0
    if data.terapkan:
        ubah = [b for b in baris if b["aksi"] == "ubah"]
        for b in ubah:
            conn.execute(text(
                "INSERT INTO lk.parameter_item (putaran_id, item_id, kode, nilai, alasan, diubah_oleh)"
                " VALUES (:p, :i, 'RKA_TD', :v, :a, sec.uid()) ON CONFLICT (putaran_id, item_id, kode) DO UPDATE"
                " SET nilai = EXCLUDED.nilai, alasan = EXCLUDED.alasan, diubah_oleh = EXCLUDED.diubah_oleh,"
                " diubah_pada = now()"),
                {"p": data.putaran_id, "i": b["id"], "v": b["baru"], "a": f"Terapkan Biaya Antara ({b['sumber']})"})
        n = len(ubah)
        if ubah:
            tandai_ubah(conn, data.putaran_id, [(data.wilayah, b["lapus_id"]) for b in ubah], "terapkan Biaya Antara")
            antrekan(conn, data.putaran_id, data.wilayah, None, "terapkan Biaya Antara")
    return {"baris": baris, "ringkasan": dict(ringkas), "diterapkan": n,
            "pesan": (f"RKA tahun dasar diterapkan ke {n} item." if data.terapkan
                      else f"Pratinjau: {ringkas.get('ubah', 0)} item akan diubah.")}
