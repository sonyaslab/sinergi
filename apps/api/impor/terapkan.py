"""Rencana impor (pratinjau selisih) dan penerapannya ke basis data (docs/05 §3).

Alur: berkas (templat/CSV) -> `rencanakan()` membandingkan dengan isi DB putaran -> pratinjau (jumlah item baru/berubah,
sel lama -> baru, pesan) -> `terapkan()` dalam satu transaksi (RLS + audit berlaku) -> antrean hitung per wilayah.

Aturan:
- Sel kosong pada berkas tidak menghapus nilai di sistem, kecuali opsi `kosongkan` (khusus admin, izin
  data.tulis_semua) dicentang.
- Baris lapus/wilayah yang tidak ditugaskan kepada pengimpor dilewati dengan pesan; putaran terkunci menolak seluruh
  impor (423).
- Item baru: berlaku mulai triwulan pertama yang berisi angka; alasan "impor templat <berkas>".
- Tautan "ikut item lain" (mis. "Ikut IH item C201", "Harga mengikuti item Sapi") diubah menjadi seri referensi
  bersama REF_<SERI>_<LAPUS>_<METODE><NO> milik lapus sumber; item sumber dan pengikut ditautkan ke seri itu
  (keputusan 5).
- TD tanpa jangkar_dari_data (TD2010): baris IH bersatuan "2010=100" yang jangkarnya kosong diberi IH_TD = 100
  (keputusan 3), kecuali parameter sudah ada.
- Penyesuaian dari berkas berstatus draf; pemegang izin penyesuaian.putus boleh memilih `setujui_penyesuaian`
  (keputusan 15). Nilai penyesuaian yang berubah kembali menjadi draf.
Pesan dan audit tidak memuat angka.
"""
from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import Connection, text

from ..app.galat import GalatSinergi
from ..putaran.status import tandai_ubah
from ..worker.antrean import antrekan
from . import tautan as tt
from .templat import JANGKAR, Berkas, ItemBerkas, Kunci, Pesan, label_periode

MAKS_RINCIAN = 2000  # sel berubah yang dikirim ke layar pratinjau


@dataclass
class Opsi:
    kosongkan: bool = False  # sel kosong di berkas menghapus nilai sistem (admin)
    setujui_penyesuaian: bool = False  # penyesuaian berkas langsung disetujui (izin penyesuaian.putus)


@dataclass(frozen=True)
class TautanDB:
    sumber: str
    rumus: str | None = None
    seri_ref: str | None = None
    lapus: tuple[str, ...] = ()
    besaran: str | None = None
    faktor: float = 1.0


@dataclass
class Rencana:
    putaran_id: int
    tahun_dasar_id: int
    nama_berkas: str
    item_baru: list[dict] = field(default_factory=list)
    item_ubah: list[dict] = field(default_factory=list)
    seri_meta: list[dict] = field(default_factory=list)
    sel: list[dict] = field(default_factory=list)  # kunci, seri, u, lama, baru (None = hapus)
    parameter: list[dict] = field(default_factory=list)
    tautan: list[dict] = field(default_factory=list)  # kunci, seri, lama, baru (TautanDB | None)
    seri_ref_baru: list[dict] = field(default_factory=list)
    seri_ref_sel: list[dict] = field(default_factory=list)
    adj: list[dict] = field(default_factory=list)
    pesan: list[Pesan] = field(default_factory=list)
    wilayah: set[str] = field(default_factory=set)

    @property
    def galat(self) -> list[Pesan]:
        return [p for p in self.pesan if p.tingkat == "galat"]

    def ringkasan(self) -> dict[str, int]:
        sel_baru = sum(1 for s in self.sel if s["lama"] is None)
        sel_hapus = sum(1 for s in self.sel if s["baru"] is None)
        return {
            "item_baru": len(self.item_baru), "item_berubah": len(self.item_ubah),
            "sel_baru": sel_baru, "sel_berubah": len(self.sel) - sel_baru - sel_hapus, "sel_dihapus": sel_hapus,
            "parameter": len(self.parameter), "tautan": len(self.tautan), "metadata_seri": len(self.seri_meta),
            "seri_referensi_baru": len(self.seri_ref_baru), "sel_seri_referensi": len(self.seri_ref_sel),
            "penyesuaian": len(self.adj),
            "dilewati": sum(1 for p in self.pesan if p.kode == "DILEWATI"),
            "galat": len(self.galat), "peringatan": sum(1 for p in self.pesan if p.tingkat == "peringatan"),
        }

    def sidik(self) -> str:
        """Sidik isi rencana: terapkan ditolak bila data berubah sejak pratinjau."""
        isi = json.dumps([self.item_baru, self.item_ubah, self.seri_meta,
                          [[*s["kunci"], s["seri"], s["u"], s["lama"], s["baru"]] for s in self.sel],
                          self.parameter, [[*t["kunci"], t["seri"], str(t["baru"])] for t in self.tautan],
                          self.seri_ref_baru, self.seri_ref_sel, self.adj], sort_keys=True, default=str)
        return hashlib.sha256(isi.encode()).hexdigest()


def _kode_lapus_tanpa_titik(kode: str) -> str:
    return kode.replace(".", "").upper()


def kode_ref_ikut(seri: str, lapus: str, metode: str, nomor: int) -> str:
    return f"REF_{seri}_{_kode_lapus_tanpa_titik(lapus)}_{metode}{nomor:02d}"


JENIS_REF = {"IH": "indeks_harga", "HARGA": "harga", "INDEKS": "indeks_produksi"}
TOTAL = ("ntb", "top", "sop", "topsop", "pdrb", "pdrb_nonmigas")  # baris total tidak boleh jadi sumber tautan


# ======================================================================== muat isi DB
@dataclass
class IsiDB:
    td_kode: str
    jangkar_dari_data: bool
    klasifikasi: str
    status_putaran: str
    lapus_id: dict[str, int]
    lapus_jenis: dict[str, str]
    item: dict[Kunci, dict]
    seri_item: dict[int, dict[str, dict]]
    nilai: dict[tuple[int, str, int], tuple[float | None, str]]
    param: dict[tuple[int, str], float]
    tautan: dict[tuple[int, str], TautanDB]
    seri_ref: dict[str, dict]
    nilai_ref: dict[tuple[str, str, int], float]
    adj: dict[tuple, dict]
    periode_id: dict[int, int]
    satuan: dict[str, str]
    katalog: dict[str, int]
    padanan_lain: dict[str, list[int]]


def muat_isi(conn: Connection, putaran_id: int, wilayah: set[str]) -> IsiDB:
    pu = conn.execute(text(
        "SELECT p.tahun_dasar_id, p.status, t.kode, t.jangkar_dari_data, t.klasifikasi FROM lk.putaran p"
        " JOIN ref.tahun_dasar t ON t.id = p.tahun_dasar_id WHERE p.id = :p"), {"p": putaran_id}).first()
    if pu is None:
        raise GalatSinergi(404, "TIDAK_ADA", "Putaran tidak ditemukan.")
    q = {"p": putaran_id, "td": pu.tahun_dasar_id, "w": sorted(wilayah)}
    lap = conn.execute(text("SELECT id, kode, jenis FROM ref.lapus WHERE tahun_dasar_id = :td AND aktif"), q).all()
    kode_lapus = {r.id: r.kode for r in lap}
    item: dict[Kunci, dict] = {}
    for r in conn.execute(text(
            "SELECT i.id, i.wilayah_kode, i.lapus_id, i.metode_kode, i.nomor, i.nama, i.jenis_indeks, i.sumber_teks,"
            " i.padanan_teks, i.status FROM lk.item i WHERE i.tahun_dasar_id = :td AND i.wilayah_kode = ANY(:w)"),
            q).mappings():
        k: Kunci = (r["wilayah_kode"].strip(), kode_lapus.get(r["lapus_id"], f"#{r['lapus_id']}"), r["metode_kode"],
                    r["nomor"])
        item[k] = dict(r)
    ids = [x["id"] for x in item.values()]
    seri_item: dict[int, dict[str, dict]] = defaultdict(dict)
    for r in conn.execute(text("SELECT * FROM lk.seri_item WHERE item_id = ANY(:i)"), {"i": ids}).mappings():
        seri_item[r["item_id"]][r["jenis_seri"]] = dict(r)
    nilai = {(r[0], r[1], r[2]): (r[3], r[4]) for r in conn.execute(text(
        "SELECT n.item_id, n.jenis_seri, p.urut, n.nilai::float8, n.status_sel FROM lk.nilai_item n"
        " JOIN ref.periode p ON p.id = n.periode_id WHERE n.putaran_id = :p AND n.item_id = ANY(:i)"),
        {"p": putaran_id, "i": ids})}
    param = {(r[0], r[1]): r[2] for r in conn.execute(text(
        "SELECT item_id, kode, nilai::float8 FROM lk.parameter_item WHERE putaran_id = :p AND item_id = ANY(:i)"),
        {"p": putaran_id, "i": ids})}
    tautan = {(r.item_id, r.jenis_seri): TautanDB(
        r.sumber, r.rumus, r.kode_ref, tuple(kode_lapus.get(x, f"#{x}") for x in (r.lapus_sumber_ids or ())),
        r.besaran, float(r.faktor)) for r in conn.execute(text(
            "SELECT t.*, s.kode AS kode_ref FROM lk.tautan_seri t LEFT JOIN lk.seri_referensi s ON s.id = t.seri_id"
            " WHERE t.item_id = ANY(:i)"), {"i": ids})}
    seri_ref = {r["kode"]: dict(r) for r in conn.execute(text("SELECT * FROM lk.seri_referensi")).mappings()}
    nilai_ref = {(r[0], r[1].strip(), r[2]): r[3] for r in conn.execute(text(
        "SELECT s.kode, n.wilayah_kode, p.urut, n.nilai::float8 FROM lk.nilai_seri_referensi n"
        " JOIN lk.seri_referensi s ON s.id = n.seri_id JOIN ref.periode p ON p.id = n.periode_id"
        " WHERE n.putaran_id = :p AND n.wilayah_kode = ANY(:w)"), q)}
    adj = {}
    for r in conn.execute(text(
            "SELECT a.id, a.wilayah_kode, l.kode AS lapus, a.tahap, a.metode_kode, a.jenis_kode, a.harga, p.urut,"
            " a.nilai::float8 AS nilai, a.alasan, a.status FROM lk.penyesuaian a JOIN ref.lapus l ON l.id = a.lapus_id"
            " JOIN ref.periode p ON p.id = a.periode_id WHERE a.putaran_id = :p AND a.wilayah_kode = ANY(:w)"),
            q).mappings():
        adj[(r["wilayah_kode"].strip(), r["lapus"], r["tahap"], r["metode_kode"], r["jenis_kode"], r["harga"],
             r["urut"])] = dict(r)
    periode = {int(r[0]): int(r[1]) for r in conn.execute(text("SELECT urut, id FROM ref.periode"))}
    satuan = {r[0].lower(): r[0] for r in conn.execute(text("SELECT kode FROM ref.satuan WHERE aktif"))}
    katalog: dict[str, int] = {}
    for kt in conn.execute(text("SELECT id, nama_baku, sinonim FROM ref.katalog_komoditas WHERE aktif")):
        for nm in [kt.nama_baku, *(kt.sinonim or [])]:
            katalog.setdefault(nm.lower(), kt.id)
    padanan_lain: dict[str, list[int]] = defaultdict(list)
    for pl in conn.execute(text("SELECT id, kode FROM ref.lapus WHERE tahun_dasar_id <> :td AND aktif"
                                " AND jenis IN ('daun','sub','kategori','top','sop')"), q):
        padanan_lain[pl.kode].append(pl.id)
    return IsiDB(pu.kode, pu.jangkar_dari_data, pu.klasifikasi, pu.status, {r.kode: r.id for r in lap},
                 {r.kode: r.jenis for r in lap}, item, dict(seri_item), nilai, param, tautan, seri_ref, nilai_ref, adj,
                 periode, satuan, katalog, dict(padanan_lain))


# ======================================================================== izin
@dataclass
class Izin:
    tulis: set[tuple[str, str]]  # (wilayah, lapus) yang boleh ditulis
    seri_ref: dict[tuple[str | None, str], bool]  # (kode lapus pemilik | None, wilayah) -> boleh
    usul_adj: bool
    putus_adj: bool
    tulis_semua: bool


def muat_izin(conn: Connection, isi: IsiDB, pasangan: set[tuple[str, str]], pemilik: set[tuple[str | None, str]],
              izin_pengguna: frozenset[str]) -> Izin:
    tulis = {(w, lap) for w, lap in pasangan if lap in isi.lapus_id and conn.execute(
        text("SELECT lk.boleh_tulis(CAST(:w AS char(4)), :l)"), {"w": w, "l": isi.lapus_id[lap]}).scalar()}
    ref = {}
    for lap, w in pemilik:
        lid = isi.lapus_id.get(lap) if lap else None
        ref[(lap, w)] = bool(conn.execute(text("SELECT lk.boleh_tulis_seri_ref(:l, CAST(:w AS char(4)))"),
                                          {"l": lid, "w": w}).scalar())
    return Izin(tulis, ref, "penyesuaian.usul" in izin_pengguna or "penyesuaian.putus" in izin_pengguna,
                "penyesuaian.putus" in izin_pengguna, "data.tulis_semua" in izin_pengguna)


# ======================================================================== rencana
def _sama(a: float | None, b: float | None) -> bool:
    return a == b


def _tautan_berkas(it: ItemBerkas, rencana: Rencana) -> dict[str, TautanDB | None]:
    """Tautan yang diminta berkas per seri (None = seri manual). IKUT diselesaikan terpisah."""
    out: dict[str, TautanDB | None] = {}
    margin = [s for s in it.seri.values() if s.tautan is not None and s.tautan.jenis == "MARGIN"]
    for s in it.seri.values():
        t = s.tautan
        if t is None or t.jenis in ("KETERANGAN", "HITUNG_SISTEM", "MARGIN", "IKUT"):
            out.setdefault(s.kode, None)
            continue
        if t.jenis == "REF":
            out[s.kode] = TautanDB("SERI_REFERENSI", seri_ref=t.seri_ref, faktor=t.faktor)
        elif t.jenis == "HASIL":
            out[s.kode] = TautanDB("HASIL_LAPUS", lapus=t.lapus, besaran=t.besaran, faktor=t.faktor)
        elif t.jenis == "RUMUS":
            metode, sasaran = tt.SASARAN[t.rumus or ""]
            if it.metode != metode or s.kode != sasaran:
                rencana.pesan.append(Pesan("galat", f"Rumus {t.rumus} hanya untuk seri {sasaran} metode {metode}.",
                                           it.sheet, s.baris, "Tautan / Rumus"))
                continue
            out[s.kode] = TautanDB("RUMUS", rumus=t.rumus, faktor=t.faktor)
    if len(margin) > 1:
        rencana.pesan.append(Pesan("galat", "Satu item hanya boleh punya satu tautan MARGIN.", it.sheet, it.baris))
    elif margin:
        t = margin[0].tautan
        assert t is not None
        out["OUT_ADHB"] = TautanDB("RUMUS", rumus=t.rumus, lapus=t.lapus, faktor=t.faktor)
    else:
        for s in it.seri.values():
            if s.tautan is not None and s.tautan.jenis == "HITUNG_SISTEM":
                rencana.pesan.append(Pesan("galat", "Baris 'Dihitung sistem' tanpa tautan MARGIN pada item ini.",
                                           it.sheet, s.baris, "Tautan / Rumus"))
    return out


def _cari_sumber_ikut(berkas: Berkas, it: ItemBerkas, t: tt.TautanTeks) -> Kunci | str:
    """Kunci item sumber "ikut item lain" (harus ada di berkas yang sama); str = pesan galat."""
    cocok: list[Kunci] = []
    for k, sb in berkas.items.items():
        if k == it.kunci or k[0] != it.wilayah:
            continue
        if t.ikut_kode is not None:
            if f"{_kode_lapus_tanpa_titik(k[1])}{k[3]:02d}" == t.ikut_kode:
                cocok.append(k)
        elif k[1] == it.lapus and sb.nama.lower() == (t.ikut_nama or "").lower():
            cocok.append(k)
    if len(cocok) > 1:
        sama = [k for k in cocok if k[2] == it.metode]
        cocok = sama if len(sama) == 1 else cocok
    if len(cocok) != 1:
        rujukan = t.ikut_kode or t.ikut_nama
        return (f"Item sumber '{rujukan}' tidak ditemukan di berkas ini." if not cocok
                else f"Item sumber '{rujukan}' tidak unik; tautkan ke seri referensi secara manual.")
    return cocok[0]


def rencanakan(conn: Connection, berkas: Berkas, putaran_id: int, nama_berkas: str, izin_pengguna: frozenset[str],
               opsi: Opsi) -> Rencana:
    wil = {k[0] for k in berkas.items} | {r.wilayah for r in berkas.seri_ref} | {a.wilayah for a in berkas.penyesuaian}
    isi = muat_isi(conn, putaran_id, wil)
    if isi.status_putaran == "terkunci":
        raise GalatSinergi(423, "PUTARAN_TERKUNCI", "Putaran sudah dikunci. Impor ditolak seluruhnya.")
    td = conn.execute(text("SELECT tahun_dasar_id FROM lk.putaran WHERE id = :p"), {"p": putaran_id}).scalar_one()
    r = Rencana(putaran_id, td, nama_berkas, pesan=list(berkas.pesan), wilayah=set())
    alasan = f"impor templat {nama_berkas}"[:200]

    # ---- ikut item lain -> seri referensi (keputusan 5)
    ikut: dict[tuple[Kunci, str], str] = {}  # (kunci item, seri) -> kode ref
    ref_ikut: dict[str, dict] = {}  # kode -> {sumber: kunci, seri, ...}
    for it in berkas.items.values():
        for s in it.seri.values():
            t = s.tautan
            if t is None or t.jenis != "IKUT":
                continue
            src = _cari_sumber_ikut(berkas, it, t)
            seri = t.ikut_seri or s.kode
            if isinstance(src, str):
                r.pesan.append(Pesan("galat", src, it.sheet, s.baris, "Tautan / Rumus"))
                continue
            sb = berkas.items[src]  # src: Kunci
            s_src = sb.seri.get(seri)
            if s_src is None:
                r.pesan.append(Pesan("galat", f"Item sumber tidak punya seri {seri}.", it.sheet, s.baris,
                                     "Tautan / Rumus"))
                continue
            if s_src.tautan is not None and s_src.tautan.jenis == "REF":
                kode = s_src.tautan.seri_ref or ""
            elif s_src.tautan is not None and s_src.tautan.nilai_diabaikan:
                r.pesan.append(Pesan("galat", "Seri item sumber dihitung dengan rumus/tautan; tautkan manual.",
                                     it.sheet, s.baris, "Tautan / Rumus"))
                continue
            else:
                kode = kode_ref_ikut(seri, src[1], src[2], src[3])
                ref_ikut.setdefault(kode, {"sumber": src, "seri": seri, "satuan": s_src.satuan,
                                           "nama": f"{seri} {sb.nama} ({src[1]} {src[2]} {src[3]})"[:200]})
                ikut[(src, seri)] = kode
            ikut[(it.kunci, s.kode)] = kode

    # ---- izin per (wilayah, lapus) dan seri referensi
    pasangan = {(k[0], k[1]) for k in berkas.items} | {(a.wilayah, a.lapus) for a in berkas.penyesuaian}
    pemilik: set[tuple[str | None, str]] = set()
    for sr in berkas.seri_ref:
        ada = isi.seri_ref.get(sr.kode)
        pemilik.add((_kode_pemilik(isi, ada) if ada else None, sr.wilayah))
    for kode, x in ref_ikut.items():
        ada = isi.seri_ref.get(kode)
        pemilik.add((x["sumber"][1] if not ada else _kode_pemilik(isi, ada), x["sumber"][0]))
    izin = muat_izin(conn, isi, pasangan, pemilik, izin_pengguna)
    if opsi.kosongkan and not izin.tulis_semua:
        raise GalatSinergi(403, "TIDAK_BERHAK", "Opsi kosongkan sel hanya untuk admin.")
    if opsi.setujui_penyesuaian and not izin.putus_adj:
        raise GalatSinergi(403, "TIDAK_BERHAK", "Opsi setujui penyesuaian butuh izin memutus penyesuaian.")

    # ---- seri referensi: definisi & nilai
    ref_dikenal = set(isi.seri_ref)
    for kode, x in ref_ikut.items():
        if kode not in isi.seri_ref:
            if not izin.seri_ref.get((x["sumber"][1], x["sumber"][0])):
                r.pesan.append(Pesan("galat", f"Anda tidak berhak membuat seri referensi {kode}.", kode="DILEWATI"))
                continue
            r.seri_ref_baru.append({"kode": kode, "nama": x["nama"], "jenis": JENIS_REF.get(x["seri"], "lainnya"),
                                    "satuan": x["satuan"], "pemilik": x["sumber"][1],
                                    "keterangan": "Dibuat otomatis dari tautan 'ikut item lain' (keputusan 5)"})
        ref_dikenal.add(kode)
    for sr in berkas.seri_ref:
        ada = isi.seri_ref.get(sr.kode)
        boleh = izin.seri_ref.get((_kode_pemilik(isi, ada) if ada else None, sr.wilayah), False)
        if not boleh:
            r.pesan.append(Pesan("peringatan", f"Seri referensi {sr.kode} hanya dapat diubah admin/lapus pemilik;"
                                 " baris dilewati.", "SERI_REFERENSI", sr.baris, kode="DILEWATI"))
            continue
        if ada is None and sr.kode not in {b["kode"] for b in r.seri_ref_baru}:
            jenis = "harga" if sr.satuan and "rp" in sr.satuan.lower() else "indeks_harga"
            r.seri_ref_baru.append({"kode": sr.kode, "nama": sr.nama or sr.kode, "jenis": jenis, "satuan": sr.satuan,
                                    "pemilik": None, "keterangan": sr.sumber})
        ref_dikenal.add(sr.kode)
        _sel_ref(r, isi, sr.kode, sr.wilayah, sr.nilai, berkas.periode, opsi)
        r.wilayah.add(sr.wilayah)
    for kode, x in ref_ikut.items():
        sk: Kunci = x["sumber"]
        if (sk[0], sk[1]) not in izin.tulis or kode not in ref_dikenal:
            continue
        _sel_ref(r, isi, kode, sk[0], berkas.items[sk].seri[x["seri"]].nilai, berkas.periode, opsi)
        r.wilayah.add(sk[0])

    # ---- item, seri, nilai, parameter, tautan
    for it in berkas.items.values():
        if (it.wilayah, it.lapus) not in izin.tulis:
            r.pesan.append(Pesan("peringatan", f"Lapus {it.lapus} wilayah {it.wilayah} tidak ditugaskan kepada Anda;"
                                 " item dilewati.", it.sheet, it.baris, kode="DILEWATI"))
            continue
        db = isi.item.get(it.kunci)
        iid = db["id"] if db else None
        r.wilayah.add(it.wilayah)
        if db is None:
            semua = [u for s in it.seri.values() for u in s.nilai]
            satuan = next((isi.satuan[s.satuan.lower()] for s in it.seri.values()
                           if s.satuan and s.satuan.lower() in isi.satuan), None)
            pad_id = None
            if it.padanan and isi.klasifikasi == "KBLI2020" and len(isi.padanan_lain.get(it.padanan, [])) == 1:
                pad_id = isi.padanan_lain[it.padanan][0]
            r.item_baru.append({"kunci": list(it.kunci), "nama": it.nama, "jenis_indeks": it.jenis_indeks,
                                "sumber": it.sumber, "padanan": it.padanan, "padanan_id": pad_id,
                                "satuan": satuan, "katalog_id": isi.katalog.get(it.nama.lower()),
                                "mulai": min(semua) if semua else None, "alasan": alasan})
        else:
            ubah = {}
            for kol, baru in (("nama", it.nama), ("jenis_indeks", it.jenis_indeks), ("sumber_teks", it.sumber),
                              ("padanan_teks", it.padanan)):
                if baru is not None and (db[kol] or None) != baru:
                    ubah[kol] = baru
            if ubah:
                r.item_ubah.append({"kunci": list(it.kunci), "id": iid, "ubah": ubah})
        meta_db = isi.seri_item.get(iid, {}) if iid else {}
        for s in it.seri.values():
            teks_t = f"REF: {ikut[(it.kunci, s.kode)]}" if (it.kunci, s.kode) in ikut else s.teks_tautan
            m = {"urutan": s.urutan, "satuan": s.satuan, "label": s.label, "catatan": s.catatan,
                 "lokasi_sumber": s.lokasi, "teks_tautan": teks_t}
            lama = meta_db.get(s.kode)
            if lama is None or any((lama.get(k) or None) != (v or None) for k, v in m.items() if k != "urutan") or \
                    lama.get("urutan") != s.urutan:
                r.seri_meta.append({"kunci": list(it.kunci), "seri": s.kode, **m})
            if lama is not None and s.satuan and lama.get("satuan") and lama["satuan"].lower() != s.satuan.lower():
                r.pesan.append(Pesan("peringatan", f"Satuan seri {s.kode} berbeda dengan satuan tersimpan.",
                                     it.sheet, s.baris, "Satuan", "V16"))
        # tautan
        minta = _tautan_berkas(it, r)
        for (k, seri), kode in ikut.items():
            if k == it.kunci:
                minta[seri] = TautanDB("SERI_REFERENSI", seri_ref=kode)
        for seri, baru_t in minta.items():
            baris = it.seri[seri].baris if seri in it.seri else it.baris
            if baru_t is not None:
                salah = [x for x in baru_t.lapus if x not in isi.lapus_id or isi.lapus_jenis[x] in TOTAL]
                if salah:
                    r.pesan.append(Pesan("galat", f"Lapus sumber {', '.join(salah)} tidak valid untuk tautan.",
                                         it.sheet, baris, "Tautan / Rumus"))
                    continue
                if baru_t.sumber == "SERI_REFERENSI" and baru_t.seri_ref not in ref_dikenal:
                    r.pesan.append(Pesan("galat", f"Seri referensi {baru_t.seri_ref} belum ada (isi sheet "
                                         "SERI_REFERENSI atau buat di menu Seri Referensi).", it.sheet, baris,
                                         "Tautan / Rumus"))
                    continue
            lama_t = isi.tautan.get((iid, seri)) if iid else None
            if lama_t != baru_t:
                r.tautan.append({"kunci": list(it.kunci), "seri": seri, "lama": lama_t, "baru": baru_t})
        tertaut = {seri for seri, t in minta.items() if t is not None}
        # nilai & jangkar
        for s in it.seri.values():
            if s.kode not in tertaut:
                for u in sorted(set(s.nilai) | (set(berkas.periode) if opsi.kosongkan else set())):
                    baru_v = s.nilai.get(u)
                    lama_v = isi.nilai.get((iid, s.kode, u)) if iid else None
                    lama_n = lama_v[0] if lama_v else None
                    if baru_v is None and lama_v is None:
                        continue
                    if lama_v is not None and lama_v[1] == "isi" and _sama(lama_n, baru_v):
                        continue
                    if baru_v is None and lama_v is not None and lama_v[1] != "isi":
                        continue
                    r.sel.append({"kunci": list(it.kunci), "seri": s.kode, "u": u, "lama": lama_n, "baru": baru_v})
            kode_p = JANGKAR.get(s.kode)
            if kode_p is None:
                continue
            jangkar = s.jangkar
            lama_p = isi.param.get((iid, kode_p)) if iid else None
            if (jangkar is None and kode_p == "IH_TD" and not isi.jangkar_dari_data and lama_p is None
                    and s.satuan and "2010=100" in s.satuan.replace(" ", "")):
                jangkar = 100.0
                al = "IH tahun dasar 2010=100 (keputusan 3)"
            else:
                al = alasan
            if jangkar is not None and lama_p != jangkar:
                r.parameter.append({"kunci": list(it.kunci), "kode": kode_p, "lama": lama_p, "baru": jangkar,
                                    "alasan": al})
            elif jangkar is None and opsi.kosongkan and lama_p is not None:
                r.parameter.append({"kunci": list(it.kunci), "kode": kode_p, "lama": lama_p, "baru": None,
                                    "alasan": alasan})

    # ---- penyesuaian
    status_baru = "disetujui" if opsi.setujui_penyesuaian else "draf"
    for a in berkas.penyesuaian:
        if (a.wilayah, a.lapus) not in izin.tulis and not izin.putus_adj:
            r.pesan.append(Pesan("peringatan", f"Penyesuaian lapus {a.lapus} wilayah {a.wilayah} tidak ditugaskan;"
                                 " baris dilewati.", "PENYESUAIAN", a.baris, kode="DILEWATI"))
            continue
        if not izin.usul_adj:
            r.pesan.append(Pesan("peringatan", "Anda tidak berhak mengusulkan penyesuaian; baris dilewati.",
                                 "PENYESUAIAN", a.baris, kode="DILEWATI"))
            continue
        r.wilayah.add(a.wilayah)
        for u in sorted(set(a.nilai) | (set(berkas.periode) if opsi.kosongkan else set())):
            ka = (a.wilayah, a.lapus, a.tahap, a.metode, a.jenis, a.harga, u)
            la = isi.adj.get(ka)
            ba = a.nilai.get(u)
            if ba is None:
                if la is not None:
                    r.adj.append({"kunci": list(ka), "id": la["id"], "lama": la["nilai"], "baru": None})
                continue
            if la is not None and la["nilai"] == ba:
                st = la["status"]
                if (opsi.setujui_penyesuaian and st != "disetujui") or (a.alasan or None) != (la["alasan"] or None):
                    r.adj.append({"kunci": list(ka), "id": la["id"], "lama": la["nilai"], "baru": ba,
                                  "alasan": a.alasan, "status": status_baru if opsi.setujui_penyesuaian else st})
                continue
            r.adj.append({"kunci": list(ka), "id": la["id"] if la else None, "lama": la["nilai"] if la else None,
                          "baru": ba, "alasan": a.alasan, "status": status_baru})
    return r


def _kode_pemilik(isi: IsiDB, seri: dict) -> str | None:
    pid = seri.get("lapus_pemilik_id")
    if pid is None:
        return None
    return next((k for k, v in isi.lapus_id.items() if v == pid), f"#{pid}")


def _sel_ref(r: Rencana, isi: IsiDB, kode: str, wilayah: str, nilai: dict[int, float], periode: list[int],
             opsi: Opsi) -> None:
    for u in sorted(set(nilai) | (set(periode) if opsi.kosongkan else set())):
        baru = nilai.get(u)
        lama = isi.nilai_ref.get((kode, wilayah, u))
        if baru == lama:
            continue
        if baru is None and lama is None:
            continue
        r.seri_ref_sel.append({"kode": kode, "wilayah": wilayah, "u": u, "lama": lama, "baru": baru})


# ======================================================================== pratinjau (untuk layar)
def pratinjau_json(r: Rencana) -> dict[str, Any]:
    sel = [{"wilayah": s["kunci"][0], "lapus": s["kunci"][1], "metode": s["kunci"][2], "no": s["kunci"][3],
            "seri": s["seri"], "periode": label_periode(s["u"]), "lama": s["lama"], "baru": s["baru"]}
           for s in r.sel[:MAKS_RINCIAN]]
    return {
        "ringkasan": r.ringkasan(),
        "item_baru": [{"wilayah": i["kunci"][0], "lapus": i["kunci"][1], "metode": i["kunci"][2],
                       "no": i["kunci"][3], "nama": i["nama"]} for i in r.item_baru[:MAKS_RINCIAN]],
        "item_berubah": [{"wilayah": i["kunci"][0], "lapus": i["kunci"][1], "metode": i["kunci"][2],
                          "no": i["kunci"][3], "kolom": sorted(i["ubah"])} for i in r.item_ubah[:MAKS_RINCIAN]],
        "sel": sel,
        "sel_terpotong": len(r.sel) > MAKS_RINCIAN,
        "parameter": [{"wilayah": p["kunci"][0], "lapus": p["kunci"][1], "metode": p["kunci"][2],
                       "no": p["kunci"][3], "kode": p["kode"], "lama": p["lama"], "baru": p["baru"]}
                      for p in r.parameter[:MAKS_RINCIAN]],
        "tautan": [{"wilayah": t["kunci"][0], "lapus": t["kunci"][1], "metode": t["kunci"][2], "no": t["kunci"][3],
                    "seri": t["seri"], "lama": _uraian_tautan(t["lama"]), "baru": _uraian_tautan(t["baru"])}
                   for t in r.tautan[:MAKS_RINCIAN]],
        "seri_referensi_baru": [{"kode": x["kode"], "nama": x["nama"], "jenis": x["jenis"]} for x in r.seri_ref_baru],
        "penyesuaian": [{"wilayah": a["kunci"][0], "lapus": a["kunci"][1], "tahap": a["kunci"][2],
                         "metode": a["kunci"][3], "jenis": a["kunci"][4], "harga": a["kunci"][5],
                         "periode": label_periode(a["kunci"][6]), "lama": a["lama"], "baru": a["baru"],
                         "status": a.get("status")} for a in r.adj[:MAKS_RINCIAN]],
        "pesan": [p.ke_dict() for p in r.pesan[:MAKS_RINCIAN]],
        "jumlah_pesan": len(r.pesan),
    }


def _uraian_tautan(t: TautanDB | None) -> str | None:
    if t is None:
        return None
    return tt.teks_kanonik(t.sumber, t.rumus, t.seri_ref, t.lapus, t.besaran, t.faktor)


def pesan_audit(r: Rencana) -> dict[str, Any]:
    """Isi audit.impor_berkas.pesan: ringkasan dan pesan (tanpa angka sel)."""
    return {"ringkasan": r.ringkasan(), "sidik_rencana": r.sidik(),
            "pesan": [p.ke_dict() for p in r.pesan[:500]], "jumlah_pesan": len(r.pesan)}


# ======================================================================== terapkan
def terapkan(conn: Connection, r: Rencana, uid: int) -> dict[str, int]:
    """Tulis rencana dalam transaksi berjalan (RLS dan audit aktif). Galat format memblokir seluruh impor."""
    if r.galat:
        raise GalatSinergi(422, "IMPOR_GALAT", "Berkas masih memiliki galat format. Perbaiki lalu unggah ulang.")
    td, p = r.tahun_dasar_id, r.putaran_id
    lapus_id = {str(x[0]): int(x[1]) for x in conn.execute(
        text("SELECT kode, id FROM ref.lapus WHERE tahun_dasar_id = :td"), {"td": td})}
    periode = {int(x[0]): int(x[1]) for x in conn.execute(text("SELECT urut, id FROM ref.periode"))}
    ref_id = {str(x[0]): int(x[1]) for x in conn.execute(text("SELECT kode, id FROM lk.seri_referensi"))}
    for x in r.seri_ref_baru:
        ref_id[x["kode"]] = conn.execute(text(
            "INSERT INTO lk.seri_referensi (kode, nama, jenis, satuan, keterangan, lapus_pemilik_id)"
            " VALUES (:k, :n, :j, :s, :ket, :l) RETURNING id"),
            {"k": x["kode"], "n": x["nama"], "j": x["jenis"], "s": x["satuan"], "ket": x.get("keterangan"),
             "l": lapus_id.get(x["pemilik"]) if x["pemilik"] else None}).scalar_one()

    item_id: dict[tuple, int] = {}
    for k_w, k_l, k_m, k_n, iid in conn.execute(text(
            "SELECT i.wilayah_kode, l.kode, i.metode_kode, i.nomor, i.id FROM lk.item i JOIN ref.lapus l"
            " ON l.id = i.lapus_id WHERE i.tahun_dasar_id = :td AND i.wilayah_kode = ANY(:w)"),
            {"td": td, "w": sorted(r.wilayah)}):
        item_id[(k_w.strip(), k_l, k_m, k_n)] = iid
    for x in r.item_baru:
        w, lap, met, no = x["kunci"]
        item_id[(w, lap, met, no)] = conn.execute(text(
            "INSERT INTO lk.item (tahun_dasar_id, wilayah_kode, lapus_id, metode_kode, nomor, katalog_id, nama,"
            " satuan_kode, sumber_teks, jenis_indeks, periode_mulai_id, lapus_padanan_id, padanan_teks,"
            " dibuat_putaran_id, dibuat_oleh, alasan) VALUES (:td, :w, :l, :m, :n, :kat, :nama, :sat, :sum, :ji,"
            " :mulai, :pad, :padt, :p, :u, :al) RETURNING id"),
            {"td": td, "w": w, "l": lapus_id[lap], "m": met, "n": no, "kat": x["katalog_id"], "nama": x["nama"],
             "sat": x["satuan"], "sum": x["sumber"], "ji": x["jenis_indeks"],
             "mulai": periode.get(x["mulai"]) if x["mulai"] is not None else None, "pad": x["padanan_id"],
             "padt": x["padanan"], "p": p, "u": uid, "al": x["alasan"]}).scalar_one()
    for x in r.item_ubah:
        sets = ", ".join(f"{k} = :{k}" for k in x["ubah"])
        conn.execute(text(f"UPDATE lk.item SET {sets} WHERE id = :id"), {**x["ubah"], "id": x["id"]})

    def id_item(k: list) -> int:
        return item_id[tuple(k)]

    if r.seri_meta:
        conn.execute(text(
            "INSERT INTO lk.seri_item (item_id, jenis_seri, urutan, satuan, label, catatan, lokasi_sumber, teks_tautan)"
            " VALUES (:i, :s, :urutan, :satuan, :label, :catatan, :lokasi_sumber, :teks_tautan)"
            " ON CONFLICT (item_id, jenis_seri) DO UPDATE SET urutan = EXCLUDED.urutan, satuan = EXCLUDED.satuan,"
            " label = EXCLUDED.label, catatan = EXCLUDED.catatan, lokasi_sumber = EXCLUDED.lokasi_sumber,"
            " teks_tautan = EXCLUDED.teks_tautan"),
            [{**{k: v for k, v in m.items() if k not in ("kunci", "seri")}, "i": id_item(m["kunci"]), "s": m["seri"]}
             for m in r.seri_meta])
    for t in r.tautan:
        b: TautanDB | None = t["baru"]
        if b is None:
            conn.execute(text("DELETE FROM lk.tautan_seri WHERE item_id = :i AND jenis_seri = :s"),
                         {"i": id_item(t["kunci"]), "s": t["seri"]})
            continue
        conn.execute(text(
            "INSERT INTO lk.tautan_seri (item_id, jenis_seri, sumber, rumus, seri_id, lapus_sumber_ids, besaran,"
            " faktor) VALUES (:i, :s, :src, :rm, :sid, :lap, :bes, :f) ON CONFLICT (item_id, jenis_seri) DO UPDATE SET"
            " sumber = EXCLUDED.sumber, rumus = EXCLUDED.rumus, seri_id = EXCLUDED.seri_id,"
            " lapus_sumber_ids = EXCLUDED.lapus_sumber_ids, besaran = EXCLUDED.besaran, faktor = EXCLUDED.faktor"),
            {"i": id_item(t["kunci"]), "s": t["seri"], "src": b.sumber, "rm": b.rumus,
             "sid": ref_id.get(b.seri_ref) if b.seri_ref else None,
             "lap": [lapus_id[x] for x in b.lapus] or None, "bes": b.besaran, "f": b.faktor})

    isi = [s for s in r.sel if s["baru"] is not None]
    hapus = [s for s in r.sel if s["baru"] is None]
    if isi:
        conn.execute(text(
            "INSERT INTO lk.nilai_item (putaran_id, item_id, jenis_seri, periode_id, nilai, status_sel, diubah_oleh)"
            " SELECT :p, x.i, x.s, x.per, x.v, 'isi', :u"
            " FROM unnest(CAST(:i AS bigint[]), CAST(:s AS text[]), CAST(:per AS int[]), CAST(:v AS float8[]))"
            " AS x(i, s, per, v)"
            " ON CONFLICT (putaran_id, item_id, jenis_seri, periode_id) DO UPDATE SET nilai = EXCLUDED.nilai,"
            " status_sel = 'isi', diubah_oleh = EXCLUDED.diubah_oleh, diubah_pada = now()"),
            {"p": p, "u": uid, "i": [id_item(s["kunci"]) for s in isi], "s": [s["seri"] for s in isi],
             "per": [periode[s["u"]] for s in isi], "v": [s["baru"] for s in isi]})
    if hapus:
        conn.execute(text(
            "DELETE FROM lk.nilai_item n USING unnest(CAST(:i AS bigint[]), CAST(:s AS text[]), CAST(:per AS int[]))"
            " AS x(i, s, per) WHERE n.putaran_id = :p AND n.item_id = x.i AND n.jenis_seri = x.s"
            " AND n.periode_id = x.per"),
            {"p": p, "i": [id_item(s["kunci"]) for s in hapus], "s": [s["seri"] for s in hapus],
             "per": [periode[s["u"]] for s in hapus]})
    for x in r.parameter:
        if x["baru"] is None:
            conn.execute(text("DELETE FROM lk.parameter_item WHERE putaran_id = :p AND item_id = :i AND kode = :k"),
                         {"p": p, "i": id_item(x["kunci"]), "k": x["kode"]})
        else:
            conn.execute(text(
                "INSERT INTO lk.parameter_item (putaran_id, item_id, kode, nilai, alasan, diubah_oleh)"
                " VALUES (:p, :i, :k, :v, :a, :u) ON CONFLICT (putaran_id, item_id, kode) DO UPDATE SET"
                " nilai = EXCLUDED.nilai, alasan = EXCLUDED.alasan, diubah_oleh = EXCLUDED.diubah_oleh,"
                " diubah_pada = now()"),
                {"p": p, "i": id_item(x["kunci"]), "k": x["kode"], "v": x["baru"], "a": x["alasan"], "u": uid})
    for x in r.seri_ref_sel:
        q = {"p": p, "s": ref_id[x["kode"]], "w": x["wilayah"], "per": periode[x["u"]], "v": x["baru"], "u": uid}
        if x["baru"] is None:
            conn.execute(text("DELETE FROM lk.nilai_seri_referensi WHERE putaran_id = :p AND seri_id = :s"
                              " AND wilayah_kode = :w AND periode_id = :per"), q)
        else:
            conn.execute(text(
                "INSERT INTO lk.nilai_seri_referensi (putaran_id, seri_id, wilayah_kode, periode_id, nilai,"
                " diubah_oleh) VALUES (:p, :s, :w, :per, :v, :u)"
                " ON CONFLICT (putaran_id, seri_id, wilayah_kode, periode_id)"
                " DO UPDATE SET nilai = EXCLUDED.nilai, diubah_oleh = EXCLUDED.diubah_oleh, diubah_pada = now()"), q)
    for a in r.adj:
        w, lap, tahap, met, jenis, harga, u = a["kunci"]
        if a["baru"] is None:
            conn.execute(text("DELETE FROM lk.penyesuaian WHERE id = :id"), {"id": a["id"]})
        elif a["id"] is not None:
            conn.execute(text(
                "UPDATE lk.penyesuaian SET nilai = :v, alasan = :al, status = :st, diusulkan_oleh = :u,"
                " diusulkan_pada = now(), diputus_oleh = CASE WHEN :st = 'disetujui' THEN :u END,"
                " diputus_pada = CASE WHEN :st = 'disetujui' THEN now() END,"
                " catatan_putusan = CASE WHEN :st = 'disetujui' THEN 'disetujui saat impor templat' END"
                " WHERE id = :id"), {"v": a["baru"], "al": a["alasan"], "st": a["status"], "u": uid, "id": a["id"]})
        else:
            conn.execute(text(
                "INSERT INTO lk.penyesuaian (putaran_id, wilayah_kode, lapus_id, tahap, metode_kode, jenis_kode, harga,"
                " periode_id, nilai, alasan, status, diusulkan_oleh, diputus_oleh, diputus_pada, catatan_putusan)"
                " VALUES (:p, :w, :l, :t, :m, :j, :h, :per, :v, :al, :st, :u,"
                " CASE WHEN :st = 'disetujui' THEN CAST(:u AS bigint) END,"
                " CASE WHEN :st = 'disetujui' THEN now() END,"
                " CASE WHEN :st = 'disetujui' THEN 'disetujui saat impor templat' END)"),
                {"p": p, "w": w, "l": lapus_id[lap], "t": tahap, "m": met, "j": jenis, "h": harga,
                 "per": periode[u], "v": a["baru"], "al": a["alasan"], "st": a["status"], "u": uid})
    # Lapus yang data/item/jangkar/tautan/penyesuaiannya berubah kembali ke draf (F4, keputusan 19).
    sentuh = {(x["kunci"][0], lapus_id[x["kunci"][1]])
              for x in [*r.item_baru, *r.item_ubah, *r.sel, *r.parameter, *r.tautan]}
    sentuh |= {(a["kunci"][0], lapus_id[a["kunci"][1]]) for a in r.adj if a["kunci"][2] != "SIMULASI"}
    tandai_ubah(conn, p, sentuh, f"impor templat {r.nama_berkas}"[:200])
    for w in sorted(r.wilayah):
        antrekan(conn, p, w, None, f"impor templat {r.nama_berkas}"[:200])
    return r.ringkasan()
