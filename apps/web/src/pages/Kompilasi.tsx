// Layar Kompilasi & Simulasi (F4): semua baris pohon (format tetap) × triwulan; simulasi NTB ADHK (target laju) dan
// ADHB (target implisit) hanya pada lapus berdata; agregat = jumlah lapus berdata (docs/02 §6). Izin simulasi.edit.
import { useMemo, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { api, GalatApi } from "../api/klien";
import { useDaftar, useIzin } from "../api/hooks";
import { DialogPenyesuaian } from "../components/DialogPenyesuaian";
import { PemilihPutaran, usePilihanPutaran } from "../components/PemilihPutaran";
import { Centang, Isian, Lencana, Pesan, Pilihan, Tombol, kelasTabel, kelasTd, kelasTh } from "../components/ui";
import { labelPeriode } from "../lib/dataDasar";
import { formatNilai, formatPersen, implisit, laju, type Seri } from "../lib/putaran";

interface BarisKompilasi { id: number; kode: string; nama: string; level: number; jenis: string; berdata: boolean; benc: Seri; final: Seri }
interface Sim { id: number; lapus_id: number; harga: "CP" | "K"; periode: number; nilai: number; status: string }
interface DataKompilasi {
  putaran: { id: number; status: string; awal: number; akhir: number };
  periode: { urut: number; label: string }[];
  pratinjau: boolean;
  baris: BarisKompilasi[];
  simulasi: Sim[];
  antrean: number;
}
type Tampilan = "ntb_k" | "ntb_cp" | "laju_k" | "implisit";
const LABEL_TAMPILAN: Record<Tampilan, string> = {
  ntb_k: "NTB ADHK", ntb_cp: "NTB ADHB", laju_k: "Laju y-on-y ADHK (%)", implisit: "Indeks implisit",
};

/** Nilai satu sel tampilan dari seri [NTB ADHB, NTB ADHK] per triwulan. */
export function nilaiTampilan(s: Seri, u: number, t: Tampilan): number | null {
  const x = s[String(u)];
  if (!x) return null;
  if (t === "ntb_cp") return x[0];
  if (t === "ntb_k") return x[1];
  if (t === "laju_k") return laju(s, u, 1);
  return implisit(x[0], x[1]);
}

export function Kompilasi() {
  const pil = usePilihanPutaran();
  const { td, put, wil } = pil;
  const qc = useQueryClient();
  const izin = useIzin();
  const [tampilan, setTampilan] = useState<Tampilan>("laju_k");
  const [sumber, setSumber] = useState<"final" | "benc">("final");
  const [pratinjau, setPratinjau] = useState(false);
  const [semua, setSemua] = useState(false);
  const [sim, setSim] = useState<{ b: BarisKompilasi; u: number } | null>(null);
  const [pesan, setPesan] = useState<{ jenis: "ok" | "galat"; teks: string } | null>(null);
  const q = useDaftar<DataKompilasi>(["kompilasi", put?.id, wil, pratinjau], put ? `/api/kompilasi?putaran_id=${put.id}&wilayah=${wil}&pratinjau=${pratinjau}` : null);
  const d = q.data;
  const simPer = useMemo(() => {
    const m = new Map<string, Sim[]>();
    for (const s of d?.simulasi ?? []) m.set(`${s.lapus_id}:${s.periode}`, [...(m.get(`${s.lapus_id}:${s.periode}`) ?? []), s]);
    return m;
  }, [d]);
  if (!td) return <p className="text-slate-500">Memuat tahun dasar…</p>;
  const periode = d ? (semua ? d.periode : d.periode.slice(-8)) : [];
  const menunggu = (d?.simulasi ?? []).filter((s) => s.status === "draf" || s.status === "diajukan").length;
  const terkunci = put?.status === "terkunci";
  const bolehSim = izin.has("simulasi.edit") && !terkunci;

  async function setujui() {
    if (!put) return;
    setPesan(null);
    try {
      const r = await api<{ pesan: string }>("/api/simulasi/setujui", { metode: "POST", isi: { putaran_id: put.id, wilayah: wil } });
      setPesan({ jenis: "ok", teks: r.pesan });
      qc.invalidateQueries({ queryKey: ["kompilasi"] });
    } catch (e) {
      setPesan({ jenis: "galat", teks: e instanceof GalatApi ? e.message : "Gagal menyetujui simulasi." });
    }
  }

  return (
    <div>
      <h1 className="mb-2 text-xl font-semibold">Kompilasi & Simulasi</h1>
      <PemilihPutaran p={pil} />
      <div className="mb-3 flex flex-wrap items-end gap-3">
        <div className="w-56"><Isian label="Tampilan">
          <Pilihan value={tampilan} onChange={(e) => setTampilan(e.target.value as Tampilan)} aria-label="Tampilan">
            {Object.entries(LABEL_TAMPILAN).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </Pilihan>
        </Isian></div>
        <div className="w-48"><Isian label="Tahap">
          <Pilihan value={sumber} onChange={(e) => setSumber(e.target.value as "final" | "benc")} aria-label="Tahap">
            <option value="final">FINAL (setelah simulasi)</option><option value="benc">Kompilasi (BENC)</option>
          </Pilihan>
        </Isian></div>
        <Centang label="Pratinjau (ikut draf)" checked={pratinjau} onChange={(e) => setPratinjau(e.target.checked)} />
        <Centang label="Semua triwulan" checked={semua} onChange={(e) => setSemua(e.target.checked)} />
        {izin.has("penyesuaian.putus") && !terkunci && <Tombol varian="utama" disabled={!menunggu} onClick={setujui}>Setujui simulasi ({menunggu})</Tombol>}
        {d && d.antrean > 0 && <Lencana warna="kuning">Menghitung ulang…</Lencana>}
      </div>
      {pratinjau && <div className="mb-2 rounded border-2 border-dashed border-amber-400 bg-amber-50 px-3 py-1.5 text-sm font-semibold text-amber-800" role="status">PRATINJAU – belum resmi</div>}
      {pesan && <div className="mb-2"><Pesan jenis={pesan.jenis}>{pesan.teks}</Pesan></div>}
      <p className="mb-1 text-xs text-slate-500">{bolehSim ? "Klik sel lapus berdata untuk mengisi simulasi. " : ""}Sel berwarna: simulasi disetujui (hijau) atau draf (kuning).</p>
      <div className="max-h-[68vh] overflow-auto rounded border border-slate-200 bg-white">
        <table className={kelasTabel}>
          <thead className="sticky top-0"><tr><th className={kelasTh}>Lapangan usaha</th>{periode.map((p) => <th key={p.urut} className={`${kelasTh} text-right`}>{p.label}</th>)}</tr></thead>
          <tbody>
            {(d?.baris ?? []).map((b) => (
              <tr key={b.id} className={b.jenis === "kategori" || ["ntb", "pdrb", "pdrb_nonmigas"].includes(b.jenis) ? "font-semibold" : b.jenis === "kelompok" ? "italic text-slate-600" : ""}>
                <td className={`${kelasTd} whitespace-nowrap`} style={{ paddingLeft: 8 + 12 * Math.max(0, b.level - 1) }} title={b.nama}>{b.kode} <span className="font-normal text-slate-500">{b.nama.length > 38 ? `${b.nama.slice(0, 38)}…` : b.nama}</span></td>
                {periode.map((p) => {
                  const s = simPer.get(`${b.id}:${p.urut}`) ?? [];
                  const warna = s.some((x) => x.status === "draf" || x.status === "diajukan") ? "bg-amber-100" : s.some((x) => x.status === "disetujui") ? "bg-green-100" : "";
                  const v = nilaiTampilan(sumber === "final" ? b.final : b.benc, p.urut, tampilan);
                  const isi = tampilan === "laju_k" || tampilan === "implisit" ? formatPersen(v) : formatNilai(v);
                  return (
                    <td key={p.urut} className={`${kelasTd} text-right tabular-nums ${warna}`}>
                      {b.berdata && bolehSim ? <button type="button" className="w-full text-right hover:underline" aria-label={`Simulasi ${b.kode} ${p.label}`} onClick={() => setSim({ b, u: p.urut })}>{isi || "·"}</button> : isi}
                    </td>
                  );
                })}
              </tr>
            ))}
            {!d && <tr><td className={kelasTd}>{q.isLoading ? "Memuat…" : "Pilih putaran."}</td></tr>}
          </tbody>
        </table>
      </div>
      {sim && put && (
        <DialogPenyesuaian putaran={put} wilayah={wil} lapus={[{ id: sim.b.id, kode: sim.b.kode, nama: sim.b.nama }]} tahapBoleh={["SIMULASI"]}
          awal={{ periode: sim.u, harga: "K" }}
          info={<InfoSel b={sim.b} u={sim.u} sim={simPer.get(`${sim.b.id}:${sim.u}`) ?? []} />}
          tutup={() => setSim(null)}
          selesai={(t) => { setSim(null); setPesan({ jenis: "ok", teks: t }); qc.invalidateQueries({ queryKey: ["kompilasi"] }); }} />
      )}
    </div>
  );
}

function InfoSel({ b, u, sim }: { b: BarisKompilasi; u: number; sim: Sim[] }) {
  const bn = b.benc[String(u)];
  const fn = b.final[String(u)];
  return (
    <div className="rounded border border-slate-200 bg-slate-50 p-2 text-xs" aria-label="Angka sel simulasi">
      <div className="font-semibold">{b.kode} · {labelPeriode(u)}</div>
      <div>Kompilasi (BENC): ADHB {formatNilai(bn?.[0])} · ADHK {formatNilai(bn?.[1])} · laju y-on-y {formatPersen(laju(b.benc, u, 1))}% · implisit {formatPersen(implisit(bn?.[0], bn?.[1]))}</div>
      <div>FINAL: ADHB {formatNilai(fn?.[0])} · ADHK {formatNilai(fn?.[1])} · laju y-on-y {formatPersen(laju(b.final, u, 1))}% · implisit {formatPersen(implisit(fn?.[0], fn?.[1]))}</div>
      {sim.map((s) => <div key={s.id}>SIM {s.harga === "CP" ? "ADHB" : "ADHK"}: {formatNilai(s.nilai)} ({s.status})</div>)}
    </div>
  );
}
