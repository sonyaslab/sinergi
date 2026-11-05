"""Impor/ekspor templat data dasar (F3) ujung-ke-ujung pada DB uji: templat KOSONG di repo, templat sintetis terisi
(angka fiktif), round-trip ekspor -> impor -> hitung sama. Mesin dibandingkan dengan oracle engine_ref."""
from __future__ import annotations

import io
import math

import openpyxl
import pytest
from engine_ref import kompilasi as kp

from sinergi_api.worker.antrean import proses_semua
from tests.conftest import tanpa_uid
from tests.golden.adaptor import kode_sumber, petakan_lapus_sumber, pohon_datar, spek_dari_templat

from .conftest import TEMPLAT, isi_sintetis

pytestmark = pytest.mark.db
KOSONG = {"TD2025": TEMPLAT / "Templat_Data_Dasar_TD2025_KOSONG.xlsx",
          "TD2010": TEMPLAT / "Templat_Data_Dasar_TD2010_KOSONG.xlsx"}
JUMLAH_ITEM = {"TD2025": 274, "TD2010": 361}


def impor(klien, h, putaran: int, data: bytes, nama: str = "templat.xlsx", **opsi) -> dict:
    q = "&".join(f"{k}={str(v).lower()}" for k, v in opsi.items())
    r = klien.post(f"/api/impor/templat?putaran_id={putaran}&nama={nama}&{q}", content=data,
                   headers={**tanpa_uid(h), "Content-Type": "application/octet-stream"})
    assert r.status_code == 200, r.text
    return r.json()


def terapkan(klien, h, pratinjau: dict, data: bytes) -> dict:
    r = klien.post(f"/api/impor/{pratinjau['impor_id']}/terapkan", content=data,
                   headers={**tanpa_uid(h), "Content-Type": "application/octet-stream"})
    assert r.status_code == 200, r.text
    return r.json()


def ekspor(klien, putaran: int, kosong: bool = False) -> bytes:
    r = klien.get(f"/api/ekspor/templat?putaran_id={putaran}&kosong={str(kosong).lower()}")
    assert r.status_code == 200, r.text
    return r.content


def _rapi(x):
    """Teks dibandingkan setelah spasi ganda dirapikan (temuan S11: nama komoditas tidak baku)."""
    return " ".join(x.split()) if isinstance(x, str) else x


def _sheet_baris(data: bytes | str) -> dict[str, list[list]]:
    wb = openpyxl.load_workbook(io.BytesIO(data) if isinstance(data, bytes) else data)
    out = {}
    for ws in wb.worksheets:
        if len(ws.title) == 1:
            out[ws.title] = [[_rapi(c.value) for c in r] for r in ws.iter_rows(min_row=4)
                             if r[0].value is not None or r[0].row == 4]
    return out


@pytest.mark.parametrize("td_kode", ["TD2025", "TD2010"])
def test_templat_kosong_impor_ekspor_persis(td_kode, klien, sebagai, td_salin, putaran_uji):
    h = sebagai("admin")
    put = putaran_uji(td_salin(td_kode))
    data = KOSONG[td_kode].read_bytes()
    p = impor(klien, h, put, data, KOSONG[td_kode].name)
    assert p["dapat_diterapkan"], [x for x in p["pesan"] if x["tingkat"] == "galat"][:5]
    assert p["ringkasan"]["galat"] == 0
    assert p["ringkasan"]["item_baru"] == JUMLAH_ITEM[td_kode]
    assert p["ringkasan"]["sel_baru"] == 0  # templat kosong: tanpa angka
    terapkan(klien, h, p, data)

    keluar = ekspor(klien, put, kosong=True)
    asli, baru = _sheet_baris(str(KOSONG[td_kode])), _sheet_baris(keluar)
    assert sorted(asli) == sorted(baru)
    for sh, rows in asli.items():
        hd = rows[0]
        assert baru[sh][0] == hd, sh
        assert len(baru[sh]) == len(rows), sh
        k_taut = hd.index("Tautan / Rumus")
        for a, b in zip(rows[1:], baru[sh][1:], strict=True):
            ikut = isinstance(a[k_taut], str) and ("Ikut " in a[k_taut] or " mengikuti item " in a[k_taut])
            if ikut or (isinstance(b[k_taut], str) and b[k_taut].startswith("REF: REF_") and not a[k_taut]):
                assert b[k_taut].startswith("REF: REF_"), (sh, a[:6])  # keputusan 5: ikut item lain -> seri referensi
                a, b = a[:k_taut] + a[k_taut + 1:], b[:k_taut] + b[k_taut + 1:]
            assert a == b, (sh, a[:6], [(i, x, y) for i, (x, y) in enumerate(zip(a, b, strict=True)) if x != y])

    # impor ulang hasil ekspor = tidak ada perubahan
    p2 = impor(klien, h, put, keluar, "ekspor.xlsx")
    r = p2["ringkasan"]
    assert r["galat"] == 0 and r["item_baru"] == r["item_berubah"] == r["tautan"] == r["sel_baru"] == 0, r
    assert r["metadata_seri"] == 0 and r["parameter"] == 0, r


def _hasil(admin_conn, put: int, tahap: str = "BENC") -> dict[str, dict[int, tuple]]:
    out: dict[str, dict[int, tuple]] = {}
    for kode, u, *x in admin_conn.execute(
            "SELECT l.kode, p.urut, h.out_cp::float8, h.gva_cp::float8, h.out_k::float8, h.gva_k::float8"
            " FROM lk.hasil_lapus h JOIN ref.lapus l ON l.id = h.lapus_id JOIN ref.periode p ON p.id = h.periode_id"
            " WHERE h.putaran_id = %s AND h.wilayah_kode = '6500' AND h.tahap = %s", (put, tahap)).fetchall():
        out.setdefault(kode, {})[u] = tuple(x)
    return out


def _rel(a: float, b: float) -> float:
    return abs(a - b) / max(abs(a), abs(b), 1.0)


@pytest.mark.parametrize("td_kode", ["TD2025", "TD2010"])
def test_templat_sintetis_sama_dengan_oracle(td_kode, klien, sebagai, td_salin, putaran_uji, admin_conn, uid_worker,
                                             tmp_path):
    """Templat terisi (angka fiktif) lewat importer -> DB -> worker = oracle atas pembaca rujukan berkas yang sama."""
    h = sebagai("admin")
    put = putaran_uji(td_salin(td_kode))
    data = isi_sintetis(KOSONG[td_kode], benih=11)
    p = impor(klien, h, put, data, "sintetis.xlsx", setujui_penyesuaian=True)
    assert p["dapat_diterapkan"], [x for x in p["pesan"] if x["tingkat"] == "galat"][:5]
    assert p["ringkasan"]["sel_baru"] > 1000 and p["ringkasan"]["penyesuaian"] > 0
    terapkan(klien, h, p, data)
    proses_semua(uid_worker)
    db = _hasil(admin_conn, put)

    f = tmp_path / "sintetis.xlsx"
    f.write_bytes(data)
    baseline, jdd = (2025, True) if td_kode == "TD2025" else (2024, False)
    per_wil, info = spek_dari_templat(str(f), baseline, jdd)
    d = per_wil["6500"]
    pohon = pohon_datar(sorted(set(d) | kode_sumber(d)))
    ids = {r["kode"]: r["id"] for r in pohon}
    petakan_lapus_sumber(d, ids)
    awal, akhir = 2019 * 4, 2026 * 4 + 1
    spec = {"tahun_baseline": baseline, "jangkar_dari_data": jdd, "awal": awal, "akhir": akhir, "pohon": pohon,
            "referensi": info["referensi"].get("6500", {}), "data": {ids[k]: d[k] for k in d}}
    ref = kp.hitung_wilayah(spec)
    terburuk, n = 0.0, 0
    for kode, lid in ids.items():
        if lid not in ref or kode not in d:
            assert kode not in db
            continue
        e = ref[lid]["benc"]
        for u in range(awal, akhir + 1):
            x = db[kode][u]
            for a, b in zip(x, (e.out_cp[u - awal], e.gva_cp[u - awal], e.out_k[u - awal], e.gva_k[u - awal]),
                            strict=True):
                terburuk = max(terburuk, _rel(a, b))
        n += 1
    assert n >= 40
    assert terburuk <= 1e-9, terburuk


def _semua_hasil(admin_conn, put: int) -> dict[tuple, tuple]:
    rows = admin_conn.execute(
        "SELECT h.wilayah_kode, l.kode, p.urut, h.tahap, h.out_cp::float8, h.gva_cp::float8, h.out_k::float8,"
        " h.gva_k::float8 FROM lk.hasil_lapus h JOIN ref.lapus l ON l.id = h.lapus_id"
        " JOIN ref.periode p ON p.id = h.periode_id WHERE h.putaran_id = %s", (put,)).fetchall()
    return {(w, k, u, t): tuple(x) for w, k, u, t, *x in rows}


def _semua_item(admin_conn, put: int) -> dict[tuple, tuple]:
    rows = admin_conn.execute(
        "SELECT i.wilayah_kode, l.kode, i.metode_kode, i.nomor, p.urut, h.out_cp::float8, h.gva_cp::float8,"
        " h.out_k::float8, h.gva_k::float8 FROM lk.hasil_item h JOIN lk.item i ON i.id = h.item_id"
        " JOIN ref.lapus l ON l.id = i.lapus_id JOIN ref.periode p ON p.id = h.periode_id"
        " WHERE h.putaran_id = %s", (put,)).fetchall()
    return {(w, k, m, n, u): tuple(x) for w, k, m, n, u, *x in rows}


@pytest.mark.parametrize("td_kode", ["TD2025", "TD2010"])
def test_round_trip_ekspor_impor_hitung_sama(td_kode, klien, sebagai, td_salin, putaran_uji, admin_conn,
                                             uid_worker):
    h = sebagai("admin")
    put1 = putaran_uji(td_salin(td_kode))
    data = isi_sintetis(KOSONG[td_kode], benih=23)
    p = impor(klien, h, put1, data, "sintetis.xlsx", setujui_penyesuaian=True)
    assert p["dapat_diterapkan"], [x for x in p["pesan"] if x["tingkat"] == "galat"][:5]
    terapkan(klien, h, p, data)
    proses_semua(uid_worker)
    hasil1, item1 = _semua_hasil(admin_conn, put1), _semua_item(admin_conn, put1)
    assert len(hasil1) > 1000

    keluar = ekspor(klien, put1)
    # impor ulang ke putaran yang sama: tidak ada perubahan apa pun
    p_sama = impor(klien, h, put1, keluar, "ekspor.xlsx")
    r = p_sama["ringkasan"]
    assert all(r[k] == 0 for k in ("item_baru", "item_berubah", "sel_baru", "sel_berubah", "parameter", "tautan",
                                   "metadata_seri", "seri_referensi_baru", "sel_seri_referensi", "penyesuaian",
                                   "galat")), r

    # impor ke tahun dasar baru (salinan pohon) -> hitung -> sama
    put2 = putaran_uji(td_salin(td_kode))
    p2 = impor(klien, h, put2, keluar, "ekspor.xlsx", setujui_penyesuaian=True)
    assert p2["dapat_diterapkan"], [x for x in p2["pesan"] if x["tingkat"] == "galat"][:5]
    terapkan(klien, h, p2, keluar)
    proses_semua(uid_worker)
    hasil2, item2 = _semua_hasil(admin_conn, put2), _semua_item(admin_conn, put2)
    assert hasil1.keys() == hasil2.keys()
    assert item1.keys() == item2.keys()
    beda = max((_rel(a, b) for k in hasil1 for a, b in zip(hasil1[k], hasil2[k], strict=True)), default=0.0)
    beda_item = max((_rel(a, b) for k in item1 for a, b in zip(item1[k], item2[k], strict=True)), default=0.0)
    assert beda == 0.0 and beda_item == 0.0, (beda, beda_item)
    assert not any(math.isnan(x) for v in hasil2.values() for x in v)
