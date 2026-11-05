"""Golden sintetis: mesin produksi vs engine_ref (oracle) pada wilayah acak, toleransi relatif 1e-9.

Selalu dijalankan (tidak butuh data rahasia). Mencakup semua tahap (item, PR/PRE metode, PRE/POST/BENC/FINAL lapus,
agregat BENC/FINAL), TD2025 (jangkar dari data) dan pola TD2010 (jangkar parameter, baseline EKS 2024).
"""
from __future__ import annotations

import pytest
from engine_ref import kompilasi as kp

from sinergi_api.engine import hitung_wilayah

from .acak import wilayah
from .adaptor import URUT0, ke_masukan, selisih_relatif

pytestmark = pytest.mark.golden
TOL = 1e-9
SEED = range(60)


def _maks(prod, ref, sb, awal, akhir) -> float:
    w = 0.0
    for a in ("out_cp", "gva_cp", "out_k", "gva_k"):
        x, y = getattr(prod, a), getattr(ref, a)
        for u in range(awal, akhir + 1):
            w = max(w, selisih_relatif(x[sb.i(u)], y[u - URUT0]))
    return w


def _ref_item(t4):
    class H:
        out_cp, gva_cp, out_k, gva_k = t4
    return H


@pytest.mark.parametrize("seed", SEED)
def test_mesin_identik_oracle(seed):
    spec = wilayah(seed)
    ref = kp.hitung_wilayah(spec)
    hasil = hitung_wilayah(ke_masukan(spec))
    sb, a, b = hasil.sumbu, spec["awal"], spec["akhir"]
    assert set(hasil.lapus) == set(ref), "himpunan lapus berhasil harus sama"
    n_banding = 0
    for lid, r in ref.items():
        h = hasil.lapus[lid]
        for th in ("pre", "post", "benc", "final"):
            if th in r:
                assert _maks(h.tahap[th.upper()], r[th], sb, a, b) <= TOL, (seed, lid, th)
                n_banding += 1
        for m, (pr, pre) in r.get("metode", {}).items():
            assert _maks(h.metode[m][0], pr, sb, a, b) <= TOL, (seed, lid, m, "PR")
            assert _maks(h.metode[m][1], pre, sb, a, b) <= TOL, (seed, lid, m, "PRE")
        for iid, t4 in r.get("item", {}).items():
            assert _maks(h.item[iid], _ref_item(t4), sb, a, b) <= TOL, (seed, lid, iid)
        assert len(h.hash_input) == 64
    assert n_banding > 10


def test_cakupan_acak():
    """Pembangkit benar-benar mencakup fitur yang diuji."""
    fitur = set()
    for s in SEED:
        spec = wilayah(s)
        fitur.add("td2010" if not spec["jangkar_dari_data"] else "td2025")
        for d in spec["data"].values():
            for it in d["item"]:
                fitur.add(it["metode"])
                fitur.update(t.get("rumus") or t["sumber"] for t in it["tautan"])
                if it.get("mulai"):
                    fitur.add("masa")
            fitur.update(a["tahap"] for a in d["penyesuaian"])
    assert {"td2010", "td2025", "REV", "EKS", "DEF", "PDK", "masa", "METODE", "REKON", "SIMULASI", "SERI_REFERENSI",
            "HASIL_LAPUS", "TPK_X_KAMAR", "JANGKAR_X_IH_100", "KAPITA_X_PENDUDUK_X_3", "MARGIN_X_OUTPUT",
            "MARGIN_X_IMPOR"} <= fitur
