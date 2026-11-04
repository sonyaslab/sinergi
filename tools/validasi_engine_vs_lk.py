"""
Validasi: hitung ulang tiap industri dari lembar DATA_REV/EKS/DEF dengan engine_ref,
lalu bandingkan dengan lembar hasil simpan {wil}_{industri} (OUT/GVA ADHB & ADHK BENC).

Pemakaian (di mesin internal):
    python tools/validasi_engine_vs_lk.py "01 LK PDRB Triwulanan TD2025 ... .xlsm" [6500] [Q1-2019] [Q2-2026]
Keluaran hanya selisih/indikator kecocokan (tanpa mencetak angka mentah).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from engine_ref.lk_engine import hitung_industri, label, t_of  # noqa: E402
from tools.lk_xlsm_reader import baca_lk, adj_rekon_dari_tersimpan  # noqa: E402


def main(path, wil="6500", awal="Q1-2019", akhir="Q2-2026"):
    q0, y0 = awal[1], int(awal[3:]); q1, y1 = akhir[1], int(akhir[3:])
    t_awal, t_akhir = t_of(y0, int(q0)), t_of(y1, int(q1))
    per_ind, tersimpan = baca_lk(path, wil)
    print(f"{'industri':<8} {'n_item(R/E/D)':<14} {'periode':>7} {'cocok':>6} {'maks_sel_rel':>12}  periode_terburuk")
    ringkas = []
    for ind in sorted(tersimpan):
        d = per_ind.get(ind)
        if d is None:
            continue
        rec = tersimpan[ind]
        res = hitung_industri(list(d["rev"].values()), list(d["eks"].values()), list(d["def"].values()),
                              d["adj"]["rev"], d["adj"]["eks"], d["adj"]["def"], adj_rekon_dari_tersimpan(rec))
        n = ok = 0; worst = (0.0, None)
        for kode, ser in (("OUT.CP.BENC", res.out_cp), ("GVA.CP.BENC", res.gva_cp),
                          ("OUT.FBY.BENC", res.out_k), ("GVA.FBY.BENC", res.gva_k)):
            ref = rec.get(kode, {})
            for t in range(t_awal, t_akhir + 1):
                a = ser[t]; b = ref.get(t, 0.0) or 0.0
                n += 1
                rel = abs(a - b) / max(abs(b), 1.0)
                if rel < 1e-6:
                    ok += 1
                elif rel > worst[0]:
                    worst = (rel, f"{kode}@{label(t)}")
        cnt = f"{len(d['rev'])}/{len(d['eks'])}/{len(d['def'])}"
        print(f"{ind:<8} {cnt:<14} {n:>7} {ok/n*100:>5.1f}% {worst[0]:>12.2e}  {worst[1] or '-'}")
        ringkas.append((ind, ok == n))
    tot = len(ringkas); cocok = sum(1 for _, x in ringkas if x)
    print(f"\nIndustri cocok 100%: {cocok}/{tot}")


if __name__ == "__main__":
    main(*sys.argv[1:])
