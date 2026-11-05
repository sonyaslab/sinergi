"""Pengguna, peran-izin, penugasan (tahun dasar x wilayah x lapus), dan jejak audit.

Pengguna tidak pernah dihapus (riwayat audit merujuknya): hapus = nonaktifkan + cabut semua sesi.
Penjaga: minimal satu pengguna aktif tetap memegang izin pengguna.kelola setelah setiap perubahan.
"""
from __future__ import annotations

import secrets
from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import Connection, text

from ..app.deps import Pengguna, butuh_izin, koneksi
from ..auth import sandi
from .lapus import BERITEM
from .umum import pesan_hapus, rapikan, tidak_ada, tidak_valid

router = APIRouter(prefix="/api", tags=["pengguna"])
KELOLA = butuh_izin("pengguna.kelola")
AKUN_SISTEM = "!disabled"  # password_hash akun sistem (mis. sistem.worker): tidak dapat login/diubah dari UI


# ================================================================= bantu
def cek_pengelola_tersisa(conn: Connection) -> None:
    n = conn.execute(text(
        "SELECT count(DISTINCT u.id) FROM sec.pengguna u JOIN sec.pengguna_peran pp ON pp.pengguna_id = u.id"
        " JOIN sec.peran p ON p.id = pp.peran_id AND p.aktif JOIN sec.peran_izin pi ON pi.peran_id = p.id"
        " WHERE u.aktif AND pi.izin_kode = 'pengguna.kelola'")).scalar_one()
    if n == 0:
        raise tidak_valid("Minimal satu pengguna aktif harus tetap memegang izin pengguna.kelola.")


def _cabut_sesi(conn: Connection, uid: int) -> None:
    conn.execute(text("UPDATE sec.sesi SET dicabut = true WHERE pengguna_id = :u AND NOT dicabut"), {"u": uid})


def _ambil_pengguna(conn: Connection, uid: int) -> dict:
    r = conn.execute(text("SELECT id, username, password_hash FROM sec.pengguna WHERE id = :i"),
                     {"i": uid}).mappings().first()
    if r is None:
        raise tidak_ada("Pengguna")
    if r["password_hash"] == AKUN_SISTEM:
        raise tidak_valid("Akun sistem tidak dapat diubah.")
    return dict(r)


def _setel_peran(conn: Connection, uid: int, peran: list[str]) -> None:
    ada = {r[0]: r[1] for r in conn.execute(text("SELECT kode, id FROM sec.peran WHERE kode = ANY(:k)"),
                                            {"k": peran})}
    kurang = sorted(set(peran) - set(ada))
    if kurang:
        raise tidak_valid(f"Peran tidak dikenal: {', '.join(kurang)}.")
    ids = list(ada.values())
    # Tambah dulu baru hapus: bila pengelola mencabut haknya sendiri, RLS tetap mengizinkan sampai akhir transaksi
    # dan penjaga cek_pengelola_tersisa yang memutuskan (pesan jelas, bukan 403).
    conn.execute(text("INSERT INTO sec.pengguna_peran (pengguna_id, peran_id) SELECT :u, unnest(CAST(:p AS smallint[]))"
                      " ON CONFLICT DO NOTHING"), {"u": uid, "p": ids})
    conn.execute(text("DELETE FROM sec.pengguna_peran WHERE pengguna_id = :u AND NOT (peran_id = ANY(:p))"),
                 {"u": uid, "p": ids})


def _sandi_sementara() -> str:
    return secrets.token_urlsafe(12)


# ================================================================= pengguna
class PenggunaIn(BaseModel):
    username: str = Field(pattern=r"^[a-z0-9._-]{3,40}$",
                          description="huruf kecil, angka, titik, garis bawah, atau strip; 3-40 karakter")
    nama: str = Field(min_length=1, max_length=120)
    email: str | None = Field(default=None, max_length=200)
    nip: str | None = Field(default=None, max_length=30)
    peran: list[str] = Field(min_length=1)


class PenggunaUbah(BaseModel):
    nama: str | None = Field(default=None, min_length=1, max_length=120)
    email: str | None = Field(default=None, max_length=200)
    nip: str | None = Field(default=None, max_length=30)
    aktif: bool | None = None
    peran: list[str] | None = None


@router.get("/pengguna")
def daftar_pengguna(conn: Connection = Depends(koneksi), _: Pengguna = Depends(KELOLA)) -> list[dict]:
    rows = conn.execute(text(
        "SELECT u.id, u.username, u.nama, u.email, u.nip, u.aktif, u.totp_aktif, u.wajib_ganti_sandi,"
        " u.terakhir_login, (u.terkunci_sampai > now()) IS TRUE AS terkunci, u.password_hash = :sis AS akun_sistem,"
        " coalesce(array_agg(p.kode ORDER BY p.kode) FILTER (WHERE p.kode IS NOT NULL), '{}') AS peran"
        " FROM sec.pengguna u LEFT JOIN sec.pengguna_peran pp ON pp.pengguna_id = u.id"
        " LEFT JOIN sec.peran p ON p.id = pp.peran_id GROUP BY u.id ORDER BY u.aktif DESC, u.username"),
        {"sis": AKUN_SISTEM}).mappings().all()
    return [dict(r) for r in rows]


@router.post("/pengguna", status_code=201)
def tambah_pengguna(data: PenggunaIn, conn: Connection = Depends(koneksi), _: Pengguna = Depends(KELOLA)) -> dict:
    sementara = _sandi_sementara()
    uid = conn.execute(text(
        "INSERT INTO sec.pengguna (username, nama, email, nip, password_hash, wajib_ganti_sandi)"
        " VALUES (:u, :n, :e, :nip, :h, true) RETURNING id"),
        {"u": data.username, "n": rapikan(data.nama), "e": rapikan(data.email) or None,
         "nip": rapikan(data.nip) or None, "h": sandi.hash_sandi(sementara)}).scalar_one()
    _setel_peran(conn, uid, data.peran)
    # Sandi sementara hanya dikembalikan sekali; wajib diganti saat login pertama (dan TOTP didaftarkan).
    return {"id": uid, "username": data.username, "sandi_sementara": sementara}


@router.patch("/pengguna/{uid}")
def ubah_pengguna(uid: int, data: PenggunaUbah, conn: Connection = Depends(koneksi),
                  saya: Pengguna = Depends(KELOLA)) -> dict:
    _ambil_pengguna(conn, uid)
    f = data.model_fields_set
    if data.aktif is False and uid == saya.id:
        raise tidak_valid("Anda tidak dapat menonaktifkan akun sendiri.")
    conn.execute(text(
        "UPDATE sec.pengguna SET nama = coalesce(:n, nama), aktif = coalesce(:a, aktif), diubah_pada = now(),"
        " email = CASE WHEN :ue THEN :e ELSE email END, nip = CASE WHEN :un THEN :nip ELSE nip END WHERE id = :i"),
        {"n": rapikan(data.nama) or None, "a": data.aktif, "ue": "email" in f, "e": rapikan(data.email) or None,
         "un": "nip" in f, "nip": rapikan(data.nip) or None, "i": uid})
    if data.peran is not None:
        _setel_peran(conn, uid, data.peran)
    if data.aktif is False:
        _cabut_sesi(conn, uid)
    cek_pengelola_tersisa(conn)
    return {"id": uid}


@router.post("/pengguna/{uid}/reset-sandi")
def reset_sandi(uid: int, conn: Connection = Depends(koneksi), _: Pengguna = Depends(KELOLA)) -> dict:
    _ambil_pengguna(conn, uid)
    sementara = _sandi_sementara()
    conn.execute(text("UPDATE sec.pengguna SET password_hash = :h, wajib_ganti_sandi = true, gagal_login = 0,"
                      " terkunci_sampai = NULL, diubah_pada = now() WHERE id = :i"),
                 {"h": sandi.hash_sandi(sementara), "i": uid})
    _cabut_sesi(conn, uid)
    return {"id": uid, "sandi_sementara": sementara}


@router.post("/pengguna/{uid}/reset-totp")
def reset_totp(uid: int, conn: Connection = Depends(koneksi), _: Pengguna = Depends(KELOLA)) -> dict:
    """Mis. ponsel hilang: pengguna mendaftarkan TOTP ulang saat login berikutnya."""
    _ambil_pengguna(conn, uid)
    conn.execute(text("UPDATE sec.pengguna SET totp_aktif = false, totp_secret_enc = NULL,"
                      " totp_langkah_terakhir = NULL, diubah_pada = now() WHERE id = :i"), {"i": uid})
    _cabut_sesi(conn, uid)
    return {"id": uid}


@router.post("/pengguna/{uid}/buka-kunci")
def buka_kunci(uid: int, conn: Connection = Depends(koneksi), _: Pengguna = Depends(KELOLA)) -> dict:
    _ambil_pengguna(conn, uid)
    conn.execute(text("UPDATE sec.pengguna SET gagal_login = 0, terkunci_sampai = NULL WHERE id = :i"), {"i": uid})
    return {"id": uid}


@router.delete("/pengguna/{uid}")
def nonaktifkan_pengguna(uid: int, conn: Connection = Depends(koneksi), saya: Pengguna = Depends(KELOLA)) -> dict:
    _ambil_pengguna(conn, uid)
    if uid == saya.id:
        raise tidak_valid("Anda tidak dapat menonaktifkan akun sendiri.")
    conn.execute(text("UPDATE sec.pengguna SET aktif = false, diubah_pada = now() WHERE id = :i"), {"i": uid})
    _cabut_sesi(conn, uid)
    cek_pengelola_tersisa(conn)
    return {"hasil": "dinonaktifkan", "pesan": "Pengguna dinonaktifkan (riwayat tetap utuh)."}


# ================================================================= peran & izin
class PeranIn(BaseModel):
    kode: str = Field(pattern=r"^[a-z][a-z_]{2,29}$")
    nama: str = Field(min_length=1, max_length=100)
    izin: list[str] = []


class PeranUbah(BaseModel):
    nama: str | None = Field(default=None, min_length=1, max_length=100)
    aktif: bool | None = None
    izin: list[str] | None = None


def _setel_izin(conn: Connection, pid: int, izin: list[str]) -> None:
    ada = {r[0] for r in conn.execute(text("SELECT kode FROM sec.izin WHERE kode = ANY(:k)"), {"k": izin})}
    kurang = sorted(set(izin) - ada)
    if kurang:
        raise tidak_valid(f"Izin tidak dikenal: {', '.join(kurang)}.")
    conn.execute(text("INSERT INTO sec.peran_izin (peran_id, izin_kode) SELECT :p, unnest(CAST(:k AS text[]))"
                      " ON CONFLICT DO NOTHING"), {"p": pid, "k": list(ada)})
    conn.execute(text("DELETE FROM sec.peran_izin WHERE peran_id = :p AND NOT (izin_kode = ANY(:k))"),
                 {"p": pid, "k": list(ada)})


@router.get("/izin")
def daftar_izin(conn: Connection = Depends(koneksi), _: Pengguna = Depends(KELOLA)) -> list[dict]:
    return [dict(r) for r in conn.execute(text("SELECT kode, nama FROM sec.izin ORDER BY kode")).mappings()]


@router.get("/peran")
def daftar_peran(conn: Connection = Depends(koneksi), _: Pengguna = Depends(KELOLA)) -> list[dict]:
    rows = conn.execute(text(
        "SELECT p.id, p.kode, p.nama, p.aktif,"
        " coalesce((SELECT array_agg(izin_kode ORDER BY izin_kode) FROM sec.peran_izin WHERE peran_id = p.id), '{}')"
        "   AS izin,"
        " (SELECT count(*) FROM sec.pengguna_peran pp JOIN sec.pengguna u ON u.id = pp.pengguna_id AND u.aktif"
        "   WHERE pp.peran_id = p.id) AS jumlah_pengguna"
        " FROM sec.peran p ORDER BY p.id")).mappings().all()
    return [dict(r) for r in rows]


@router.post("/peran", status_code=201)
def tambah_peran(data: PeranIn, conn: Connection = Depends(koneksi), _: Pengguna = Depends(KELOLA)) -> dict:
    pid = conn.execute(text("INSERT INTO sec.peran (kode, nama) VALUES (:k, :n) RETURNING id"),
                       {"k": data.kode, "n": rapikan(data.nama)}).scalar_one()
    _setel_izin(conn, pid, data.izin)
    return {"id": pid}


@router.patch("/peran/{pid}")
def ubah_peran(pid: int, data: PeranUbah, conn: Connection = Depends(koneksi), _: Pengguna = Depends(KELOLA)) -> dict:
    n = conn.execute(text("UPDATE sec.peran SET nama = coalesce(:n, nama), aktif = coalesce(:a, aktif)"
                          " WHERE id = :i"), {"n": rapikan(data.nama) or None, "a": data.aktif, "i": pid}).rowcount
    if n == 0:
        raise tidak_ada("Peran")
    if data.izin is not None:
        _setel_izin(conn, pid, data.izin)
    cek_pengelola_tersisa(conn)
    return {"id": pid}


@router.delete("/peran/{pid}")
def hapus_peran(pid: int, conn: Connection = Depends(koneksi), _: Pengguna = Depends(KELOLA)) -> dict:
    """Peran yang masih dipegang pengguna dinonaktifkan (tidak memberi izin lagi); yang tidak dipakai dihapus."""
    if conn.execute(text("SELECT 1 FROM sec.peran WHERE id = :i"), {"i": pid}).first() is None:
        raise tidak_ada("Peran")
    dipakai = conn.execute(text("SELECT 1 FROM sec.pengguna_peran WHERE peran_id = :i LIMIT 1"), {"i": pid}).first()
    if dipakai:
        conn.execute(text("UPDATE sec.peran SET aktif = false WHERE id = :i"), {"i": pid})
    else:
        conn.execute(text("DELETE FROM sec.peran_izin WHERE peran_id = :i"), {"i": pid})
        conn.execute(text("DELETE FROM sec.peran WHERE id = :i"), {"i": pid})
    cek_pengelola_tersisa(conn)
    return pesan_hapus("Peran", "dinonaktifkan" if dipakai else "dihapus")


# ================================================================= penugasan
class PenugasanIn(BaseModel):
    pengguna_id: int
    tahun_dasar_id: int
    wilayah_kode: list[str] = Field(min_length=1)
    lapus_ids: list[int] = Field(min_length=1, description="boleh kategori/subkategori: diperluas ke lapus daun")
    peran_tugas: Literal["operator", "pemeriksa"] = "operator"
    berlaku_mulai: date | None = None
    berlaku_sampai: date | None = None


def daun_dari(conn: Connection, td_id: int, lapus_ids: list[int]) -> list[int]:
    """Perluas lapus (kategori/subkategori) ke lapus berdata (daun, TOP, SOP) aktif di bawahnya."""
    rows = conn.execute(text(
        "WITH RECURSIVE t AS (SELECT id, jenis, aktif, tahun_dasar_id FROM ref.lapus WHERE id = ANY(:ids)"
        " UNION ALL SELECT l.id, l.jenis, l.aktif, l.tahun_dasar_id FROM ref.lapus l JOIN t ON l.induk_id = t.id)"
        " SELECT DISTINCT id, jenis, aktif, tahun_dasar_id FROM t"), {"ids": lapus_ids}).all()
    if any(r.tahun_dasar_id != td_id for r in rows) or len({r.id for r in rows} & set(lapus_ids)) != len(
            set(lapus_ids)):
        raise tidak_valid("Lapus tidak ditemukan pada tahun dasar yang dipilih.")
    return sorted(r.id for r in rows if r.jenis in BERITEM and r.aktif)


@router.get("/penugasan")
def daftar_penugasan(tahun_dasar_id: int | None = None, wilayah_kode: str | None = None,
                     pengguna_id: int | None = None, hanya_aktif: bool = True,
                     conn: Connection = Depends(koneksi), _: Pengguna = Depends(KELOLA)) -> list[dict]:
    rows = conn.execute(text(
        "SELECT p.id, p.pengguna_id, u.username, u.nama, p.tahun_dasar_id, td.kode AS tahun_dasar, p.wilayah_kode,"
        " p.lapus_id, l.kode AS kode_lapus, l.nama AS nama_lapus, p.peran_tugas, p.berlaku_mulai, p.berlaku_sampai,"
        " (current_date >= p.berlaku_mulai AND (p.berlaku_sampai IS NULL OR current_date <= p.berlaku_sampai))"
        "   AS aktif"
        " FROM lk.penugasan p JOIN sec.pengguna u ON u.id = p.pengguna_id"
        " JOIN ref.tahun_dasar td ON td.id = p.tahun_dasar_id JOIN ref.lapus l ON l.id = p.lapus_id"
        " WHERE (CAST(:td AS int) IS NULL OR p.tahun_dasar_id = :td)"
        "   AND (CAST(:w AS text) IS NULL OR p.wilayah_kode = :w)"
        "   AND (CAST(:u AS bigint) IS NULL OR p.pengguna_id = :u)"
        "   AND (NOT :aktif OR p.berlaku_sampai IS NULL OR p.berlaku_sampai >= current_date)"
        " ORDER BY u.username, p.wilayah_kode, l.urutan"),
        {"td": tahun_dasar_id, "w": wilayah_kode, "u": pengguna_id, "aktif": hanya_aktif}).mappings().all()
    return [dict(r) for r in rows]


@router.post("/penugasan", status_code=201)
def tambah_penugasan(data: PenugasanIn, conn: Connection = Depends(koneksi), _: Pengguna = Depends(KELOLA)) -> dict:
    u = conn.execute(text("SELECT aktif FROM sec.pengguna WHERE id = :i AND password_hash <> :sis"),
                     {"i": data.pengguna_id, "sis": AKUN_SISTEM}).first()
    if u is None or not u[0]:
        raise tidak_valid("Pengguna tidak ada atau nonaktif.")
    wil = {r[0] for r in conn.execute(text("SELECT kode FROM ref.wilayah WHERE kode = ANY(:k) AND aktif"),
                                      {"k": data.wilayah_kode})}
    if wil != set(data.wilayah_kode):
        raise tidak_valid(f"Wilayah tidak dikenal/nonaktif: {', '.join(sorted(set(data.wilayah_kode) - wil))}.")
    if data.berlaku_sampai and data.berlaku_mulai and data.berlaku_sampai < data.berlaku_mulai:
        raise tidak_valid("Tanggal berlaku sampai tidak boleh sebelum berlaku mulai.")
    daun = daun_dari(conn, data.tahun_dasar_id, data.lapus_ids)
    if not daun:
        raise tidak_valid("Tidak ada lapus daun aktif pada pilihan tersebut.")
    n = conn.execute(text(
        "INSERT INTO lk.penugasan (pengguna_id, tahun_dasar_id, wilayah_kode, lapus_id, peran_tugas, berlaku_mulai,"
        " berlaku_sampai) SELECT :u, :td, w, l, :pt, coalesce(CAST(:mulai AS date), current_date), :sampai"
        " FROM unnest(CAST(:wil AS text[])) w, unnest(CAST(:daun AS int[])) l"
        " ON CONFLICT (pengguna_id, tahun_dasar_id, wilayah_kode, lapus_id, peran_tugas) DO UPDATE"
        " SET berlaku_mulai = EXCLUDED.berlaku_mulai, berlaku_sampai = EXCLUDED.berlaku_sampai"),
        {"u": data.pengguna_id, "td": data.tahun_dasar_id, "pt": data.peran_tugas, "mulai": data.berlaku_mulai,
         "sampai": data.berlaku_sampai, "wil": sorted(wil), "daun": daun}).rowcount
    return {"jumlah": n, "lapus_daun": len(daun), "wilayah": len(wil)}


@router.delete("/penugasan/{pid}")
def akhiri_penugasan(pid: int, conn: Connection = Depends(koneksi), _: Pengguna = Depends(KELOLA)) -> dict:
    """Penugasan tidak dihapus (riwayat): berlaku_sampai = kemarin sehingga hak tulis langsung berakhir."""
    n = conn.execute(text("UPDATE lk.penugasan SET berlaku_sampai = current_date - 1 WHERE id = :i"),
                     {"i": pid}).rowcount
    if n == 0:
        raise tidak_ada("Penugasan")
    return {"hasil": "diakhiri", "pesan": "Penugasan diakhiri; hak tulis pengguna pada lapus ini berakhir."}


# ================================================================= jejak audit
@router.get("/audit")
def jejak_audit(entitas: str | None = None, aksi: str | None = None, pengguna_id: int | None = None,
                dari: date | None = None, sampai: date | None = None,
                halaman: int = Query(default=1, ge=1), per_halaman: int = Query(default=50, ge=1, le=200),
                conn: Connection = Depends(koneksi), _: Pengguna = Depends(butuh_izin("audit.lihat"))) -> dict:
    p = {"e": entitas, "a": aksi, "u": pengguna_id, "dari": dari, "sampai": sampai,
         "lim": per_halaman, "off": (halaman - 1) * per_halaman}
    where = (" WHERE (CAST(:e AS text) IS NULL OR l.entitas = :e) AND (CAST(:a AS text) IS NULL OR l.aksi = :a)"
             " AND (CAST(:u AS bigint) IS NULL OR l.pengguna_id = :u)"
             " AND (CAST(:dari AS date) IS NULL OR l.waktu >= CAST(:dari AS date))"
             " AND (CAST(:sampai AS date) IS NULL OR l.waktu < CAST(:sampai AS date) + 1)")
    total = conn.execute(text("SELECT count(*) FROM audit.log l" + where), p).scalar_one()
    rows = conn.execute(text(
        "SELECT l.id, l.waktu, l.pengguna_id, u.username, host(l.ip) AS ip, l.aksi, l.entitas, l.entitas_id,"
        " l.putaran_id, l.alasan, l.nilai_lama, l.nilai_baru FROM audit.log l"
        " LEFT JOIN sec.pengguna u ON u.id = l.pengguna_id" + where +
        " ORDER BY l.id DESC LIMIT :lim OFFSET :off"), p).mappings().all()
    return {"total": total, "halaman": halaman, "baris": [dict(r) for r in rows]}


@router.get("/audit/verifikasi")
def verifikasi_audit(conn: Connection = Depends(koneksi), _: Pengguna = Depends(butuh_izin("audit.lihat"))) -> dict:
    """Periksa rantai hash audit (hash_sebelum = hash baris sebelumnya)."""
    putus = conn.execute(text(
        "SELECT count(*) FROM (SELECT hash_sebelum, lag(hash) OVER (ORDER BY id) AS prev FROM audit.log) x"
        " WHERE x.prev IS NOT NULL AND x.hash_sebelum IS DISTINCT FROM x.prev")).scalar_one()
    total = conn.execute(text("SELECT count(*) FROM audit.log")).scalar_one()
    return {"utuh": putus == 0, "baris": total, "putus": putus}
