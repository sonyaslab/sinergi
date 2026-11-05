"""Endpoint impor/ekspor data dasar (F3): pratinjau selisih -> terapkan; ekspor templat, CSV panjang, seri referensi.

Berkas dikirim sebagai badan permintaan mentah (xlsx atau csv) dengan parameter `nama`; berkas mentah tidak disimpan
(audit.impor_berkas hanya menyimpan sha256, ringkasan, dan pesan tanpa angka). Terapkan mengirim ulang berkas yang
sama; sistem menolak bila sha256 berbeda atau data berubah sejak pratinjau.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import date

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import Response
from sqlalchemy import Connection, text

from ..app import audit
from ..app.deps import Pengguna, butuh_izin, ip_klien, koneksi
from ..app.galat import GalatSinergi
from . import csv_panjang, ekspor
from .konteks import muat_konteks
from .templat import Berkas, baca
from .terapkan import Opsi, pesan_audit, pratinjau_json, rencanakan, terapkan

router = APIRouter(prefix="/api", tags=["impor"])
MAKS_BAYT = 25 * 1024 * 1024  # sama dengan client_max_body_size Nginx
MAKS_JAM_PRATINJAU = 6
IMPOR = Depends(butuh_izin("data_dasar.impor"))
BACA_DATA = Depends(butuh_izin("data_dasar.isi", "data_dasar.impor", "lk.setujui"))
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


async def isi_berkas(request: Request) -> bytes:
    data = await request.body()
    if not data:
        raise GalatSinergi(422, "BERKAS_KOSONG", "Berkas kosong. Pilih berkas templat (.xlsx) atau CSV.")
    if len(data) > MAKS_BAYT:
        raise GalatSinergi(413, "BERKAS_BESAR", "Berkas terlalu besar (maksimal 25 MB).")
    return data


def _nama(nama: str) -> str:
    nama = re.sub(r"[^\w .()\-]", "_", nama.split("/")[-1].split("\\")[-1]).strip()[:120]
    return nama or "berkas"


def _putaran(conn: Connection, putaran_id: int) -> tuple[int, str, str]:
    r = conn.execute(text("SELECT p.tahun_dasar_id, t.kode, p.status FROM lk.putaran p JOIN ref.tahun_dasar t"
                          " ON t.id = p.tahun_dasar_id WHERE p.id = :p"), {"p": putaran_id}).first()
    if r is None:
        raise GalatSinergi(404, "TIDAK_ADA", "Putaran tidak ditemukan.")
    return int(r[0]), str(r[1]), str(r[2])


def _baca(conn: Connection, data: bytes, nama: str, td: int, td_kode: str) -> tuple[Berkas, str]:
    k = muat_konteks(conn, td)
    if data[:2] == b"PK":
        b = baca(data, k)
        jenis = "templat_xlsx" if b.sheet_kategori else "seri_referensi"
        return b, jenis
    jenis_csv = csv_panjang.jenis_csv(data)
    if jenis_csv is None:
        raise GalatSinergi(422, "FORMAT_BERKAS", "Format berkas tidak dikenal. Gunakan templat .xlsx atau CSV panjang.")
    return csv_panjang.baca(data, k, td_kode), jenis_csv


@router.post("/impor/templat")
def pratinjau_impor(request: Request, putaran_id: int, nama: str = "berkas.xlsx", kosongkan: bool = False,
                    setujui_penyesuaian: bool = False, data: bytes = Depends(isi_berkas),
                    conn: Connection = Depends(koneksi), pengguna: Pengguna = IMPOR) -> dict:
    """Langkah 1: baca berkas dan bandingkan dengan isi putaran (tidak mengubah data)."""
    nama = _nama(nama)
    td, td_kode, status = _putaran(conn, putaran_id)
    if status == "terkunci":
        raise GalatSinergi(423, "PUTARAN_TERKUNCI", "Putaran sudah dikunci. Impor ditolak seluruhnya.")
    berkas, jenis = _baca(conn, data, nama, td, td_kode)
    opsi = Opsi(kosongkan, setujui_penyesuaian)
    r = rencanakan(conn, berkas, putaran_id, nama, pengguna.izin, opsi)
    sha = hashlib.sha256(data).hexdigest()
    isi = pesan_audit(r) | {"opsi": {"kosongkan": kosongkan, "setujui_penyesuaian": setujui_penyesuaian}}
    iid = conn.execute(text(
        "INSERT INTO audit.impor_berkas (nama_berkas, sha256, jenis, pengguna_id, putaran_id, jumlah_baris, status,"
        " pesan) VALUES (:n, :s, :j, :u, :p, :jml, :st, CAST(:m AS jsonb)) RETURNING id"),
        {"n": nama, "s": sha, "j": jenis, "u": pengguna.id, "p": putaran_id, "jml": berkas.jumlah_angka(),
         "st": "ditolak" if r.galat else "pratinjau", "m": json.dumps(isi, ensure_ascii=False)}).scalar_one()
    return {"impor_id": iid, "jenis": jenis, "nama_berkas": nama, "dapat_diterapkan": not r.galat,
            "opsi": isi["opsi"], **pratinjau_json(r)}


@router.post("/impor/{impor_id}/terapkan")
def terapkan_impor(impor_id: int, request: Request, data: bytes = Depends(isi_berkas),
                   conn: Connection = Depends(koneksi), pengguna: Pengguna = IMPOR) -> dict:
    """Langkah 2: kirim ulang berkas yang sama; perubahan ditulis dalam satu transaksi lalu dihitung ulang."""
    pr = conn.execute(text(
        "SELECT nama_berkas, sha256, jenis, pengguna_id, putaran_id, status, pesan, waktu > now() - make_interval("
        "hours => :j) AS segar FROM audit.impor_berkas WHERE id = :i"),
        {"i": impor_id, "j": MAKS_JAM_PRATINJAU}).first()
    if pr is None or pr.pengguna_id != pengguna.id:
        raise GalatSinergi(404, "TIDAK_ADA", "Pratinjau impor tidak ditemukan.")
    if pr.status != "pratinjau":
        raise GalatSinergi(409, "IMPOR_TIDAK_SIAP", "Pratinjau ini tidak dapat diterapkan (ada galat atau sudah"
                                                    " diterapkan). Ulangi unggah.")
    sudah = conn.execute(text("SELECT 1 FROM audit.impor_berkas WHERE status = 'diterapkan'"
                              " AND (pesan->>'pratinjau_id')::bigint = :i"), {"i": impor_id}).first()
    if sudah is not None:
        raise GalatSinergi(409, "SUDAH_DITERAPKAN", "Pratinjau ini sudah diterapkan.")
    if not pr.segar:
        raise GalatSinergi(409, "PRATINJAU_KEDALUWARSA", "Pratinjau sudah kedaluwarsa. Unggah ulang berkas.")
    if hashlib.sha256(data).hexdigest() != pr.sha256:
        raise GalatSinergi(409, "BERKAS_BERBEDA", "Berkas berbeda dengan yang dipratinjau. Unggah ulang berkas.")
    td, td_kode, status = _putaran(conn, pr.putaran_id)
    if status == "terkunci":
        raise GalatSinergi(423, "PUTARAN_TERKUNCI", "Putaran sudah dikunci. Impor ditolak seluruhnya.")
    berkas, _ = _baca(conn, data, pr.nama_berkas, td, td_kode)
    o = (pr.pesan or {}).get("opsi", {})
    r = rencanakan(conn, berkas, pr.putaran_id, pr.nama_berkas, pengguna.izin,
                   Opsi(bool(o.get("kosongkan")), bool(o.get("setujui_penyesuaian"))))
    if r.sidik() != (pr.pesan or {}).get("sidik_rencana"):
        raise GalatSinergi(409, "DATA_BERUBAH", "Data di sistem berubah sejak pratinjau. Ulangi pratinjau.")
    conn.execute(text("SELECT set_config('app.alasan', :a, true)"), {"a": f"impor templat {pr.nama_berkas}"[:200]})
    ringkasan = terapkan(conn, r, pengguna.id)
    conn.execute(text(
        "INSERT INTO audit.impor_berkas (nama_berkas, sha256, jenis, pengguna_id, putaran_id, jumlah_baris, status,"
        " pesan) VALUES (:n, :s, :j, :u, :p, :jml, 'diterapkan', CAST(:m AS jsonb))"),
        {"n": pr.nama_berkas, "s": pr.sha256, "j": pr.jenis, "u": pengguna.id, "p": pr.putaran_id,
         "jml": berkas.jumlah_angka(), "m": json.dumps({"pratinjau_id": impor_id, "ringkasan": ringkasan})})
    return {"impor_id": impor_id, "ringkasan": ringkasan, "wilayah_dihitung": sorted(r.wilayah),
            "pesan": "Impor diterapkan. Hitung ulang otomatis sudah dijadwalkan."}


# ======================================================================== ekspor
def _td_putaran(conn: Connection, putaran_id: int | None, tahun_dasar_id: int | None) -> int:
    if putaran_id is not None:
        return _putaran(conn, putaran_id)[0]
    if tahun_dasar_id is None:
        raise GalatSinergi(422, "TIDAK_VALID", "Pilih putaran atau tahun dasar.")
    return tahun_dasar_id


def _wilayah(wilayah: str | None) -> list[str] | None:
    return [w.strip() for w in wilayah.split(",") if w.strip()] if wilayah else None


@router.get("/ekspor/templat")
def ekspor_templat(request: Request, putaran_id: int | None = None, tahun_dasar_id: int | None = None,
                   wilayah: str | None = Query(default=None, description="kode dipisah koma"), kosong: bool = False,
                   conn: Connection = Depends(koneksi), pengguna: Pengguna = BACA_DATA) -> Response:
    td = _td_putaran(conn, putaran_id, tahun_dasar_id)
    kosong = kosong or putaran_id is None
    ta = audit.catat_ekspor(conn, pengguna.id, pengguna.username, "templat_xlsx",
                            {"putaran_id": putaran_id, "tahun_dasar_id": td, "wilayah": wilayah, "kosong": kosong},
                            ip_klien(request))
    d = ekspor.muat_data(conn, td, putaran_id, _wilayah(wilayah), kosong, ta)
    isi = ekspor.tulis_xlsx(d)
    nama = f"Templat_Data_Dasar_{d.td_kode}_{'KOSONG' if kosong else 'ISI'}_{date.today():%Y%m%d}.xlsx"
    return Response(isi, media_type=XLSX, headers={"Content-Disposition": f'attachment; filename="{nama}"'})


@router.get("/ekspor/csv")
def ekspor_csv(request: Request, putaran_id: int, wilayah: str | None = None, conn: Connection = Depends(koneksi),
               pengguna: Pengguna = BACA_DATA) -> Response:
    td = _putaran(conn, putaran_id)[0]
    ta = audit.catat_ekspor(conn, pengguna.id, pengguna.username, "csv_panjang",
                            {"putaran_id": putaran_id, "wilayah": wilayah}, ip_klien(request))
    d = ekspor.muat_data(conn, td, putaran_id, _wilayah(wilayah), False, ta)
    nama = f"Data_Dasar_{d.td_kode}_{date.today():%Y%m%d}.csv"
    return Response(csv_panjang.tulis_data(ekspor.baris_csv(d)), media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="{nama}"'})


@router.get("/ekspor/seri-referensi")
def ekspor_seri_ref(request: Request, putaran_id: int, wilayah: str | None = None,
                    conn: Connection = Depends(koneksi), pengguna: Pengguna = BACA_DATA) -> Response:
    _putaran(conn, putaran_id)
    audit.catat_ekspor(conn, pengguna.id, pengguna.username, "seri_referensi",
                       {"putaran_id": putaran_id, "wilayah": wilayah}, ip_klien(request))
    q = {"p": putaran_id, "w": _wilayah(wilayah)}
    baris = [{"kode_wilayah": r[0].strip(), "kode_referensi": r[1], "nama": r[2], "satuan": r[3] or "",
              "periode": f"{r[4]}-T{r[5]}", "nilai": format(r[6], ".17g")} for r in conn.execute(text(
        "SELECT n.wilayah_kode, s.kode, s.nama, s.satuan, p.tahun, p.triwulan, n.nilai::float8"
        " FROM lk.nilai_seri_referensi n JOIN lk.seri_referensi s ON s.id = n.seri_id JOIN ref.periode p"
        " ON p.id = n.periode_id WHERE n.putaran_id = :p AND (CAST(:w AS text[]) IS NULL OR n.wilayah_kode = ANY(:w))"
        " ORDER BY s.kode, n.wilayah_kode, p.urut"), q)]
    return Response(csv_panjang.tulis_ref(baris), media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="Seri_Referensi_{date.today():%Y%m%d}.csv"'})
