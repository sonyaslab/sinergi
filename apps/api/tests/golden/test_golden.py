"""Golden test mesin produksi vs engine_ref pada data LK Put 0 (folder golden/ hanya di mesin internal).

Diisi pada fase F2. Tanpa folder golden/ uji ini dilewati (bukan gagal), karena data bersifat rahasia.
"""
from __future__ import annotations

from pathlib import Path

import pytest

GOLDEN = Path(__file__).resolve().parents[4] / "golden"

pytestmark = pytest.mark.golden


@pytest.mark.skipif(not GOLDEN.is_dir(), reason="folder golden/ tidak ada (data rahasia, hanya di mesin internal)")
def test_golden_belum_tersedia():
    pytest.skip("Mesin produksi (apps/api/engine) dibangun di F2.")
