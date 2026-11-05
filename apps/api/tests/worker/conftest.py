"""Fixture uji worker: tahun dasar terisolasi (salinan pohon TD2025), putaran, dan pengisi data dari spek."""
from __future__ import annotations

import secrets
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[4]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture
def td_baru(admin_conn):
    """td_baru(baseline=2025, jangkar_dari_data=True) -> (td_id, {kode: lapus_id}, pohon_spek)."""

    def _buat(baseline: int = 2025, jangkar_dari_data: bool = True):
        kode = f"TW{secrets.randbelow(90000) + 10000}"
        td = admin_conn.execute(
            "INSERT INTO ref.tahun_dasar (kode, tahun_dasar, status, tahun_awal_seri, klasifikasi, tahun_baseline_eks,"
            " jangkar_dari_data) VALUES (%s, 2025, 'rencana', 2019, 'KBLI2025', %s, %s) RETURNING id",
            (kode, baseline, jangkar_dari_data)).fetchone()[0]
        admin_conn.execute(
            "INSERT INTO ref.lapus (tahun_dasar_id, kode, nama, level, urutan, jenis, is_migas, kode_lk_bps)"
            " SELECT %s, kode, nama, level, urutan, jenis, is_migas, kode_lk_bps FROM ref.lapus"
            " WHERE tahun_dasar_id = (SELECT id FROM ref.tahun_dasar WHERE kode = 'TD2025')", (td,))
        admin_conn.execute(
            "UPDATE ref.lapus c SET induk_id = pb.id FROM ref.lapus s, ref.lapus ps, ref.lapus pb"
            " WHERE c.tahun_dasar_id = %s AND s.tahun_dasar_id = (SELECT id FROM ref.tahun_dasar WHERE kode = 'TD2025')"
            " AND s.kode = c.kode AND ps.id = s.induk_id AND pb.tahun_dasar_id = %s AND pb.kode = ps.kode", (td, td))
        admin_conn.execute(
            "INSERT INTO ref.lapus_kelompok (kelompok_id, anggota_id) SELECT kb.id, ab.id FROM ref.lapus_kelompok k"
            " JOIN ref.lapus ks ON ks.id = k.kelompok_id JOIN ref.lapus as_ ON as_.id = k.anggota_id"
            " JOIN ref.lapus kb ON kb.tahun_dasar_id = %s AND kb.kode = ks.kode"
            " JOIN ref.lapus ab ON ab.tahun_dasar_id = %s AND ab.kode = as_.kode"
            " WHERE ks.tahun_dasar_id = (SELECT id FROM ref.tahun_dasar WHERE kode = 'TD2025')", (td, td))
        baris = admin_conn.execute(
            "SELECT id, kode, jenis, induk_id, urutan, is_migas FROM ref.lapus WHERE tahun_dasar_id = %s AND aktif"
            " ORDER BY urutan", (td,)).fetchall()
        angg: dict[int, list[int]] = {}
        for k, a in admin_conn.execute(
                "SELECT k.kelompok_id, k.anggota_id FROM ref.lapus_kelompok k JOIN ref.lapus a ON a.id = k.anggota_id"
                " WHERE a.tahun_dasar_id = %s ORDER BY a.urutan", (td,)).fetchall():
            angg.setdefault(k, []).append(a)
        pohon = [{"id": i, "kode": k, "jenis": j, "induk": p, "urutan": u, "is_migas": m, "anggota": angg.get(i, [])}
                 for i, k, j, p, u, m in baris]
        return td, {r["kode"]: r["id"] for r in pohon}, pohon

    return _buat


def _pid(admin_conn, tahun: int, tw: int) -> int:
    q = "SELECT id FROM ref.periode WHERE tahun = %s AND triwulan = %s"
    return admin_conn.execute(q, (tahun, tw)).fetchone()[0]


@pytest.fixture
def putaran_baru(admin_conn):
    def _buat(td: int, awal=(2024, 1), akhir=(2026, 1), status: str = "terbuka") -> int:
        return admin_conn.execute(
            "INSERT INTO lk.putaran (tahun_dasar_id, tahun, triwulan, nomor, nama, jenis, status, periode_awal_id,"
            " periode_akhir_id) VALUES (%s, %s, %s, %s, 'Uji mesin', 'REGULER', %s, %s, %s) RETURNING id",
            (td, akhir[0], akhir[1], secrets.randbelow(30000) + 100, status, _pid(admin_conn, *awal),
             _pid(admin_conn, *akhir))).fetchone()[0]

    return _buat


@pytest.fixture
def uid_worker(admin_conn) -> int:
    return admin_conn.execute("SELECT id FROM sec.pengguna WHERE username = 'sistem.worker'").fetchone()[0]


@pytest.fixture
def isi_spek(admin_conn):
    """isi_spek(td, putaran, wilayah, lapus_by_kode, data_by_kode, referensi) -> data spek (id DB).

    data_by_kode = {kode_lapus: {"item": [item spek tanpa id], "penyesuaian": [... + "status"]}}.
    """

    def _isi(td: int, put: int, wil: str, lid: dict[str, int], data: dict[str, dict], referensi: dict | None = None):
        per = dict(admin_conn.execute("SELECT urut, id FROM ref.periode").fetchall())
        seri_id = {}
        for kode, s in (referensi or {}).items():
            sid = admin_conn.execute("INSERT INTO lk.seri_referensi (kode, nama, jenis) VALUES (%s, %s, 'indeks_harga')"
                                     " RETURNING id", (f"{kode}_{put}", kode)).fetchone()[0]
            seri_id[kode] = (sid, f"{kode}_{put}")
            for u, x in s.items():
                admin_conn.execute("INSERT INTO lk.nilai_seri_referensi (putaran_id, seri_id, wilayah_kode, periode_id,"
                                   " nilai) VALUES (%s, %s, %s, %s, %s)", (put, sid, wil, per[u], x))
        out: dict[int, dict] = {}
        for kode, d in data.items():
            items = []
            for no, it in enumerate(d.get("item", []), start=1):
                iid = admin_conn.execute(
                    "INSERT INTO lk.item (tahun_dasar_id, wilayah_kode, lapus_id, metode_kode, nomor, nama,"
                    " jenis_indeks, periode_mulai_id, periode_selesai_id, alasan) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,"
                    " 'uji mesin hitung') RETURNING id",
                    (td, wil, lid[kode], it["metode"], no, f"Item uji {no}", it.get("jenis_indeks"),
                     per.get(it.get("mulai")), per.get(it.get("selesai")))).fetchone()[0]
                for js, s in it.get("seri", {}).items():
                    for u, x in s.items():
                        admin_conn.execute("INSERT INTO lk.nilai_item (putaran_id, item_id, jenis_seri, periode_id,"
                                           " nilai) VALUES (%s,%s,%s,%s,%s)", (put, iid, js, per[u], x))
                for k, x in it.get("parameter", {}).items():
                    admin_conn.execute("INSERT INTO lk.parameter_item (putaran_id, item_id, kode, nilai, alasan)"
                                       " VALUES (%s,%s,%s,%s,'jangkar uji')", (put, iid, k, x))
                taut = []
                for t in it.get("tautan", []):
                    sid = seri_id[t["seri_ref"]][0] if t.get("seri_ref") else None
                    src = [lid[k] for k in t.get("lapus_sumber", [])] or None
                    admin_conn.execute(
                        "INSERT INTO lk.tautan_seri (item_id, jenis_seri, sumber, rumus, seri_id, lapus_sumber_ids,"
                        " besaran, faktor) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                        (iid, t["jenis_seri"], t["sumber"], t.get("rumus"), sid, src, t.get("besaran"),
                         t.get("faktor", 1.0)))
                    taut.append({**t, "lapus_sumber": src or [],
                                 "seri_ref": seri_id[t["seri_ref"]][1] if t.get("seri_ref") else None})
                items.append({**it, "id": iid, "tautan": taut})
            adj = []
            for a in d.get("penyesuaian", []):
                admin_conn.execute(
                    "INSERT INTO lk.penyesuaian (putaran_id, wilayah_kode, lapus_id, tahap, metode_kode, jenis_kode,"
                    " harga, periode_id, nilai, alasan, status) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,"
                    " 'penyesuaian uji mesin',%s)",
                    (put, wil, lid[kode], a["tahap"], a.get("metode"), a["jenis"], a["harga"], per[a["periode"]],
                     a["nilai"], a.get("status", "disetujui")))
                adj.append(a)
            out[lid[kode]] = {"item": items, "penyesuaian": adj}
        return out, {v[1]: (referensi or {})[k] for k, v in seri_id.items()}

    return _isi
