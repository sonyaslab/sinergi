"""Worker antrean hitung ujung-ke-ujung: muat dari DB → mesin → lk.hasil_* (+ versi_mesin, hash_input), dibandingkan
dengan oracle engine_ref pada spek yang sama. Angka sintetis (bukan data nyata)."""
from __future__ import annotations

import math

import pytest
from engine_ref import kompilasi as kp
from sqlalchemy import text

from sinergi_api.app import db
from sinergi_api.engine import VERSI_MESIN
from sinergi_api.worker.antrean import antrekan, pratinjau, proses_semua

pytestmark = pytest.mark.db
W = "6502"
URUT0 = 2019 * 4


def U(y: int, q: int) -> int:
    return y * 4 + q - 1


PER = list(range(U(2024, 1), U(2026, 1) + 1))


def _s(f) -> dict[int, float]:
    return {u: float(f(i)) for i, u in enumerate(PER)}


def _data_dasar() -> dict:
    t25 = [U(2025, q) for q in (1, 2, 3, 4)]
    return {
        "A.1.a": {"item": [
            {"metode": "REV", "seri": {"KUANTUM": _s(lambda i: 100 + 7 * i), "HARGA": _s(lambda i: 2 + 0.1 * i),
                                       "RKA": _s(lambda i: 0.3)}, "parameter": {"RKA_TD": 0.3}},
            {"metode": "REV", "seri": {"TPK": _s(lambda i: 40 + i), "KAMAR": _s(lambda i: 50), "HARGA": _s(lambda i: 1),
                                       "RKA": _s(lambda i: 0.2)}, "parameter": {"RKA_TD": 0.2},
             "tautan": [{"jenis_seri": "KUANTUM", "sumber": "RUMUS", "rumus": "TPK_X_KAMAR"}]},
            {"metode": "PDK", "seri": {"NILAI": _s(lambda i: 1)}}],
            "penyesuaian": [
                {"tahap": "METODE", "metode": "REV", "jenis": "ADJ1", "harga": "CP", "periode": U(2025, 2),
                 "nilai": 15.0},
                {"tahap": "REKON", "jenis": "ADJ3", "harga": "CP", "periode": U(2025, 3), "nilai": 40.0,
                 "status": "draf"},
                {"tahap": "REKON", "jenis": "CT_OUTPUT", "harga": "CP", "periode": U(2025, 3), "nilai": 999.0},
                {"tahap": "SIMULASI", "jenis": "SIM_NTB", "harga": "CP", "periode": U(2026, 1), "nilai": -12.5}]},
        "A.1.b": {"item": [
            {"metode": "EKS", "jenis_indeks": "IP",
             "seri": {"INDEKS": _s(lambda i: 100 + 3 * i), "IH": _s(lambda i: 95 + 2 * i),
                      "BASE_ADHK": {u: 250.0 for u in t25}, "RKA": _s(lambda i: 0.25)},
             "parameter": {"RKA_TD": 0.25}}]},
        "A.1.c": {"item": [
            {"metode": "DEF", "seri": {"OUT_ADHB": _s(lambda i: 300 + 11 * i), "NTB_ADHB": _s(lambda i: 180 + 5 * i)},
             "tautan": [{"jenis_seri": "IH", "sumber": "SERI_REFERENSI", "seri_ref": "REF_IH"}]}]},
        "G.1": {"item": [
            {"metode": "DEF", "seri": {"R_MARGIN": _s(lambda i: 0.1 + 0.002 * i), "RKA": _s(lambda i: 0.2)},
             "parameter": {"R_MARGIN_TD": 0.1, "RKA_TD": 0.2},
             "tautan": [{"jenis_seri": "OUT_ADHB", "sumber": "RUMUS", "rumus": "MARGIN_X_OUTPUT",
                         "lapus_sumber": ["A"]}]}]},
        "TOP": {"item": [
            {"metode": "DEF", "seri": {"OUT_ADHB": _s(lambda i: 40 + i), "IH": _s(lambda i: 100 + i)},
             "parameter": {"IH_TD": 100.0}}]},
        "SOP": {"item": [
            {"metode": "REV", "seri": {"KUANTUM": _s(lambda i: 10), "HARGA": _s(lambda i: 1.5)},
             "parameter": {"H_TD": 1.5}}]},
    }


def _spek(td_info, put, data_db, ref, baseline=2025, jdd=True):
    resmi = {}
    for lid, d in data_db.items():
        adj = [a for a in d["penyesuaian"]
               if a.get("status", "disetujui") == "disetujui" and not a["jenis"].startswith("CT")]
        resmi[lid] = {"item": d["item"], "penyesuaian": adj}
    return {"tahun_baseline": baseline, "jangkar_dari_data": jdd, "awal": PER[0], "akhir": PER[-1],
            "pohon": td_info[2], "referensi": ref, "data": resmi}


def _hasil_db(admin_conn, put):
    rows = admin_conn.execute(
        "SELECT h.lapus_id, h.tahap, p.urut, h.out_cp::float8, h.gva_cp::float8, h.out_k::float8, h.gva_k::float8,"
        " h.versi_mesin, h.hash_input FROM lk.hasil_lapus h JOIN ref.periode p ON p.id = h.periode_id"
        " WHERE h.putaran_id = %s AND h.wilayah_kode = %s", (put, W)).fetchall()
    return {(r[0], r[1], r[2]): r[3:] for r in rows}


def _rel(a, b):
    return abs(a - b) / max(abs(a), abs(b), 1.0)


def _siapkan(td_baru, putaran_baru, isi_spek, baseline=2025, jdd=True, data=None):
    td_info = td_baru(baseline, jdd)
    put = putaran_baru(td_info[0])  # data diisi saat terbuka; status akhir disetel sesudahnya
    data_db, ref = isi_spek(td_info[0], put, W, td_info[1], data or _data_dasar(),
                            {"REF_IH": _s(lambda i: 90 + 2.5 * i)})
    return td_info, put, data_db, ref


def _jalankan(uid_worker, put, alasan="uji"):
    with db.transaksi(uid_worker, alasan="uji antrekan") as c:
        jid = antrekan(c, put, W, None, alasan)
    proses_semua(uid_worker)
    return jid


def test_worker_menulis_hasil_identik_oracle(td_baru, putaran_baru, isi_spek, uid_worker, admin_conn):
    td_info, put, data_db, ref = _siapkan(td_baru, putaran_baru, isi_spek)
    jid = _jalankan(uid_worker, put)
    st, pesan = admin_conn.execute("SELECT status, pesan FROM lk.antrean_hitung WHERE id = %s", (jid,)).fetchone()
    assert st == "selesai", pesan
    db_h = _hasil_db(admin_conn, put)
    ref_h = kp.hitung_wilayah(_spek(td_info, put, data_db, ref))
    n = 0
    for lid, r in ref_h.items():
        for th in ("pre", "post", "benc", "final"):
            if th not in r:
                continue
            for u in PER:
                row = db_h[(lid, th.upper(), u)]
                for j, a in enumerate(("out_cp", "gva_cp", "out_k", "gva_k")):
                    assert _rel(row[j], getattr(r[th], a)[u - URUT0]) <= 1e-9, (lid, th, u, a)
                    n += 1
    assert n > 1000
    assert {r[4] for r in db_h.values()} == {VERSI_MESIN}
    assert all(len(r[5]) == 64 for r in db_h.values())
    lid = td_info[1]
    # FINAL dipengaruhi simulasi; draf ADJ3 dan CT tidak ikut angka resmi
    benc = db_h[(lid["A.1.a"], "BENC", U(2026, 1))]
    final = db_h[(lid["A.1.a"], "FINAL", U(2026, 1))]
    assert math.isclose(final[1], benc[1] - 12.5) and final[0] < benc[0]
    pre = db_h[(lid["A.1.a"], "PRE", U(2025, 3))]
    post = db_h[(lid["A.1.a"], "POST", U(2025, 3))]
    assert pre[0] == post[0]
    # TOP tanpa konsumsi antara; PDRB = NTB + TOP − SOP
    top = db_h[(lid["TOP"], "FINAL", U(2025, 4))]
    assert top[0] == top[1] and top[2] == top[3]
    for u in PER:
        ntb, tp, sp, pdrb = (db_h[(lid[k], "FINAL", u)][1] for k in ("NTB", "TOP", "SOP", "PDRB"))
        assert _rel(pdrb, ntb + tp - sp) <= 1e-12
    # lapus tanpa data tidak punya hasil; tabel pokok tetap lengkap
    assert (lid["B.1"], "BENC", U(2025, 1)) not in db_h
    n_baris, n_isi = admin_conn.execute(
        "SELECT count(*), count(ntb_adhb) FROM lk.v_tabel_pokok WHERE putaran_id = %s AND wilayah_kode = %s",
        (put, W)).fetchone()
    assert n_baris == len(td_info[2]) * len(PER) and 0 < n_isi < n_baris
    n_item = admin_conn.execute("SELECT count(*) FROM lk.hasil_item WHERE putaran_id = %s", (put,)).fetchone()[0]
    assert n_item == 7 * len(PER)  # PDK tidak dihitung
    met = admin_conn.execute("SELECT DISTINCT lapus_id, metode_kode FROM lk.hasil_metode WHERE putaran_id = %s",
                             (put,)).fetchall()
    assert (lid["A.1.a"], "REV") in met and (lid["A.1.a"], "EKS") not in met


def test_pratinjau_draf_tidak_disimpan(td_baru, putaran_baru, isi_spek, uid_worker, admin_conn):
    td_info, put, _, _ = _siapkan(td_baru, putaran_baru, isi_spek)
    _jalankan(uid_worker, put)
    sebelum = _hasil_db(admin_conn, put)
    with db.transaksi(uid_worker, alasan="uji pratinjau") as c:
        h = pratinjau(c, put, W)
    lid = td_info[1]["A.1.a"]
    t = h.sumbu.i(U(2025, 3))
    resmi = sebelum[(lid, "POST", U(2025, 3))]
    assert math.isclose(h.lapus[lid].tahap["POST"].out_cp[t], resmi[0] + 40.0)
    assert _hasil_db(admin_conn, put) == sebelum


def test_hash_input_berubah_hanya_bila_masukan_berubah(td_baru, putaran_baru, isi_spek, uid_worker, admin_conn):
    td_info, put, data_db, _ = _siapkan(td_baru, putaran_baru, isi_spek)
    _jalankan(uid_worker, put)
    a = _hasil_db(admin_conn, put)
    _jalankan(uid_worker, put, "hitung ulang")
    b = _hasil_db(admin_conn, put)
    assert a == b
    lid = td_info[1]
    iid = data_db[lid["A.1.b"]]["item"][0]["id"]
    admin_conn.execute("UPDATE lk.nilai_item SET nilai = nilai + 1 WHERE putaran_id = %s AND item_id = %s"
                       " AND jenis_seri = 'INDEKS' AND periode_id = (SELECT id FROM ref.periode WHERE urut = %s)",
                       (put, iid, U(2026, 1)))
    _jalankan(uid_worker, put, "data berubah")
    c = _hasil_db(admin_conn, put)
    h = lambda d, k: d[(lid[k], "BENC", U(2025, 1))][5]  # noqa: E731
    assert h(c, "A.1.b") != h(a, "A.1.b") and h(c, "G.1") != h(a, "G.1") and h(c, "A") != h(a, "A")
    assert h(c, "A.1.a") == h(a, "A.1.a") and h(c, "TOP") == h(a, "TOP")


def test_td2010_jangkar_parameter(td_baru, putaran_baru, isi_spek, uid_worker, admin_conn):
    data = _data_dasar()
    data["A.1.c"]["item"][0]["parameter"] = {"RKA_TD": 0.1, "IH_TD": 100.0}
    data["A.1.b"]["item"][0]["seri"]["BASE_ADHK"] = {U(2024, q): 240.0 for q in (1, 2, 3, 4)}
    data["A.1.b"]["item"][0]["parameter"]["IH_TD"] = 100.0
    data["A.1.a"]["item"][0]["parameter"]["H_TD"] = 1.8
    data["A.1.a"]["item"][1]["parameter"]["H_TD"] = 0.9
    td_info, put, data_db, ref = _siapkan(td_baru, putaran_baru, isi_spek, baseline=2024, jdd=False, data=data)
    _jalankan(uid_worker, put)
    db_h = _hasil_db(admin_conn, put)
    ref_h = kp.hitung_wilayah(_spek(td_info, put, data_db, ref, baseline=2024, jdd=False))
    lid = td_info[1]["A.1.c"]
    for u in PER:
        row = db_h[(lid, "BENC", u)]
        assert _rel(row[3], ref_h[lid]["benc"].gva_k[u - URUT0]) <= 1e-9
        assert _rel(row[3], 0.9 * row[2]) <= 1e-12  # NTB ADHK = (1 − RKA_TD parameter) × output ADHK


def test_putaran_terkunci_dan_siklus_gagal_rapi(td_baru, putaran_baru, isi_spek, uid_worker, admin_conn):
    td_info, put, _, _ = _siapkan(td_baru, putaran_baru, isi_spek)
    admin_conn.execute("UPDATE lk.putaran SET status = 'terkunci' WHERE id = %s", (put,))
    jid = _jalankan(uid_worker, put)
    assert admin_conn.execute("SELECT status, pesan FROM lk.antrean_hitung WHERE id = %s", (jid,)).fetchone() == (
        "gagal", "Putaran terkunci; hasil tidak diubah.")
    data = _data_dasar()
    data["A.1.c"]["item"][0]["tautan"] = [{"jenis_seri": "IH", "sumber": "HASIL_LAPUS", "lapus_sumber": ["G.1"],
                                           "besaran": "IMPLISIT_OUT"}]
    td_info, put, _, _ = _siapkan(td_baru, putaran_baru, isi_spek, data=data)
    jid = _jalankan(uid_worker, put)
    st, pesan = admin_conn.execute("SELECT status, pesan FROM lk.antrean_hitung WHERE id = %s", (jid,)).fetchone()
    assert st == "gagal" and pesan == "Tautan antarlapus membentuk siklus: A.1.c, G.1."  # kode lapus, tanpa angka


def test_antrean_tidak_ganda_dan_digabung(td_baru, putaran_baru, isi_spek, uid_worker, admin_conn):
    _, put, _, _ = _siapkan(td_baru, putaran_baru, isi_spek)
    with db.transaksi(uid_worker, alasan="uji antrean") as c:
        a = antrekan(c, put, W, None, "simpan data")
        assert antrekan(c, put, W, 5, "simpan data lagi") is None
    admin_conn.execute("UPDATE lk.antrean_hitung SET dibuat_pada = dibuat_pada - interval '1 minute' WHERE id = %s",
                       (a,))
    b = admin_conn.execute("INSERT INTO lk.antrean_hitung (putaran_id, wilayah_kode, alasan) VALUES (%s, %s, 'x')"
                           " RETURNING id", (put, W)).fetchone()[0]
    assert proses_semua(uid_worker) == 1
    rows = dict(admin_conn.execute("SELECT id, pesan FROM lk.antrean_hitung WHERE id IN (%s, %s)", (a, b)).fetchall())
    assert rows[b] == f"digabung ke job {a}"
    with db.engine_rw().connect() as c:
        assert c.execute(text("SELECT count(*) FROM lk.antrean_hitung WHERE putaran_id = :p AND status <> 'selesai'"),
                         {"p": put}).scalar_one() == 0
