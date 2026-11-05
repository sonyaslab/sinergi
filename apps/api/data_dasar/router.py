"""Endpoint Data Dasar (F3): grid item x seri, simpan sel, + Komoditas, nonaktif/berlaku/sambung (dengan
usulan jangkar dari overlap), seri dan tautan item, jangkar, seri referensi, hitung ulang, validasi.

Semua tulis memakai koneksi app_rw ber-RLS (operator hanya lapus/wilayah yang ditugaskan; putaran terkunci -> 423)
dan memicu hitung ulang otomatis (antrean per wilayah). Perubahan data/item/jangkar/tautan mengembalikan status lapus
ke draf (F4, keputusan 19). Daftar putaran: `putaran/router.py`. Pesan tidak memuat angka.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any, Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import Connection, text

from ..app.deps import Pengguna, butuh_izin, koneksi, pengguna_aktif
from ..app.galat import GalatSinergi
from ..engine import Empat, hitung_wilayah
from ..engine.graf import Pohon
from ..engine.turunan import selesaikan
from ..engine.umum import bagi, rata_isi, v
from ..impor import tautan as tt
from ..master.umum import rapikan, tidak_ada, tidak_valid
from ..putaran.status import tandai_ubah
from ..worker.antrean import antrekan
from ..worker.muat import muat
from . import validasi_db

router = APIRouter(prefix="/api", tags=["data-dasar"])
ISI = Depends(butuh_izin("data_dasar.isi"))
TAMBAH = Depends(butuh_izin("item.tambah"))
BACA = Depends(butuh_izin("data_dasar.isi", "data_dasar.impor", "lk.setujui", "tabel_pokok.lihat"))
KELOLA = Depends(butuh_izin("master.kelola"))
JANGKAR = {"RKA": "RKA_TD", "HARGA": "H_TD", "IH": "IH_TD", "R_MARGIN": "R_MARGIN_TD"}


def _label(u: int) -> str:
    return f"Q{u % 4 + 1}-{u // 4}"


def _putaran(conn: Connection, putaran_id: int) -> dict:
    r = conn.execute(text(
        "SELECT p.id, p.tahun_dasar_id, p.nama, p.jenis, p.status, p.tahun, p.triwulan, pa.urut AS awal,"
        " pz.urut AS akhir, t.kode AS td_kode, t.tahun_awal_seri, t.tahun_baseline_eks, t.jangkar_dari_data"
        " FROM lk.putaran p JOIN ref.periode pa ON pa.id = p.periode_awal_id JOIN ref.periode pz"
        " ON pz.id = p.periode_akhir_id JOIN ref.tahun_dasar t ON t.id = p.tahun_dasar_id WHERE p.id = :p"),
        {"p": putaran_id}).mappings().first()
    if r is None:
        raise tidak_ada("Putaran")
    return dict(r)


def _boleh(conn: Connection, wilayah: str, lapus_id: int) -> bool:
    return bool(conn.execute(text("SELECT lk.boleh_tulis(CAST(:w AS char(4)), :l)"),
                             {"w": wilayah, "l": lapus_id}).scalar())


def _cek_tulis(conn: Connection, wilayah: str, lapus_id: int) -> None:
    if not _boleh(conn, wilayah, lapus_id):
        raise GalatSinergi(403, "TIDAK_DITUGASKAN", "Lapus/wilayah ini tidak ditugaskan kepada Anda.")


def _terbuka(p: dict) -> None:
    if p["status"] == "terkunci":
        raise GalatSinergi(423, "PUTARAN_TERKUNCI", "Putaran sudah dikunci. Perubahan tidak dapat disimpan.")


# ======================================================================== grid
def _lapus_target(conn: Connection, td: int, lapus_id: int) -> list[dict]:
    rows = conn.execute(text("SELECT id, kode, nama, jenis, induk_id, urutan FROM ref.lapus WHERE tahun_dasar_id = :td"
                             " AND aktif ORDER BY urutan"), {"td": td}).mappings().all()
    b = {r["id"]: dict(r) for r in rows}
    if lapus_id not in b:
        raise tidak_ada("Lapus")
    anak: dict[int, list[int]] = defaultdict(list)
    for r in rows:
        if r["induk_id"]:
            anak[r["induk_id"]].append(r["id"])
    out: list[dict] = []

    def turun(i: int) -> None:
        if b[i]["jenis"] in ("daun", "top", "sop"):
            out.append(b[i])
        for a in anak.get(i, []):
            turun(a)

    turun(lapus_id)
    return out


@router.get("/data-dasar/grid")
def grid(putaran_id: int, wilayah: str, lapus_id: int, conn: Connection = Depends(koneksi),
         _: Pengguna = BACA) -> dict:
    """Grid satu kategori/subkategori: baris = item x seri, kolom = triwulan (kosong != nol)."""
    p = _putaran(conn, putaran_id)
    td = p["tahun_dasar_id"]
    lapus = _lapus_target(conn, td, lapus_id)
    lids = [r["id"] for r in lapus]
    q = {"p": putaran_id, "w": wilayah, "td": td, "l": lids}
    tampil = min(p["awal"], max(2019 * 4, p["tahun_awal_seri"] * 4))  # seri 2019+ (atau awal putaran bila lebih awal)
    periode = [{"urut": u, "label": _label(u), "ubah": p["awal"] <= u <= p["akhir"]}
               for u in range(tampil, p["akhir"] + 1)]
    items = [dict(r) for r in conn.execute(text(
        "SELECT i.id, i.lapus_id, l.kode AS kode_lapus, i.metode_kode AS metode, i.nomor, i.nama, i.status,"
        " i.jenis_indeks, i.satuan_kode, i.sumber_teks AS sumber, i.katalog_id, i.item_asal_id, i.alasan,"
        " pm.urut AS mulai, ps.urut AS selesai FROM lk.item i JOIN ref.lapus l ON l.id = i.lapus_id"
        " LEFT JOIN ref.periode pm ON pm.id = i.periode_mulai_id LEFT JOIN ref.periode ps"
        " ON ps.id = i.periode_selesai_id WHERE i.tahun_dasar_id = :td AND i.wilayah_kode = :w"
        " AND i.lapus_id = ANY(:l) ORDER BY l.urutan, array_position(ARRAY['REV','EKS','DEF','PDK'], i.metode_kode),"
        " i.nomor"), q).mappings()]
    ids = [i["id"] for i in items]
    qi = {**q, "i": ids}
    meta: dict[int, dict[str, dict]] = defaultdict(dict)
    for r in conn.execute(text("SELECT * FROM lk.seri_item WHERE item_id = ANY(:i) ORDER BY urutan"), qi).mappings():
        meta[r["item_id"]][r["jenis_seri"]] = dict(r)
    nilai: dict[tuple[int, str], dict[int, float]] = defaultdict(dict)
    tt_sel: dict[tuple[int, str], list[int]] = defaultdict(list)
    for iid, s, u, x, st in conn.execute(text(
            "SELECT n.item_id, n.jenis_seri, pe.urut, n.nilai::float8, n.status_sel FROM lk.nilai_item n"
            " JOIN ref.periode pe ON pe.id = n.periode_id WHERE n.putaran_id = :p AND n.item_id = ANY(:i)"), qi):
        if st == "isi":
            nilai[(iid, s)][u] = x
        elif st == "tidak_tersedia":
            tt_sel[(iid, s)].append(u)
    param: dict[int, dict[str, dict]] = defaultdict(dict)
    for r in conn.execute(text("SELECT item_id, kode, nilai::float8 AS nilai, alasan FROM lk.parameter_item"
                               " WHERE putaran_id = :p AND item_id = ANY(:i)"), qi).mappings():
        param[r["item_id"]][r["kode"]] = {"nilai": r["nilai"], "alasan": r["alasan"]}
    kode_lapus = {r[0]: r[1] for r in conn.execute(text("SELECT id, kode FROM ref.lapus WHERE tahun_dasar_id = :td"),
                                                   q)}
    taut: dict[int, dict[str, dict]] = defaultdict(dict)
    for r in conn.execute(text(
            "SELECT t.*, s.kode AS kode_ref FROM lk.tautan_seri t LEFT JOIN lk.seri_referensi s ON s.id = t.seri_id"
            " WHERE t.item_id = ANY(:i)"), qi).mappings():
        lap = tuple(kode_lapus.get(x, "?") for x in (r["lapus_sumber_ids"] or ()))
        taut[r["item_id"]][r["jenis_seri"]] = {
            "sumber": r["sumber"], "rumus": r["rumus"], "seri_ref": r["kode_ref"], "seri_id": r["seri_id"],
            "lapus_sumber_ids": r["lapus_sumber_ids"] or [], "lapus_sumber": list(lap), "besaran": r["besaran"],
            "faktor": float(r["faktor"]),
            "teks": tt.teks_kanonik(r["sumber"], r["rumus"], r["kode_ref"], lap, r["besaran"], float(r["faktor"]))}
    turunan = _seri_turunan(conn, putaran_id, wilayah, {i for i in ids if taut.get(i)})
    kontrib = _kontribusi(conn, putaran_id, ids, items)
    urut_seri = {(m, k): u for m, k, u in conn.execute(text("SELECT metode_kode, kode, urutan FROM ref.jenis_seri"))}
    bawaan: dict[str, list[str]] = defaultdict(list)
    for m, k in conn.execute(text("SELECT metode_kode, kode FROM ref.jenis_seri WHERE NOT komponen ORDER BY urutan")):
        bawaan[m].append(k)
    boleh = {lid: _boleh(conn, wilayah, lid) for lid in lids}
    for lp in lapus:
        lp["boleh_tulis"] = boleh[lp["id"]]
    for it in items:
        iid = it["id"]
        kode = list(meta[iid])
        lain = ({s for (i, s) in nilai if i == iid} | set(taut[iid]) |
                {s for s, kp in JANGKAR.items() if kp in param[iid]}) - set(kode)
        if not kode:
            lain |= set(bawaan[it["metode"]])
        kode += sorted(lain, key=lambda s: urut_seri.get((it["metode"], s), 99))
        it["boleh_tulis"] = boleh[it["lapus_id"]]
        it["kontribusi"] = kontrib.get(iid, {})
        it["seri"] = [{
            "kode": s, "satuan": meta[iid].get(s, {}).get("satuan"), "label": meta[iid].get(s, {}).get("label"),
            "catatan": meta[iid].get(s, {}).get("catatan"), "tautan": taut[iid].get(s),
            "jangkar": ({"kode": JANGKAR[s], **param[iid][JANGKAR[s]]} if s in JANGKAR and JANGKAR[s] in param[iid]
                        else ({"kode": JANGKAR[s], "nilai": None, "alasan": None} if s in JANGKAR else None)),
            "nilai": {str(u): x for u, x in nilai.get((iid, s), {}).items()},
            "tidak_tersedia": tt_sel.get((iid, s), []),
            "nilai_turunan": {str(u): x for u, x in turunan.get((iid, s), {}).items()},
        } for s in kode]
    temuan = [dict(r) for r in conn.execute(text(
        "SELECT h.kode_validasi AS kode, h.tingkat, h.lapus_id, h.item_id, h.jenis_seri, pe.urut AS periode, h.pesan,"
        " h.kunci, h.dikonfirmasi_oleh IS NOT NULL AS dikonfirmasi, h.alasan_konfirmasi FROM lk.hasil_validasi h"
        " LEFT JOIN ref.periode pe ON pe.id = h.periode_id WHERE h.putaran_id = :p AND h.wilayah_kode = :w"
        " AND h.lapus_id = ANY(:l) ORDER BY h.kode_validasi, h.id"), q).mappings()]
    return {"putaran": p, "periode": periode, "lapus": lapus, "item": items, "validasi": temuan,
            "antrean": _status_antrean(conn, putaran_id, wilayah)}


def _seri_turunan(conn: Connection, putaran_id: int, wilayah: str, ids: set[int]) -> dict[tuple[int, str], dict]:
    """Nilai seri tertaut/rumus yang dipakai mesin (tampilan baris hijau/biru), dihitung saat diminta."""
    if not ids:
        return {}
    m, _ = muat(conn, putaran_id, wilayah)
    h = hitung_wilayah(m)
    pohon = Pohon(m.pohon)
    nol = Empat.nol(len(h.sumbu))

    def benc(xs: Any) -> list[Empat]:
        return [h.lapus[i].tahap["BENC"] if i in h.lapus else nol for i in xs]

    out: dict[tuple[int, str], dict] = {}
    for d in m.data.values():
        for it in d.item:
            if it.id not in ids:
                continue
            siap = selesaikan(it, h.sumbu, m.konfig, m.referensi, pohon.urai, benc)
            for t in it.tautan:
                out[(it.id, t.jenis_seri)] = siap.seri.get(t.jenis_seri, {})
    return out


def _kontribusi(conn: Connection, putaran_id: int, ids: list[int], items: list[dict]) -> dict[int, dict[str, Any]]:
    """Kontribusi item terhadap output lapus (jumlah item, ADHB dan ADHK) per triwulan, dalam persen."""
    if not ids:
        return {}
    lapus_dari = {i["id"]: i["lapus_id"] for i in items}
    per: dict[int, dict[int, tuple[float, float]]] = defaultdict(dict)
    total: dict[tuple[int, int], list[float]] = defaultdict(lambda: [0.0, 0.0])
    for iid, u, cp, k in conn.execute(text(
            "SELECT h.item_id, pe.urut, h.out_cp::float8, h.out_k::float8 FROM lk.hasil_item h JOIN ref.periode pe"
            " ON pe.id = h.periode_id WHERE h.putaran_id = :p AND h.item_id = ANY(:i)"), {"p": putaran_id, "i": ids}):
        per[iid][u] = (cp, k)
        t = total[(lapus_dari[iid], u)]
        t[0] += cp
        t[1] += k
    out: dict[int, dict[str, Any]] = {}
    for iid, d in per.items():
        lid = lapus_dari[iid]
        out[iid] = {str(u): [round(bagi(cp, total[(lid, u)][0]) * 100, 2), round(bagi(k, total[(lid, u)][1]) * 100, 2)]
                    for u, (cp, k) in d.items()}
    return out


def _status_antrean(conn: Connection, putaran_id: int, wilayah: str) -> dict:
    r = conn.execute(text(
        "SELECT count(*) FILTER (WHERE status IN ('menunggu','proses')) AS berjalan,"
        " (SELECT row_to_json(x) FROM (SELECT id, status, pesan, selesai_pada FROM lk.antrean_hitung"
        "  WHERE putaran_id = :p AND wilayah_kode = :w AND status IN ('selesai','gagal')"
        "  ORDER BY id DESC LIMIT 1) x) AS terakhir FROM lk.antrean_hitung"
        " WHERE putaran_id = :p AND wilayah_kode = :w"),
        {"p": putaran_id, "w": wilayah}).one()
    return {"berjalan": int(r.berjalan or 0), "terakhir": r.terakhir}


# ======================================================================== simpan sel
class Sel(BaseModel):
    item_id: int
    seri: str = Field(min_length=1, max_length=30)
    periode: int
    nilai: float | None = None
    tidak_tersedia: bool = False


class SimpanSel(BaseModel):
    putaran_id: int
    perubahan: list[Sel] = Field(min_length=1, max_length=20000)


@router.put("/data-dasar/nilai")
def simpan_nilai(data: SimpanSel, conn: Connection = Depends(koneksi), pengguna: Pengguna = ISI) -> dict:
    """Simpan sel grid (batch). Kosong = hapus nilai (belum diisi); `tidak_tersedia` = kosong yang disengaja."""
    p = _putaran(conn, data.putaran_id)
    _terbuka(p)
    ids = sorted({s.item_id for s in data.perubahan})
    items = {r.id: r for r in conn.execute(text(
        "SELECT i.id, i.wilayah_kode, i.lapus_id, i.metode_kode FROM lk.item i WHERE i.id = ANY(:i)"
        " AND i.tahun_dasar_id = :td"), {"i": ids, "td": p["tahun_dasar_id"]})}
    if len(items) != len(ids):
        raise tidak_ada("Item")
    seri_ok = defaultdict(set)
    for m, k in conn.execute(text("SELECT metode_kode, kode FROM ref.jenis_seri")):
        seri_ok[m].add(k)
    tertaut = {(r[0], r[1]) for r in conn.execute(text(
        "SELECT item_id, jenis_seri FROM lk.tautan_seri WHERE item_id = ANY(:i)"), {"i": ids})}
    for wl in {(r.wilayah_kode.strip(), r.lapus_id) for r in items.values()}:
        _cek_tulis(conn, *wl)
    per = {int(r[0]): int(r[1]) for r in conn.execute(text("SELECT urut, id FROM ref.periode"))}
    isi: list[Sel] = []
    kosong: list[Sel] = []
    tdk: list[Sel] = []
    for s in data.perubahan:
        it = items[s.item_id]
        if s.seri not in seri_ok[it.metode_kode]:
            raise tidak_valid(f"Seri {s.seri} tidak berlaku untuk metode {it.metode_kode}.")
        if (s.item_id, s.seri) in tertaut:
            raise tidak_valid(f"Seri {s.seri} tertaut/dihitung otomatis; nilainya tidak dapat diketik.")
        if s.periode not in per or not p["awal"] <= s.periode <= p["akhir"]:
            raise tidak_valid("Periode di luar cakupan putaran ini.")
        (tdk if s.tidak_tersedia else isi if s.nilai is not None else kosong).append(s)
    if isi:
        conn.execute(text(
            "INSERT INTO lk.nilai_item (putaran_id, item_id, jenis_seri, periode_id, nilai, status_sel, diubah_oleh)"
            " SELECT :p, x.i, x.s, x.per, x.v, 'isi', :u FROM unnest(CAST(:i AS bigint[]), CAST(:s AS text[]),"
            " CAST(:per AS int[]), CAST(:v AS float8[])) AS x(i, s, per, v)"
            " ON CONFLICT (putaran_id, item_id, jenis_seri, periode_id) DO UPDATE SET nilai = EXCLUDED.nilai,"
            " status_sel = 'isi', diubah_oleh = EXCLUDED.diubah_oleh, diubah_pada = now()"),
            {"p": data.putaran_id, "u": pengguna.id, "i": [s.item_id for s in isi], "s": [s.seri for s in isi],
             "per": [per[s.periode] for s in isi], "v": [s.nilai for s in isi]})
    if tdk:
        conn.execute(text(
            "INSERT INTO lk.nilai_item (putaran_id, item_id, jenis_seri, periode_id, nilai, status_sel, diubah_oleh)"
            " SELECT :p, x.i, x.s, x.per, NULL, 'tidak_tersedia', :u FROM unnest(CAST(:i AS bigint[]),"
            " CAST(:s AS text[]), CAST(:per AS int[])) AS x(i, s, per)"
            " ON CONFLICT (putaran_id, item_id, jenis_seri, periode_id) DO UPDATE SET nilai = NULL,"
            " status_sel = 'tidak_tersedia', diubah_oleh = EXCLUDED.diubah_oleh, diubah_pada = now()"),
            {"p": data.putaran_id, "u": pengguna.id, "i": [s.item_id for s in tdk], "s": [s.seri for s in tdk],
             "per": [per[s.periode] for s in tdk]})
    if kosong:
        conn.execute(text(
            "DELETE FROM lk.nilai_item n USING unnest(CAST(:i AS bigint[]), CAST(:s AS text[]), CAST(:per AS int[]))"
            " AS x(i, s, per) WHERE n.putaran_id = :p AND n.item_id = x.i AND n.jenis_seri = x.s"
            " AND n.periode_id = x.per"),
            {"p": data.putaran_id, "i": [s.item_id for s in kosong], "s": [s.seri for s in kosong],
             "per": [per[s.periode] for s in kosong]})
    ubah = {(items[x.item_id].wilayah_kode.strip(), items[x.item_id].lapus_id) for x in data.perubahan}
    tandai_ubah(conn, data.putaran_id, ubah, "simpan data dasar")
    for w in sorted({r.wilayah_kode.strip() for r in items.values()}):
        antrekan(conn, data.putaran_id, w, None, "simpan data dasar")
    return {"disimpan": len(isi), "tidak_tersedia": len(tdk), "dikosongkan": len(kosong),
            "pesan": "Tersimpan. Hitung ulang otomatis sedang berjalan."}


# ======================================================================== jangkar (parameter item)
class ParamIn(BaseModel):
    putaran_id: int
    item_id: int
    kode: Literal["RKA_TD", "H_TD", "IH_TD", "R_MARGIN_TD"]
    nilai: float | None = None
    alasan: str | None = Field(default=None, max_length=500)


@router.put("/data-dasar/parameter")
def simpan_parameter(data: ParamIn, conn: Connection = Depends(koneksi), pengguna: Pengguna = ISI) -> dict:
    p = _putaran(conn, data.putaran_id)
    _terbuka(p)
    it = conn.execute(text("SELECT wilayah_kode, lapus_id FROM lk.item WHERE id = :i AND tahun_dasar_id = :td"),
                      {"i": data.item_id, "td": p["tahun_dasar_id"]}).first()
    if it is None:
        raise tidak_ada("Item")
    _cek_tulis(conn, it.wilayah_kode.strip(), it.lapus_id)
    alasan = rapikan(data.alasan) or None
    if data.kode in ("H_TD", "IH_TD") and data.nilai is not None and len(alasan or "") < 10:
        raise tidak_valid("Jangkar pengganti (harga/IH tahun dasar) wajib beralasan (min. 10 karakter).")
    q = {"p": data.putaran_id, "i": data.item_id, "k": data.kode, "v": data.nilai, "a": alasan, "u": pengguna.id}
    if data.nilai is None:
        conn.execute(text("DELETE FROM lk.parameter_item WHERE putaran_id = :p AND item_id = :i AND kode = :k"), q)
    else:
        conn.execute(text(
            "INSERT INTO lk.parameter_item (putaran_id, item_id, kode, nilai, alasan, diubah_oleh)"
            " VALUES (:p, :i, :k, :v, :a, :u) ON CONFLICT (putaran_id, item_id, kode) DO UPDATE SET"
            " nilai = EXCLUDED.nilai, alasan = EXCLUDED.alasan, diubah_oleh = EXCLUDED.diubah_oleh,"
            " diubah_pada = now()"), q)
    tandai_ubah(conn, data.putaran_id, [(it.wilayah_kode, it.lapus_id)], "ubah jangkar tahun dasar")
    antrekan(conn, data.putaran_id, it.wilayah_kode.strip(), it.lapus_id, "ubah jangkar tahun dasar")
    return {"pesan": "Jangkar tersimpan."}


# ======================================================================== + Komoditas, ubah item
class ItemIn(BaseModel):
    putaran_id: int
    wilayah: str = Field(min_length=4, max_length=4)
    lapus_id: int
    metode: Literal["REV", "EKS", "DEF", "PDK"]
    nama: str = Field(min_length=1, max_length=200)
    katalog_id: int | None = None
    satuan_kode: str | None = None
    jenis_indeks: Literal["IP", "IB"] | None = None
    mulai: int | None = None
    selesai: int | None = None
    sumber: str | None = Field(default=None, max_length=300)
    alasan: str = Field(min_length=10, max_length=500)
    seri: list[str] | None = None


def _periode_id(conn: Connection, u: int | None) -> int | None:
    if u is None:
        return None
    r = conn.execute(text("SELECT id FROM ref.periode WHERE urut = :u"), {"u": u}).scalar()
    if r is None:
        raise tidak_valid("Periode berlaku tidak dikenal.")
    return int(r)


def _seri_bawaan(conn: Connection, metode: str, diminta: list[str] | None) -> list[str]:
    semua = [(k, kmp) for k, kmp in conn.execute(text(
        "SELECT kode, komponen FROM ref.jenis_seri WHERE metode_kode = :m ORDER BY urutan"), {"m": metode})]
    if diminta is None:
        return [k for k, kmp in semua if not kmp]
    salah = set(diminta) - {k for k, _ in semua}
    if salah:
        raise tidak_valid(f"Seri {', '.join(sorted(salah))} tidak berlaku untuk metode {metode}.")
    return list(dict.fromkeys(diminta))


@router.post("/data-dasar/item", status_code=201)
def tambah_item(data: ItemIn, conn: Connection = Depends(koneksi), pengguna: Pengguna = TAMBAH) -> dict:
    """+ Komoditas: nomor berikutnya per metode, masa berlaku, alasan wajib; seri bawaan metode dibuat."""
    p = _putaran(conn, data.putaran_id)
    _terbuka(p)
    lap = conn.execute(text("SELECT jenis FROM ref.lapus WHERE id = :l AND tahun_dasar_id = :td AND aktif"),
                       {"l": data.lapus_id, "td": p["tahun_dasar_id"]}).scalar()
    if lap not in ("daun", "top", "sop"):
        raise tidak_valid("Komoditas hanya dapat ditambahkan pada lapus berdata (daun, TOP, SOP).")
    if data.metode == "EKS" and data.jenis_indeks is None:
        raise tidak_valid("Item EKS wajib memilih jenis indeks (IP atau IB).")
    if data.mulai is not None and data.selesai is not None and data.selesai < data.mulai:
        raise tidak_valid("Berlaku sampai harus sesudah berlaku mulai.")
    _cek_tulis(conn, data.wilayah, data.lapus_id)
    maks = conn.execute(text("SELECT maks_item FROM ref.metode WHERE kode = :m"), {"m": data.metode}).scalar_one()
    nomor = conn.execute(text(
        "SELECT coalesce(max(nomor), 0) + 1 FROM lk.item WHERE tahun_dasar_id = :td AND wilayah_kode = :w"
        " AND lapus_id = :l AND metode_kode = :m"),
        {"td": p["tahun_dasar_id"], "w": data.wilayah, "l": data.lapus_id, "m": data.metode}).scalar_one()
    if nomor > maks:
        raise tidak_valid(f"Batas {maks} item untuk metode {data.metode} sudah tercapai.")
    nama = rapikan(data.nama)
    seri = _seri_bawaan(conn, data.metode, data.seri)
    iid = conn.execute(text(
        "INSERT INTO lk.item (tahun_dasar_id, wilayah_kode, lapus_id, metode_kode, nomor, katalog_id, nama,"
        " satuan_kode, sumber_teks, jenis_indeks, periode_mulai_id, periode_selesai_id, dibuat_putaran_id,"
        " dibuat_oleh, alasan)"
        " VALUES (:td, :w, :l, :m, :n, :kat, :nama, :sat, :sum, :ji, :mulai, :selesai, :p, :u, :al) RETURNING id"),
        {"td": p["tahun_dasar_id"], "w": data.wilayah, "l": data.lapus_id, "m": data.metode, "n": nomor,
         "kat": data.katalog_id, "nama": nama, "sat": data.satuan_kode, "sum": rapikan(data.sumber) or None,
         "ji": data.jenis_indeks if data.metode == "EKS" else None, "mulai": _periode_id(conn, data.mulai),
         "selesai": _periode_id(conn, data.selesai), "p": data.putaran_id, "u": pengguna.id,
         "al": rapikan(data.alasan)}).scalar_one()
    for i, s in enumerate(seri, start=1):
        conn.execute(text("INSERT INTO lk.seri_item (item_id, jenis_seri, urutan) VALUES (:i, :s, :u)"),
                     {"i": iid, "s": s, "u": i})
    tandai_ubah(conn, data.putaran_id, [(data.wilayah, data.lapus_id)], "tambah komoditas")
    antrekan(conn, data.putaran_id, data.wilayah, data.lapus_id, "tambah komoditas")
    return {"id": iid, "nomor": nomor, "pesan": f"Komoditas ditambahkan sebagai {data.metode} no. {nomor}."}


class ItemUbah(BaseModel):
    putaran_id: int
    nama: str | None = Field(default=None, min_length=1, max_length=200)
    status: Literal["aktif", "nonaktif"] | None = None
    mulai: int | None = None
    selesai: int | None = None
    jenis_indeks: Literal["IP", "IB"] | None = None
    satuan_kode: str | None = None
    sumber: str | None = Field(default=None, max_length=300)
    katalog_id: int | None = None
    alasan: str = Field(min_length=10, max_length=500)


@router.patch("/data-dasar/item/{item_id}")
def ubah_item(item_id: int, data: ItemUbah, conn: Connection = Depends(koneksi), pengguna: Pengguna = TAMBAH) -> dict:
    """Ubah item: nonaktifkan (riwayat tetap dihitung), masa berlaku, jenis indeks, satuan, nama. Alasan wajib."""
    p = _putaran(conn, data.putaran_id)
    _terbuka(p)
    it = conn.execute(text("SELECT id, wilayah_kode, lapus_id, metode_kode FROM lk.item WHERE id = :i"
                           " AND tahun_dasar_id = :td"), {"i": item_id, "td": p["tahun_dasar_id"]}).first()
    if it is None:
        raise tidak_ada("Item")
    _cek_tulis(conn, it.wilayah_kode.strip(), it.lapus_id)
    f = data.model_fields_set - {"putaran_id", "alasan"}
    if not f:
        raise tidak_valid("Tidak ada perubahan.")
    if "jenis_indeks" in f and it.metode_kode == "EKS" and data.jenis_indeks is None:
        raise tidak_valid("Item EKS wajib punya jenis indeks.")
    sets, q = [], {"i": item_id, "al": rapikan(data.alasan)}
    peta = {"nama": ("nama", rapikan(data.nama) if data.nama else None), "status": ("status", data.status),
            "jenis_indeks": ("jenis_indeks", data.jenis_indeks), "satuan_kode": ("satuan_kode", data.satuan_kode),
            "sumber": ("sumber_teks", rapikan(data.sumber) or None), "katalog_id": ("katalog_id", data.katalog_id),
            "mulai": ("periode_mulai_id", _periode_id(conn, data.mulai)),
            "selesai": ("periode_selesai_id", _periode_id(conn, data.selesai))}
    for k in sorted(f):
        kol, nilai = peta[k]
        sets.append(f"{kol} = :{kol}")
        q[kol] = nilai
    conn.execute(text("SELECT set_config('app.alasan', :a, true)"), {"a": q["al"]})
    conn.execute(text(f"UPDATE lk.item SET {', '.join(sets)} WHERE id = :i"), q)
    cek = conn.execute(text("SELECT pm.urut, ps.urut FROM lk.item i LEFT JOIN ref.periode pm"
                            " ON pm.id = i.periode_mulai_id LEFT JOIN ref.periode ps ON ps.id = i.periode_selesai_id"
                            " WHERE i.id = :i"), {"i": item_id}).one()
    if cek[0] is not None and cek[1] is not None and cek[1] < cek[0]:
        raise tidak_valid("Berlaku sampai harus sesudah berlaku mulai.")
    tandai_ubah(conn, data.putaran_id, [(it.wilayah_kode, it.lapus_id)], "ubah item")
    antrekan(conn, data.putaran_id, it.wilayah_kode.strip(), it.lapus_id, "ubah item")
    return {"pesan": "Item diperbarui."}


# ======================================================================== sambungkan ke item penerus
class SambungIn(BaseModel):
    putaran_id: int
    penerus_id: int
    alasan: str = Field(min_length=10, max_length=500)


def usulan_jangkar(lama: dict, baru: dict, t0: list[int], jdd: bool) -> dict:
    """Usulan jangkar item lama dari item penerus (keputusan 14). Hanya usulan; operator menyimpan sendiri.

    lama/baru = {"metode", "seri": {kode: {urut: nilai}}, "param": {kode: nilai}}. Overlap = triwulan yang punya
    data kedua item. H_TD (REV) = harga tahun dasar penerus x (harga rata-rata tertimbang lama / penerus pada
    overlap); IH_TD = IH tahun dasar penerus x (rata-rata IH lama / penerus pada overlap); RKA_TD = RKA_TD penerus.
    """
    out: list[dict] = []
    catatan: list[str] = []
    sl, sb, pb = lama["seri"], baru["seri"], baru["param"]
    if lama["metode"] == "REV" and baru["metode"] == "REV":
        o = sorted(set(sl.get("KUANTUM", {})) & set(sl.get("HARGA", {})) & set(sb.get("KUANTUM", {}))
                   & set(sb.get("HARGA", {})))
        if o:
            def hw(s: dict, us: list[int]) -> float:
                return bagi(sum(v(s.get("KUANTUM"), u) * v(s.get("HARGA"), u) for u in us),
                            sum(v(s.get("KUANTUM"), u) for u in us))
            h_baru = pb.get("H_TD") if pb.get("H_TD") is not None else (hw(sb, t0) if jdd else None)
            if h_baru:
                out.append({"kode": "H_TD", "nilai": h_baru * bagi(hw(sl, o), hw(sb, o)), "overlap": [_label(u)
                            for u in o], "dasar": "harga tahun dasar penerus x rasio harga tertimbang overlap"})
    if lama["metode"] in ("EKS", "DEF") and baru["metode"] in ("EKS", "DEF"):
        o = sorted(set(sl.get("IH", {})) & set(sb.get("IH", {})))
        if o:
            ih_baru = pb.get("IH_TD") if pb.get("IH_TD") is not None else (rata_isi(sb.get("IH"), t0) if jdd else None)
            if ih_baru:
                out.append({"kode": "IH_TD", "nilai": ih_baru * bagi(rata_isi(sl.get("IH"), o),
                                                                     rata_isi(sb.get("IH"), o)),
                            "overlap": [_label(u) for u in o], "dasar": "IH tahun dasar penerus x rasio IH overlap"})
    if pb.get("RKA_TD") is not None:
        out.append({"kode": "RKA_TD", "nilai": pb["RKA_TD"], "overlap": [], "dasar": "RKA_TD item penerus"})
    o_all = sorted(set().union(*[set(x) for x in sl.values()]) & set().union(*[set(x) for x in sb.values()])) \
        if sl and sb else []
    if not o_all:
        catatan.append("Tidak ada triwulan overlap; jangkar diisi manual.")
    elif len(o_all) < 4:
        catatan.append("Overlap kurang dari satu tahun (docs/04 §3: minimal satu tahun).")
    return {"usulan": out, "catatan": catatan, "overlap": [_label(u) for u in o_all]}


def _data_item(conn: Connection, putaran_id: int, iid: int) -> dict:
    r = conn.execute(text("SELECT metode_kode, wilayah_kode, lapus_id, tahun_dasar_id FROM lk.item WHERE id = :i"),
                     {"i": iid}).first()
    if r is None:
        raise tidak_ada("Item")
    seri: dict[str, dict[int, float]] = defaultdict(dict)
    for s, u, x in conn.execute(text(
            "SELECT n.jenis_seri, pe.urut, n.nilai::float8 FROM lk.nilai_item n JOIN ref.periode pe ON pe.id ="
            " n.periode_id WHERE n.putaran_id = :p AND n.item_id = :i AND n.status_sel = 'isi'"),
            {"p": putaran_id, "i": iid}):
        seri[s][u] = x
    par = {k: x for k, x in conn.execute(text(
        "SELECT kode, nilai::float8 FROM lk.parameter_item WHERE putaran_id = :p AND item_id = :i"),
        {"p": putaran_id, "i": iid})}
    return {"metode": r.metode_kode, "wilayah": r.wilayah_kode.strip(), "lapus_id": r.lapus_id,
            "td": r.tahun_dasar_id, "seri": dict(seri), "param": par}


@router.get("/data-dasar/item/{item_id}/usulan-jangkar")
def lihat_usulan(item_id: int, putaran_id: int, penerus_id: int, conn: Connection = Depends(koneksi),
                 _: Pengguna = BACA) -> dict:
    p = _putaran(conn, putaran_id)
    t0 = [p["tahun_baseline_eks"] * 4 + q for q in range(4)]
    return usulan_jangkar(_data_item(conn, putaran_id, item_id), _data_item(conn, putaran_id, penerus_id), t0,
                          bool(p["jangkar_dari_data"]))


@router.post("/data-dasar/item/{item_id}/sambung")
def sambung(item_id: int, data: SambungIn, conn: Connection = Depends(koneksi), pengguna: Pengguna = TAMBAH) -> dict:
    """Sambungkan item lama ke item penerus (rebasing, docs/04 §3). Mengembalikan usulan jangkar (keputusan 14)."""
    p = _putaran(conn, data.putaran_id)
    _terbuka(p)
    if item_id == data.penerus_id:
        raise tidak_valid("Item tidak dapat disambung ke dirinya sendiri.")
    lama, baru = _data_item(conn, data.putaran_id, item_id), _data_item(conn, data.putaran_id, data.penerus_id)
    if lama["td"] != baru["td"] or lama["td"] != p["tahun_dasar_id"] or lama["wilayah"] != baru["wilayah"]:
        raise tidak_valid("Item penerus harus pada tahun dasar dan wilayah yang sama.")
    _cek_tulis(conn, baru["wilayah"], baru["lapus_id"])
    conn.execute(text("SELECT set_config('app.alasan', :a, true)"), {"a": rapikan(data.alasan)})
    conn.execute(text("UPDATE lk.item SET item_asal_id = :a WHERE id = :b"), {"a": item_id, "b": data.penerus_id})
    tandai_ubah(conn, data.putaran_id, [(baru["wilayah"], baru["lapus_id"])], "sambung item penerus")
    t0 = [p["tahun_baseline_eks"] * 4 + q for q in range(4)]
    return {"pesan": "Item disambungkan ke penerus. Jangkar item lama tetap wajib diisi (V03).",
            **usulan_jangkar(lama, baru, t0, bool(p["jangkar_dari_data"]))}


# ======================================================================== seri & tautan item
class SeriItemIn(BaseModel):
    putaran_id: int
    seri: list[str] = Field(min_length=1, max_length=20)


@router.put("/data-dasar/item/{item_id}/seri")
def atur_seri(item_id: int, data: SeriItemIn, conn: Connection = Depends(koneksi), _: Pengguna = TAMBAH) -> dict:
    """Atur baris seri item (tambah seri komponen, mis. TPK/KAMAR). Menghapus baris tidak menghapus nilai."""
    _terbuka(_putaran(conn, data.putaran_id))
    it = conn.execute(text("SELECT wilayah_kode, lapus_id, metode_kode FROM lk.item WHERE id = :i"),
                      {"i": item_id}).first()
    if it is None:
        raise tidak_ada("Item")
    _cek_tulis(conn, it.wilayah_kode.strip(), it.lapus_id)
    seri = _seri_bawaan(conn, it.metode_kode, data.seri)
    conn.execute(text("DELETE FROM lk.seri_item WHERE item_id = :i AND NOT (jenis_seri = ANY(:s))"),
                 {"i": item_id, "s": seri})
    for i, s in enumerate(seri, start=1):
        conn.execute(text("INSERT INTO lk.seri_item (item_id, jenis_seri, urutan) VALUES (:i, :s, :u)"
                          " ON CONFLICT (item_id, jenis_seri) DO UPDATE SET urutan = EXCLUDED.urutan"),
                     {"i": item_id, "s": s, "u": i})
    return {"pesan": "Baris seri diperbarui."}


class SatuanSeriIn(BaseModel):
    putaran_id: int
    satuan: str | None = Field(default=None, max_length=60)
    catatan: str | None = Field(default=None, max_length=500)


@router.patch("/data-dasar/item/{item_id}/seri/{seri}")
def ubah_meta_seri(item_id: int, seri: str, data: SatuanSeriIn, conn: Connection = Depends(koneksi),
                   _: Pengguna = ISI) -> dict:
    _terbuka(_putaran(conn, data.putaran_id))
    it = conn.execute(text("SELECT wilayah_kode, lapus_id FROM lk.item WHERE id = :i"), {"i": item_id}).first()
    if it is None:
        raise tidak_ada("Item")
    _cek_tulis(conn, it.wilayah_kode.strip(), it.lapus_id)
    f = data.model_fields_set - {"putaran_id"}
    conn.execute(text(
        "INSERT INTO lk.seri_item (item_id, jenis_seri, urutan, satuan, catatan) VALUES (:i, :s,"
        " (SELECT coalesce(max(urutan), 0) + 1 FROM lk.seri_item WHERE item_id = :i), :sat, :cat)"
        " ON CONFLICT (item_id, jenis_seri) DO UPDATE SET satuan = CASE WHEN :us THEN EXCLUDED.satuan ELSE"
        " lk.seri_item.satuan END, catatan = CASE WHEN :uc THEN EXCLUDED.catatan ELSE lk.seri_item.catatan END"),
        {"i": item_id, "s": seri, "sat": rapikan(data.satuan) or None, "cat": rapikan(data.catatan) or None,
         "us": "satuan" in f, "uc": "catatan" in f})
    return {"pesan": "Tersimpan."}


class TautanIn(BaseModel):
    putaran_id: int
    jenis_seri: str
    sumber: Literal["SERI_REFERENSI", "HASIL_LAPUS", "RUMUS"] | None = None
    rumus: str | None = None
    seri_id: int | None = None
    lapus_sumber_ids: list[int] | None = None
    besaran: Literal["OUT_CP", "OUT_K", "GVA_CP", "GVA_K", "IMPLISIT_OUT"] | None = None
    faktor: float = 1.0


@router.put("/data-dasar/item/{item_id}/tautan")
def atur_tautan(item_id: int, data: TautanIn, conn: Connection = Depends(koneksi), _: Pengguna = ISI) -> dict:
    """Tautkan seri item ke seri referensi, hasil lapus lain, atau rumus baku; sumber kosong = lepas tautan."""
    p = _putaran(conn, data.putaran_id)
    _terbuka(p)
    it = conn.execute(text("SELECT wilayah_kode, lapus_id, metode_kode FROM lk.item WHERE id = :i"
                           " AND tahun_dasar_id = :td"), {"i": item_id, "td": p["tahun_dasar_id"]}).first()
    if it is None:
        raise tidak_ada("Item")
    _cek_tulis(conn, it.wilayah_kode.strip(), it.lapus_id)
    if data.sumber is None:
        conn.execute(text("DELETE FROM lk.tautan_seri WHERE item_id = :i AND jenis_seri = :s"),
                     {"i": item_id, "s": data.jenis_seri})
    else:
        if data.sumber == "RUMUS":
            if data.rumus not in tt.SASARAN:
                raise tidak_valid("Rumus harus dipilih dari daftar baku.")
            met, sasaran = tt.SASARAN[data.rumus]
            if it.metode_kode != met or data.jenis_seri != sasaran:
                raise tidak_valid(f"Rumus {data.rumus} hanya untuk seri {sasaran} metode {met}.")
        if data.lapus_sumber_ids:
            ok = conn.execute(text("SELECT count(*) FROM ref.lapus WHERE id = ANY(:l) AND tahun_dasar_id = :td AND"
                                   " jenis IN ('daun','sub','kategori','kelompok','top','sop')"),
                              {"l": data.lapus_sumber_ids, "td": p["tahun_dasar_id"]}).scalar_one()
            if ok != len(set(data.lapus_sumber_ids)):
                raise tidak_valid("Lapus sumber tidak valid (baris total tidak boleh dipakai).")
        conn.execute(text(
            "INSERT INTO lk.tautan_seri (item_id, jenis_seri, sumber, rumus, seri_id, lapus_sumber_ids, besaran,"
            " faktor) VALUES (:i, :s, :src, :rm, :sid, :lap, :bes, :f) ON CONFLICT (item_id, jenis_seri) DO UPDATE"
            " SET sumber = EXCLUDED.sumber, rumus = EXCLUDED.rumus, seri_id = EXCLUDED.seri_id,"
            " lapus_sumber_ids = EXCLUDED.lapus_sumber_ids, besaran = EXCLUDED.besaran, faktor = EXCLUDED.faktor"),
            {"i": item_id, "s": data.jenis_seri, "src": data.sumber, "rm": data.rumus if data.sumber == "RUMUS"
             else None, "sid": data.seri_id if data.sumber == "SERI_REFERENSI" else None,
             "lap": data.lapus_sumber_ids or None, "bes": data.besaran if data.sumber == "HASIL_LAPUS" else None,
             "f": data.faktor})
    tandai_ubah(conn, data.putaran_id, [(it.wilayah_kode, it.lapus_id)], "ubah tautan seri")
    antrekan(conn, data.putaran_id, it.wilayah_kode.strip(), it.lapus_id, "ubah tautan seri")
    return {"pesan": "Tautan diperbarui."}


# ======================================================================== seri referensi
@router.get("/seri-referensi")
def daftar_seri_ref(putaran_id: int | None = None, wilayah: str | None = None, conn: Connection = Depends(koneksi),
                    _: Pengguna = Depends(pengguna_aktif)) -> dict:
    seri = [dict(r) for r in conn.execute(text(
        "SELECT s.id, s.kode, s.nama, s.jenis, s.satuan, s.keterangan, s.lapus_pemilik_id, l.kode AS lapus_pemilik,"
        " (SELECT count(*) FROM lk.tautan_seri t WHERE t.seri_id = s.id) AS jumlah_tautan,"
        " lk.boleh_tulis_seri_ref(s.lapus_pemilik_id, CAST(:w AS char(4))) AS boleh_tulis"
        " FROM lk.seri_referensi s LEFT JOIN ref.lapus l ON l.id = s.lapus_pemilik_id ORDER BY s.kode"),
        {"w": wilayah}).mappings()]
    nilai: dict[int, dict[str, float]] = defaultdict(dict)
    if putaran_id is not None and wilayah:
        for sid, u, x in conn.execute(text(
                "SELECT n.seri_id, pe.urut, n.nilai::float8 FROM lk.nilai_seri_referensi n JOIN ref.periode pe"
                " ON pe.id = n.periode_id WHERE n.putaran_id = :p AND n.wilayah_kode = :w"),
                {"p": putaran_id, "w": wilayah}):
            nilai[sid][str(u)] = x
    for s in seri:
        s["nilai"] = nilai.get(s["id"], {})
    out: dict[str, Any] = {"seri": seri}
    if putaran_id is not None:
        p = _putaran(conn, putaran_id)
        out["periode"] = [{"urut": u, "label": _label(u), "ubah": True}
                          for u in range(min(p["awal"], max(2019 * 4, p["tahun_awal_seri"] * 4)), p["akhir"] + 1)]
    return out


class SeriRefIn(BaseModel):
    kode: str = Field(pattern=r"^[A-Za-z0-9_.\-]{2,40}$")
    nama: str = Field(min_length=2, max_length=200)
    jenis: Literal["indeks_harga", "indeks_produksi", "indeks_nilai", "pdrb_td2010", "lainnya", "harga"]
    satuan: str | None = Field(default=None, max_length=60)
    keterangan: str | None = Field(default=None, max_length=500)
    lapus_pemilik_id: int | None = None


@router.post("/seri-referensi", status_code=201)
def tambah_seri_ref(data: SeriRefIn, conn: Connection = Depends(koneksi), _: Pengguna = ISI) -> dict:
    sid = conn.execute(text(
        "INSERT INTO lk.seri_referensi (kode, nama, jenis, satuan, keterangan, lapus_pemilik_id)"
        " VALUES (:k, :n, :j, :s, :ket, :l) RETURNING id"),
        {"k": data.kode.upper(), "n": rapikan(data.nama), "j": data.jenis, "s": rapikan(data.satuan) or None,
         "ket": rapikan(data.keterangan) or None, "l": data.lapus_pemilik_id}).scalar_one()
    return {"id": sid}


class SelRef(BaseModel):
    seri_id: int
    periode: int
    nilai: float | None = None


class SimpanRef(BaseModel):
    putaran_id: int
    wilayah: str = Field(min_length=4, max_length=4)
    perubahan: list[SelRef] = Field(min_length=1, max_length=5000)


@router.put("/seri-referensi/nilai")
def simpan_nilai_ref(data: SimpanRef, conn: Connection = Depends(koneksi), pengguna: Pengguna = ISI) -> dict:
    p = _putaran(conn, data.putaran_id)
    _terbuka(p)
    per = {int(r[0]): int(r[1]) for r in conn.execute(text("SELECT urut, id FROM ref.periode"))}
    for s in data.perubahan:
        if s.periode not in per:
            raise tidak_valid("Periode tidak dikenal.")
        q = {"p": data.putaran_id, "s": s.seri_id, "w": data.wilayah, "per": per[s.periode], "v": s.nilai,
             "u": pengguna.id}
        if s.nilai is None:
            conn.execute(text("DELETE FROM lk.nilai_seri_referensi WHERE putaran_id = :p AND seri_id = :s"
                              " AND wilayah_kode = :w AND periode_id = :per"), q)
        else:
            conn.execute(text(
                "INSERT INTO lk.nilai_seri_referensi (putaran_id, seri_id, wilayah_kode, periode_id, nilai,"
                " diubah_oleh) VALUES (:p, :s, :w, :per, :v, :u) ON CONFLICT (putaran_id, seri_id, wilayah_kode,"
                " periode_id) DO UPDATE SET nilai = EXCLUDED.nilai, diubah_oleh = EXCLUDED.diubah_oleh,"
                " diubah_pada = now()"), q)
    antrekan(conn, data.putaran_id, data.wilayah, None, "ubah seri referensi")
    return {"disimpan": len(data.perubahan), "pesan": "Seri referensi tersimpan. Item tertaut dihitung ulang."}


# ======================================================================== hitung & validasi
class HitungIn(BaseModel):
    putaran_id: int
    wilayah: str = Field(min_length=4, max_length=4)


@router.post("/hitung")
def minta_hitung(data: HitungIn, conn: Connection = Depends(koneksi), _: Pengguna = BACA) -> dict:
    _terbuka(_putaran(conn, data.putaran_id))
    jid = antrekan(conn, data.putaran_id, data.wilayah, None, "diminta pengguna")
    return {"job_id": jid, "pesan": "Hitung ulang dijadwalkan."}


@router.get("/hitung/status")
def status_hitung(putaran_id: int, wilayah: str, conn: Connection = Depends(koneksi), _: Pengguna = BACA) -> dict:
    return _status_antrean(conn, putaran_id, wilayah)


@router.get("/validasi")
def daftar_validasi(putaran_id: int, wilayah: str, lapus_id: int | None = None,
                    tingkat: str | None = Query(default=None), conn: Connection = Depends(koneksi),
                    _: Pengguna = BACA) -> list[dict]:
    return [dict(r) for r in conn.execute(text(
        "SELECT h.kode_validasi AS kode, v.nama, h.tingkat, h.lapus_id, l.kode AS kode_lapus, h.item_id, h.jenis_seri,"
        " pe.urut AS periode, h.pesan, h.kunci, h.dikonfirmasi_oleh IS NOT NULL AS dikonfirmasi, h.alasan_konfirmasi,"
        " coalesce((v.parameter->>'boleh_konfirmasi')::boolean, false) AS boleh_konfirmasi"
        " FROM lk.hasil_validasi h JOIN ref.validasi v ON v.kode = h.kode_validasi"
        " JOIN ref.lapus l ON l.id = h.lapus_id"
        " LEFT JOIN ref.periode pe ON pe.id = h.periode_id WHERE h.putaran_id = :p AND h.wilayah_kode = :w"
        " AND (CAST(:l AS int) IS NULL OR h.lapus_id = :l OR h.lapus_id IN (SELECT id FROM ref.lapus"
        "  WHERE induk_id = :l OR induk_id IN (SELECT id FROM ref.lapus WHERE induk_id = :l)))"
        " AND (CAST(:t AS text) IS NULL OR h.tingkat = :t) ORDER BY l.urutan, h.kode_validasi, h.id"),
        {"p": putaran_id, "w": wilayah, "l": lapus_id, "t": tingkat}).mappings()]


class KonfirmasiIn(BaseModel):
    putaran_id: int
    wilayah: str = Field(min_length=4, max_length=4)
    lapus_id: int
    kode: str
    kunci: str = Field(min_length=1, max_length=200)
    alasan: str = Field(min_length=10, max_length=500)


@router.post("/validasi/konfirmasi")
def konfirmasi(data: KonfirmasiIn, conn: Connection = Depends(koneksi), pengguna: Pengguna = ISI) -> dict:
    """Konfirmasi beralasan atas temuan yang boleh dikonfirmasi (V05); bertahan setelah hitung ulang."""
    _terbuka(_putaran(conn, data.putaran_id))
    boleh = conn.execute(text("SELECT coalesce((parameter->>'boleh_konfirmasi')::boolean, false) FROM ref.validasi"
                              " WHERE kode = :k"), {"k": data.kode}).scalar()
    if not boleh:
        raise tidak_valid("Temuan ini tidak dapat dikonfirmasi; perbaiki datanya.")
    ada = conn.execute(text("SELECT 1 FROM lk.hasil_validasi WHERE putaran_id = :p AND wilayah_kode = :w"
                            " AND lapus_id = :l AND kode_validasi = :k AND kunci = :kc LIMIT 1"),
                       {"p": data.putaran_id, "w": data.wilayah, "l": data.lapus_id, "k": data.kode,
                        "kc": data.kunci}).first()
    if ada is None:
        raise tidak_ada("Temuan validasi")
    q = {"p": data.putaran_id, "w": data.wilayah, "l": data.lapus_id, "k": data.kode, "kc": data.kunci,
         "a": rapikan(data.alasan), "u": pengguna.id}
    conn.execute(text(
        "INSERT INTO lk.konfirmasi_validasi (putaran_id, wilayah_kode, lapus_id, kode_validasi, kunci, alasan,"
        " dikonfirmasi_oleh) VALUES (:p, :w, :l, :k, :kc, :a, :u) ON CONFLICT (putaran_id, wilayah_kode, lapus_id,"
        " kode_validasi, kunci) DO UPDATE SET alasan = EXCLUDED.alasan, dikonfirmasi_oleh = EXCLUDED.dikonfirmasi_oleh,"
        " dikonfirmasi_pada = now()"), q)
    conn.execute(text("UPDATE lk.hasil_validasi SET dikonfirmasi_oleh = :u, alasan_konfirmasi = :a"
                      " WHERE putaran_id = :p AND wilayah_kode = :w AND lapus_id = :l AND kode_validasi = :k"
                      " AND kunci = :kc"), q)
    return {"pesan": "Temuan dikonfirmasi."}


@router.get("/validasi/kunci")
def validasi_kunci(putaran_id: int, wilayah: str, conn: Connection = Depends(koneksi), _: Pengguna = BACA) -> dict:
    """Temuan yang memblokir kunci putaran (V13, V14, V15) untuk satu wilayah (dipakai alur kunci F4)."""
    return validasi_db.ringkasan_kunci(conn, putaran_id, wilayah)


@router.get("/validasi/aturan")
def aturan(conn: Connection = Depends(koneksi), _: Pengguna = Depends(pengguna_aktif)) -> list[dict]:
    return [dict(r) for r in conn.execute(text(
        "SELECT kode, nama, tingkat, parameter, aktif FROM ref.validasi ORDER BY kode")).mappings()]


class AturanUbah(BaseModel):
    tingkat: Literal["info", "peringatan", "blokir_ajukan", "blokir_kunci"] | None = None
    parameter: dict[str, Any] | None = None
    aktif: bool | None = None


@router.patch("/validasi/aturan/{kode}")
def ubah_aturan(kode: str, data: AturanUbah, conn: Connection = Depends(koneksi), _: Pengguna = KELOLA) -> dict:
    """Admin: tingkat, aktif, dan parameter (mis. ambang V08 per lapus "TD2025:A.3", kalibrasi "p95")."""
    import json

    f = data.model_fields_set
    r = conn.execute(text(
        "UPDATE ref.validasi SET tingkat = CASE WHEN :ut THEN :t ELSE tingkat END,"
        " parameter = CASE WHEN :up THEN CAST(:p AS jsonb) ELSE parameter END,"
        " aktif = CASE WHEN :ua THEN :a ELSE aktif END WHERE kode = :k RETURNING kode"),
        {"ut": "tingkat" in f and data.tingkat is not None, "t": data.tingkat, "up": "parameter" in f
         and data.parameter is not None, "p": json.dumps(data.parameter or {}), "ua": "aktif" in f
         and data.aktif is not None, "a": data.aktif, "k": kode}).first()
    if r is None:
        raise tidak_ada("Aturan validasi")
    return {"pesan": "Aturan validasi diperbarui; berlaku pada hitung berikutnya."}
