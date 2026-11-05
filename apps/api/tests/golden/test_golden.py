"""Golden test pada data LK Put 0 (folder golden/ hanya di mesin internal; dilewati bila tidak ada).

    make golden                    # atau: SINERGI_GOLDEN=/jalur/golden make golden

Kriteria F2: mesin produksi identik dengan engine_ref (relatif ≤ 1e-9) untuk setiap lapus LK 01 dan templat terisi;
hasil simpan LK 01 identik (≤ 1e-6, seperti tools/validasi_engine_vs_lk.py) kecuali lapus `tersimpan_usang` (B.3,
temuan T3); templat terisi = LK 01 untuk `harap_identik` lapus (72). Isi folder: lihat tests/golden/periksa.py.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from . import periksa as pk

GOLDEN = Path(os.environ.get("SINERGI_GOLDEN") or Path(__file__).resolve().parents[4] / "golden")
pytestmark = [pytest.mark.golden,
              pytest.mark.skipif(not GOLDEN.is_dir(), reason="folder golden/ tidak ada (data rahasia, mesin internal)")]


def _manifest() -> dict:
    return pk.baca_manifest(GOLDEN)


def _lk() -> list[Path]:
    m = _manifest()
    if m.get("lk01"):
        return sorted({GOLDEN / b for b in m["lk01"].values()})
    return sorted(GOLDEN.rglob("*.xlsm"))


def _templat() -> Path | None:
    m = _manifest()
    if m.get("templat_td2025"):
        return GOLDEN / m["templat_td2025"]
    xs = sorted(GOLDEN.glob("*TD2025*TERISI*.xlsx"))
    return xs[0] if xs else None


def test_lk01_mesin_identik_engine_ref():
    berkas = _lk()
    if not berkas:
        pytest.skip("tidak ada berkas LK 01 (.xlsm) di golden/")
    m = _manifest()
    awal, akhir = pk.rentang(m)
    for b in berkas:
        lap = pk.lk01_vs_oracle(b, str(m.get("wilayah", "6500")), awal, akhir)
        assert not lap.beda, lap.ringkas()


def test_lk01_identik_hasil_simpan():
    m = _manifest()
    if not m.get("lk01"):
        pytest.skip("manifest.json tanpa peta lk01 (rekap LK 02)")
    lap = pk.lk01_vs_tersimpan(GOLDEN, m, *pk.rentang(m))
    assert not lap.beda, lap.ringkas()


def test_templat_mesin_identik_engine_ref():
    t = _templat()
    if t is None:
        pytest.skip("tidak ada templat TD2025 TERISI di golden/")
    m = _manifest()
    lap = pk.templat_vs_oracle(t, str(m.get("wilayah", "6500")), *pk.rentang(m))
    assert not lap.beda and lap.identik, lap.ringkas()


def test_templat_identik_lk01_72_lapus():
    m = _manifest()
    if not (m.get("lk01") and _templat()):
        pytest.skip("butuh manifest lk01 dan templat TD2025 TERISI")
    m.setdefault("templat_td2025", _templat().name)  # type: ignore[union-attr]
    lap = pk.templat_vs_lk(GOLDEN, m, *pk.rentang(m))
    assert not lap.beda, lap.ringkas()
    assert len(lap.identik) >= int(m.get("harap_identik", len(lap.identik))), lap.ringkas()
