"""Uji unit pemetaan galat basis data -> HTTP (P0423 -> 423, 42501 -> 403) tanpa membocorkan nilai."""
from __future__ import annotations

import types

from sqlalchemy.exc import DBAPIError

from sinergi_api.app.galat import petakan_db


def _galat(sqlstate: str, pesan: str = "", constraint: str | None = None) -> DBAPIError:
    orig = Exception(pesan)
    orig.sqlstate = sqlstate  # type: ignore[attr-defined]
    orig.diag = types.SimpleNamespace(message_primary=pesan, constraint_name=constraint)  # type: ignore[attr-defined]
    return DBAPIError("stmt", {}, orig)


def test_putaran_terkunci_423():
    g = petakan_db(_galat("P0423", "Putaran 9 terkunci"))
    assert g.status == 423 and g.kode == "PUTARAN_TERKUNCI"


def test_rls_403():
    g = petakan_db(_galat("42501", 'new row violates row-level security policy for table "item"'))
    assert g.status == 403 and "item" not in g.pesan


def test_pesan_trigger_diteruskan_constraint_generik_tidak():
    g = petakan_db(_galat("23514", "Alasan penyesuaian wajib diisi (min. 10 karakter)"))
    assert g.status == 422 and g.pesan.startswith("Alasan penyesuaian wajib")
    g = petakan_db(_galat("23514", 'new row for relation "nilai_item" violates check constraint "x"', "x"))
    assert g.status == 422 and "nilai_item" not in g.pesan


def test_galat_lain_500_tanpa_rincian():
    g = petakan_db(_galat("22003", "numeric field overflow 123456789.123"))
    assert g.status == 500 and "123456789" not in g.pesan
