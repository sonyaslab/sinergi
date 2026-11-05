// Bandingkan dua putaran (tahun dasar sama) satu wilayah: NTB FINAL, selisih, laju y-on-y, dan jumlah perubahan
// data dasar / jangkar / adjustment per lapus; klik lapus untuk rincian sel yang berbeda.
import { useEffect, useState } from "react";
import { useDaftar } from "../../api/hooks";
import { Isian, Pilihan, kelasTabel, kelasTd, kelasTh } from "../../components/ui";
import { formatNilai, formatPersen, laju, type Seri } from "../../lib/putaran";
import type { Putaran } from "../DataDasar";

interface BarisBanding {
  id: number;
  kode: string;
  nama: string;
  level: number;
  jenis: string;
  a: Seri;
  b: Seri;
  data: { baru: number; hilang: number; berubah: number };
  jangkar: number;
  penyesuaian: number;
}
interface Banding { a: { nama: string; akhir: number }; b: { nama: string; akhir: number }; periode: { urut: number; label: string }[]; baris: BarisBanding[] }
interface SelBeda { item_id: number; metode: string; nomor: number; nama: string; seri: string; label_periode: string; lama: number | null; baru: number | null }

export function Bandingkan({ putaran, wilayah, semua }: { putaran: Putaran; wilayah: string; semua: Putaran[] }) {
  const lain = semua.filter((p) => p.id !== putaran.id);
  const [a, setA] = useState<number | null>(putaran.sumber_putaran_id ?? lain[0]?.id ?? null);
  useEffect(() => {
    if (a === null || a === putaran.id) setA(putaran.sumber_putaran_id ?? lain[0]?.id ?? null);
  }, [putaran.id, putaran.sumber_putaran_id, a, lain]);
  const q = useDaftar<Banding>(["banding", a, putaran.id, wilayah], a ? `/api/putaran/${a}/banding/${putaran.id}?wilayah=${wilayah}` : null);
  const d = q.data;
  const [u, setU] = useState<number | null>(null);
  const [harga, setHarga] = useState<0 | 1>(1);
  const [detail, setDetail] = useState<BarisBanding | null>(null);
  useEffect(() => {
    // bawaan: triwulan berjalan terakhir yang dimiliki kedua putaran
    if (d && (u === null || !d.periode.some((p) => p.urut === u))) setU(Math.min(d.a.akhir, d.b.akhir));
  }, [d, u]);
  if (!lain.length) return <p className="text-sm text-slate-500">Perlu minimal dua putaran pada tahun dasar ini.</p>;
  const k = String(u);
  return (
    <div>
      <div className="mb-2 flex flex-wrap items-end gap-3">
        <div className="w-64"><Isian label="Putaran pembanding (lama)">
          <Pilihan value={a ?? ""} onChange={(e) => setA(Number(e.target.value))} aria-label="Putaran pembanding">
            {lain.map((p) => <option key={p.id} value={p.id}>{p.nama} · {p.label_akhir}</option>)}
          </Pilihan>
        </Isian></div>
        <div className="w-36"><Isian label="Triwulan">
          <Pilihan value={u ?? ""} onChange={(e) => setU(Number(e.target.value))} aria-label="Triwulan banding">
            {(d?.periode ?? []).slice().reverse().map((p) => <option key={p.urut} value={p.urut}>{p.label}</option>)}
          </Pilihan>
        </Isian></div>
        <div className="w-36"><Isian label="Harga">
          <Pilihan value={harga} onChange={(e) => setHarga(Number(e.target.value) as 0 | 1)} aria-label="Harga banding">
            <option value={1}>NTB ADHK</option><option value={0}>NTB ADHB</option>
          </Pilihan>
        </Isian></div>
        <span className="pb-1.5 text-xs text-slate-500">{d ? `${d.a.nama} → ${d.b.nama}` : ""}</span>
      </div>
      <div className="max-h-[60vh] overflow-auto rounded border border-slate-200 bg-white">
        <table className={kelasTabel}>
          <thead><tr>{["Lapus", "Lama", "Baru", "Selisih %", "Laju y-on-y lama", "Laju y-on-y baru", "Sel data (+/−/≠)", "Jangkar", "Adjustment"].map((h) => <th key={h} className={kelasTh}>{h}</th>)}</tr></thead>
          <tbody>
            {(d?.baris ?? []).map((b) => {
              const x = b.a[k]?.[harga];
              const y = b.b[k]?.[harga];
              const beda = b.data.baru + b.data.hilang + b.data.berubah + b.jangkar + b.penyesuaian;
              return (
                <tr key={b.id} className={b.jenis === "kategori" ? "font-semibold" : ""}>
                  <td className={kelasTd} style={{ paddingLeft: 8 + 12 * Math.max(0, b.level - 1) }} title={b.nama}>
                    {beda ? <button type="button" className="text-merek-700 hover:underline" onClick={() => setDetail(b)}>{b.kode}</button> : b.kode}
                  </td>
                  <td className={`${kelasTd} text-right tabular-nums`}>{formatNilai(x)}</td>
                  <td className={`${kelasTd} text-right tabular-nums`}>{formatNilai(y)}</td>
                  <td className={`${kelasTd} text-right tabular-nums`}>{x !== undefined && y !== undefined && x !== 0 ? formatPersen((y / x) * 100 - 100) : ""}</td>
                  <td className={`${kelasTd} text-right tabular-nums`}>{u !== null ? formatPersen(laju(b.a, u, harga)) : ""}</td>
                  <td className={`${kelasTd} text-right tabular-nums`}>{u !== null ? formatPersen(laju(b.b, u, harga)) : ""}</td>
                  <td className={kelasTd}>{b.data.baru + b.data.hilang + b.data.berubah ? `${b.data.baru}/${b.data.hilang}/${b.data.berubah}` : ""}</td>
                  <td className={kelasTd}>{b.jangkar || ""}</td>
                  <td className={kelasTd}>{b.penyesuaian || ""}</td>
                </tr>
              );
            })}
            {!d && <tr><td className={kelasTd} colSpan={9}>{q.isLoading ? "Memuat…" : ""}</td></tr>}
          </tbody>
        </table>
      </div>
      {detail && a && <RincianSel a={a} b={putaran.id} wilayah={wilayah} lapus={detail} />}
    </div>
  );
}

function RincianSel({ a, b, wilayah, lapus }: { a: number; b: number; wilayah: string; lapus: BarisBanding }) {
  const q = useDaftar<SelBeda[]>(["banding-data", a, b, wilayah, lapus.id], `/api/putaran/${a}/banding/${b}/data?wilayah=${wilayah}&lapus_id=${lapus.id}`);
  return (
    <div className="mt-3">
      <h3 className="mb-1 text-sm font-semibold">Sel data dasar berbeda: {lapus.kode}</h3>
      <div className="max-h-64 overflow-auto rounded border border-slate-200 bg-white">
        <table className={kelasTabel}>
          <thead><tr>{["Item", "Seri", "Triwulan", "Lama", "Baru"].map((h) => <th key={h} className={kelasTh}>{h}</th>)}</tr></thead>
          <tbody>
            {(q.data ?? []).map((s, i) => (
              <tr key={i}><td className={kelasTd}>{s.metode} {s.nomor} {s.nama}</td><td className={kelasTd}>{s.seri}</td><td className={kelasTd}>{s.label_periode}</td>
                <td className={`${kelasTd} text-right tabular-nums`}>{formatNilai(s.lama)}</td><td className={`${kelasTd} text-right tabular-nums`}>{formatNilai(s.baru)}</td></tr>
            ))}
            {!q.data?.length && <tr><td className={kelasTd} colSpan={5}>{q.isLoading ? "Memuat…" : "Data dasar sama (perbedaan pada jangkar/adjustment)."}</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  );
}
