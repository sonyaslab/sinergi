"""Bantuan uji alur F4 (putaran, status lapus, penyesuaian, kunci). Angka fiktif."""
from __future__ import annotations

from urllib.parse import quote

from tests.conftest import tanpa_uid

W = "6500"


def U(y: int, q: int) -> int:
    return y * 4 + q - 1


PER = [U(2024, q) for q in (1, 2, 3, 4)] + [U(2025, q) for q in (1, 2, 3, 4)] + [U(2026, 1)]


def h_(h: dict[str, str], alasan: str | None = None) -> dict[str, str]:
    x = tanpa_uid(h)
    if alasan:
        x["X-Alasan"] = quote(alasan)
    return x


def lapus_id(admin_conn, td: int) -> dict[str, int]:
    return dict(admin_conn.execute("SELECT kode, id FROM ref.lapus WHERE tahun_dasar_id = %s", (td,)).fetchall())


def tugaskan(admin_conn, uid: int, td: int, lid: int, wilayah: str = W) -> None:
    admin_conn.execute("INSERT INTO lk.penugasan (pengguna_id, tahun_dasar_id, wilayah_kode, lapus_id, peran_tugas)"
                       " VALUES (%s, %s, %s, %s, 'operator')", (uid, td, wilayah, lid))


def buka(klien, h, td: int, nama: str = "Put uji", sumber: int | None = None, awal: int = U(2024, 1),
         tahun: int = 2026, triwulan: int = 1, **kw) -> int:
    r = klien.post("/api/putaran", headers=h_(h), json={
        "tahun_dasar_id": td, "tahun": tahun, "triwulan": triwulan, "nama": nama, "jenis": "REGULER",
        "periode_awal": awal, "sumber_putaran_id": sumber, **kw})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def isi_rev(klien, h, put: int, lid: int, nama: str = "Padi", dasar: float = 100.0, rka_td: float | None = 0.3,
            wilayah: str = W) -> int:
    """+ Komoditas REV dengan KUANTUM, HARGA, RKA lengkap 2024Q1–2026Q1 dan RKA_TD (lolos validasi blokir ajukan)."""
    r = klien.post("/api/data-dasar/item", headers=h_(h), json={
        "putaran_id": put, "wilayah": wilayah, "lapus_id": lid, "metode": "REV", "nama": nama,
        "alasan": "komoditas uji alur putaran"})
    assert r.status_code == 201, r.text
    iid = r.json()["id"]
    ubah = [{"item_id": iid, "seri": "KUANTUM", "periode": u, "nilai": dasar + 2 * i} for i, u in enumerate(PER)]
    ubah += [{"item_id": iid, "seri": "HARGA", "periode": u, "nilai": 2.0 + 0.01 * i} for i, u in enumerate(PER)]
    ubah += [{"item_id": iid, "seri": "RKA", "periode": u, "nilai": 0.3} for u in PER]
    r = klien.put("/api/data-dasar/nilai", headers=h_(h), json={"putaran_id": put, "perubahan": ubah})
    assert r.status_code == 200, r.text
    if rka_td is not None:
        r = klien.put("/api/data-dasar/parameter", headers=h_(h), json={
            "putaran_id": put, "item_id": iid, "kode": "RKA_TD", "nilai": rka_td})
        assert r.status_code == 200, r.text
    return iid


def nihil_lainnya(admin_conn, put: int, td: int, wilayah: str = W) -> int:
    """Tandai NIHIL semua daun tanpa item (persiapan kunci; jalur API NIHIL diuji terpisah)."""
    return admin_conn.execute(
        "INSERT INTO lk.status_lapus (putaran_id, wilayah_kode, lapus_id, status, catatan)"
        " SELECT %s, %s, l.id, 'nihil', 'tidak ada kegiatan (uji)' FROM ref.lapus l WHERE l.tahun_dasar_id = %s"
        " AND l.jenis = 'daun' AND l.aktif AND NOT EXISTS (SELECT 1 FROM lk.item i WHERE i.lapus_id = l.id"
        " AND i.wilayah_kode = %s) ON CONFLICT DO NOTHING", (put, wilayah, td, wilayah)).rowcount


def status(admin_conn, put: int, lid: int, wilayah: str = W) -> str:
    r = admin_conn.execute("SELECT status FROM lk.status_lapus WHERE putaran_id = %s AND wilayah_kode = %s"
                           " AND lapus_id = %s", (put, wilayah, lid)).fetchone()
    return r[0] if r else "belum"


def hasil(admin_conn, put: int, lid: int, u: int, tahap: str = "FINAL", wilayah: str = W) -> tuple[float, ...]:
    r = admin_conn.execute(
        "SELECT h.out_cp::float8, h.gva_cp::float8, h.out_k::float8, h.gva_k::float8 FROM lk.hasil_lapus h"
        " JOIN ref.periode p ON p.id = h.periode_id WHERE h.putaran_id = %s AND h.wilayah_kode = %s"
        " AND h.lapus_id = %s AND h.tahap = %s AND p.urut = %s", (put, wilayah, lid, tahap, u)).fetchone()
    assert r is not None, (put, lid, u, tahap)
    return tuple(r)
