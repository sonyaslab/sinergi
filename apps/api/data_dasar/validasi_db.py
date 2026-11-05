"""Muat konteks validasi dari DB dan tulis temuan ke lk.hasil_validasi (dipanggil worker setelah hitung).

Temuan ditulis ulang per (putaran, wilayah) setiap hitung; konfirmasi beralasan (lk.konfirmasi_validasi) bertahan
karena dicocokkan dengan kunci temuan.
"""
from __future__ import annotations

from collections import defaultdict

from sqlalchemy import Connection, text

from ..engine import HasilWilayah, MasukanWilayah, hitung_wilayah
from .validasi import AdjInfo, AturanValidasi, InfoItem, KonteksValidasi, Temuan, validasi


def muat_konteks(conn: Connection, putaran_id: int, wilayah: str, awal: int, akhir: int) -> KonteksValidasi:
    q = {"p": putaran_id, "w": wilayah}
    td = conn.execute(text("SELECT t.id, t.kode, t.tahun_dasar FROM lk.putaran p JOIN ref.tahun_dasar t"
                           " ON t.id = p.tahun_dasar_id WHERE p.id = :p"), q).one()
    q["td"] = td.id
    item: dict[int, InfoItem] = {}
    for r in conn.execute(text(
            "SELECT id, lapus_id, metode_kode, nama, nomor, status, katalog_id, satuan_kode FROM lk.item"
            " WHERE tahun_dasar_id = :td AND wilayah_kode = :w"), q):
        item[r.id] = InfoItem(r.id, r.lapus_id, r.metode_kode, r.nama, r.nomor, r.status, r.katalog_id, r.satuan_kode)
    for r in conn.execute(text(
            "SELECT s.item_id, s.jenis_seri, s.satuan FROM lk.seri_item s JOIN lk.item i ON i.id = s.item_id"
            " WHERE i.tahun_dasar_id = :td AND i.wilayah_kode = :w"), q):
        item[r.item_id].satuan_seri[r.jenis_seri] = r.satuan
    for r in conn.execute(text(
            "SELECT n.item_id, n.jenis_seri, p.urut FROM lk.nilai_item n JOIN ref.periode p ON p.id = n.periode_id"
            " JOIN lk.item i ON i.id = n.item_id WHERE n.putaran_id = :p AND n.status_sel = 'tidak_tersedia'"
            " AND i.wilayah_kode = :w"), q):
        item[r.item_id].tidak_tersedia.add((r.jenis_seri, r.urut))
    lapus = {r.id: (r.kode, r.jenis) for r in conn.execute(text(
        "SELECT id, kode, jenis FROM ref.lapus WHERE tahun_dasar_id = :td AND aktif"), q)}
    aturan = {r.kode: AturanValidasi(r.tingkat, dict(r.parameter or {}), r.aktif) for r in conn.execute(text(
        "SELECT kode, tingkat, parameter, aktif FROM ref.validasi"))}
    wajib: dict[str, set[str]] = defaultdict(set)
    for m, k in conn.execute(text("SELECT metode_kode, kode FROM ref.jenis_seri WHERE wajib")):
        wajib[m].add(k)
    adj = [AdjInfo(r.lapus_id, r.tahap, r.metode_kode, r.jenis_kode, r.harga, r.urut, float(r.nilai), r.status)
           for r in conn.execute(text(
               "SELECT a.lapus_id, a.tahap, a.metode_kode, a.jenis_kode, a.harga, p.urut, a.nilai, a.status"
               " FROM lk.penyesuaian a JOIN ref.periode p ON p.id = a.periode_id"
               " WHERE a.putaran_id = :p AND a.wilayah_kode = :w"), q)]
    status = {r.lapus_id: r.status for r in conn.execute(text(
        "SELECT lapus_id, status FROM lk.status_lapus WHERE putaran_id = :p AND wilayah_kode = :w"), q)}
    konf = {(r.kode_validasi, r.lapus_id, r.kunci): (r.dikonfirmasi_oleh, r.alasan) for r in conn.execute(text(
        "SELECT kode_validasi, lapus_id, kunci, dikonfirmasi_oleh, alasan FROM lk.konfirmasi_validasi"
        " WHERE putaran_id = :p AND wilayah_kode = :w"), q)}
    return KonteksValidasi(td.kode, td.tahun_dasar, awal, akhir, item, lapus, aturan, dict(wajib), adj, status, konf)


def tulis_temuan(conn: Connection, putaran_id: int, wilayah: str, temuan: list[Temuan]) -> int:
    conn.execute(text("DELETE FROM lk.hasil_validasi WHERE putaran_id = :p AND wilayah_kode = :w"),
                 {"p": putaran_id, "w": wilayah})
    if not temuan:
        return 0
    per = {int(r[0]): int(r[1]) for r in conn.execute(text("SELECT urut, id FROM ref.periode"))}
    raw = conn.connection.driver_connection
    assert raw is not None
    with raw.cursor() as cur, cur.copy(
            "COPY lk.hasil_validasi (putaran_id, wilayah_kode, lapus_id, item_id, periode_id, kode_validasi, pesan,"
            " dikonfirmasi_oleh, alasan_konfirmasi, jenis_seri, tingkat, kunci) FROM STDIN") as cp:
        for t in temuan:
            cp.write_row((putaran_id, wilayah, t.lapus_id, t.item_id, per.get(t.periode) if t.periode else None,
                          t.kode, t.pesan, t.dikonfirmasi_oleh, t.alasan_konfirmasi, t.jenis_seri, t.tingkat, t.kunci))
    return len(temuan)


def jalankan(conn: Connection, putaran_id: int, wilayah: str, awal: int, akhir: int, m: MasukanWilayah,
             h: HasilWilayah) -> int:
    k = muat_konteks(conn, putaran_id, wilayah, awal, akhir)
    return tulis_temuan(conn, putaran_id, wilayah, validasi(m, h, k))


def temuan_langsung(conn: Connection, putaran_id: int, wilayah: str
                    ) -> tuple[list[Temuan], MasukanWilayah, HasilWilayah]:
    """Validasi dihitung saat diminta (bukan dari lk.hasil_validasi yang mungkin belum diperbarui worker).

    Dipakai saat AJUKAN/SETUJUI lapus dan syarat KUNCI putaran (F4). Angka resmi (hanya penyesuaian disetujui);
    konfirmasi beralasan (lk.konfirmasi_validasi) ikut diperhitungkan.
    """
    from ..worker.muat import muat  # impor lambat: worker.antrean mengimpor modul ini

    m, pu = muat(conn, putaran_id, wilayah)
    h = hitung_wilayah(m)
    k = muat_konteks(conn, putaran_id, wilayah, pu.awal, pu.akhir)
    return validasi(m, h, k), m, h


def blokir(temuan: list[Temuan], tingkat: str, lapus_id: int | None = None) -> list[Temuan]:
    """Temuan bertingkat `tingkat` yang belum dikonfirmasi (opsional: satu lapus)."""
    return [t for t in temuan if t.tingkat == tingkat and t.dikonfirmasi_oleh is None
            and (lapus_id is None or t.lapus_id == lapus_id)]


def periksa_v15(conn: Connection, putaran_id: int, wilayah: str, m: MasukanWilayah | None = None,
                h: HasilWilayah | None = None) -> list[str]:
    """V15: kode lapus yang hasil tersimpannya berbeda dari hitung ulang (sidik masukan berubah tanpa hitung ulang).

    Seharusnya selalu kosong (hitung otomatis tiap simpan; temuan T3); dipakai saat kunci putaran (F4).
    """
    if m is None or h is None:
        from ..worker.muat import muat  # impor lambat: worker.antrean mengimpor modul ini

        m, _ = muat(conn, putaran_id, wilayah)
        h = hitung_wilayah(m)
    simpan = {r[0]: r[1] for r in conn.execute(text(
        "SELECT DISTINCT ON (lapus_id) lapus_id, hash_input FROM lk.hasil_lapus WHERE putaran_id = :p"
        " AND wilayah_kode = :w ORDER BY lapus_id"), {"p": putaran_id, "w": wilayah})}
    kode = {r.id: r.kode for r in m.pohon}
    beda = {lid for lid, hl in h.lapus.items() if simpan.get(lid) != hl.hash_input}
    beda |= {lid for lid in simpan if lid not in h.lapus}
    return sorted(kode.get(lid, str(lid)) for lid in beda)


def ringkasan_kunci(conn: Connection, putaran_id: int, wilayah: str) -> dict:
    """Temuan yang memblokir kunci putaran: V13/V14 (validasi dihitung saat diminta) + V15 (sidik tersimpan)."""
    ts, m, h = temuan_langsung(conn, putaran_id, wilayah)
    kode = {r.id: (r.kode, r.urutan) for r in m.pohon}
    hasil = [{"kode": t.kode, "kode_lapus": kode.get(t.lapus_id, ("?", 0))[0], "pesan": t.pesan}
             for t in sorted(blokir(ts, "blokir_kunci"), key=lambda t: (kode.get(t.lapus_id, ("", 0))[1], t.kode))]
    v15 = periksa_v15(conn, putaran_id, wilayah, m, h)
    aktif = conn.execute(text("SELECT aktif FROM ref.validasi WHERE kode = 'V15'")).scalar()
    if v15 and aktif:
        hasil.append({"kode": "V15", "kode_lapus": ", ".join(v15),
                      "pesan": "Hasil tersimpan berbeda dari hitung ulang; jalankan hitung ulang."})
    return {"blokir": hasil, "boleh_kunci": not hasil}
