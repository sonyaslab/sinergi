// Layar LK Hitung NTB (F4): per lapus berdata — PR → PRE → POST → BENC → FINAL per metode dan item, laju, rasio KA,
// panel data kurang (validasi), adjustment lapus, ajukan. Sakelar pratinjau menghitung draf/diajukan di memori saja
// (tidak disimpan; label "PRATINJAU – belum resmi"; keputusan 8a).
import { useEffect, useMemo, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { api, GalatApi } from "../api/klien";
import { useDaftar, useIzin } from "../api/hooks";
import type { Lapus } from "../api/tipe";
import { DialogPenyesuaian, type Tahap } from "../components/DialogPenyesuaian";
import { PemilihPutaran, usePilihanPutaran } from "../components/PemilihPutaran";
import { Centang, Isian, Lencana, Pesan, Pilihan, Tombol, kelasTabel, kelasTd, kelasTh } from "../components/ui";
import { LABEL_TINGKAT, labelPeriode, type Temuan } from "../lib/dataDasar";
import { aksiTersedia, formatNilai, formatPersen, LABEL_STATUS, laju, WARNA_STATUS, type Seri, type StatusLapus } from "../lib/putaran";
import type { Adj } from "./putaran/DaftarPenyesuaian";

interface ItemHasil { id: number; metode: string; nomor: number; nama: string; status: string; nilai: Seri }
interface HasilLapus {
  putaran: { id: number; status: string; awal: number; akhir: number };
  lapus: { id: number; kode: string; nama: string; jenis: string };
  periode: { urut: number; label: string }[];
  pratinjau: boolean;
  tahap: Record<string, Seri>;
  metode: Record<string, { pr: Seri; pre: Seri }>;
  item: ItemHasil[];
  status: StatusLapus;
  validasi: (Temuan & { dikonfirmasi: boolean })[];
  boleh_tulis: boolean;
}

const BERDATA = ["daun", "top", "sop"];

/** Daftar lapus berdata di bawah satu akar (urut pohon). */
export function lapusBerdataDi(lapus: Lapus[], akar: number): Lapus[] {
  const anak = new Map<number, Lapus[]>();
  for (const l of lapus) if (l.induk_id !== null && l.aktif) anak.set(l.induk_id, [...(anak.get(l.induk_id) ?? []), l]);
  const out: Lapus[] = [];
  const turun = (l: Lapus) => {
    if (BERDATA.includes(l.jenis)) out.push(l);
    for (const a of (anak.get(l.id) ?? []).sort((x, y) => x.urutan - y.urutan)) turun(a);
  };
  const r = lapus.find((l) => l.id === akar);
  if (r) turun(r);
  return out;
}

export function LkHitung() {
  const pil = usePilihanPutaran();
  const { td, put, wil } = pil;
  const qc = useQueryClient();
  const izin = useIzin();
  const qLapus = useDaftar<Lapus[]>(["lapus", td?.id], td ? `/api/tahun-dasar/${td.id}/lapus` : null).data;
  const lapus = useMemo(() => qLapus ?? [], [qLapus]);
  const akar = useMemo(() => lapus.filter((l) => l.aktif && l.induk_id === null && ["kategori", ...BERDATA].includes(l.jenis)), [lapus]);
  const [kat, setKat] = useState<number | null>(null);
  useEffect(() => {
    if (akar.length && !akar.some((a) => a.id === kat)) setKat(akar[0].id);
  }, [akar, kat]);
  const pilihan = useMemo(() => (kat ? lapusBerdataDi(lapus, kat) : []), [lapus, kat]);
  const [lid, setLid] = useState<number | null>(null);
  useEffect(() => {
    if (pilihan.length && !pilihan.some((l) => l.id === lid)) setLid(pilihan[0].id);
  }, [pilihan, lid]);
  const [pratinjau, setPratinjau] = useState(false);
  const [harga, setHarga] = useState<"CP" | "K">("K");
  const [semua, setSemua] = useState(false);
  const [tambah, setTambah] = useState(false);
  const [pesan, setPesan] = useState<{ jenis: "ok" | "galat"; teks: string; rincian?: string[] } | null>(null);
  const siap = put && lid;
  const kunciHasil = ["hasil-lapus", put?.id, wil, lid, pratinjau];
  const q = useDaftar<HasilLapus>(kunciHasil, siap ? `/api/hasil/lapus/${lid}?putaran_id=${put.id}&wilayah=${wil}&pratinjau=${pratinjau}` : null);
  const qAdj = useDaftar<Adj[]>(["penyesuaian", put?.id, wil, "lapus", lid], siap ? `/api/penyesuaian?putaran_id=${put.id}&wilayah=${wil}&lapus_id=${lid}` : null);
  const d = q.data;

  if (!td) return <p className="text-slate-500">Memuat tahun dasar…</p>;
  const periode = d ? (semua ? d.periode : d.periode.slice(-8)) : [];
  const [io, in_] = harga === "CP" ? [0, 1] : [2, 3];
  const sel = (s: Seri | undefined, u: number, i: number) => s?.[String(u)]?.[i];
  const terkunci = put?.status === "terkunci";
  const lap = lapus.find((l) => l.id === lid);
  const aksi = d && lap ? aksiTersedia({ id: lap.id, kode: lap.kode, nama: lap.nama, jenis: lap.jenis, status: d.status,
    jumlah_item: d.item.length, boleh_tulis: d.boleh_tulis }, izin, terkunci) : [];
  const tahapBoleh: Tahap[] = (izin.has("penyesuaian.usul") || izin.has("penyesuaian.putus")) ? ["METODE", "REKON"] : [];

  async function ajukan() {
    if (!put || !lid) return;
    setPesan(null);
    try {
      const r = await api<{ pesan: string }>(`/api/status/${lid}/ajukan`, { metode: "POST", isi: { putaran_id: put.id, wilayah: wil } });
      setPesan({ jenis: "ok", teks: r.pesan });
      qc.invalidateQueries({ queryKey: ["hasil-lapus"] });
    } catch (e) {
      const rincian = e instanceof GalatApi && Array.isArray(e.rincian) ? (e.rincian as { kode: string; pesan: string }[]).map((x) => `${x.kode}: ${x.pesan}`) : undefined;
      setPesan({ jenis: "galat", teks: e instanceof GalatApi ? e.message : "Gagal mengajukan.", rincian });
    }
  }

  const baris: { label: string; s: Seri | undefined; i: number; tebal?: boolean; jenis?: "laju" | "rasio" }[] = [];
  if (d) {
    for (const [m, x] of Object.entries(d.metode)) {
      baris.push({ label: `${m} · PR output`, s: x.pr, i: io }, { label: `${m} · PR NTB`, s: x.pr, i: in_ },
        { label: `${m} · PRE output`, s: x.pre, i: io }, { label: `${m} · PRE NTB`, s: x.pre, i: in_ });
    }
    for (const t of ["PRE", "POST", "BENC", "FINAL"]) {
      baris.push({ label: `${t} output`, s: d.tahap[t], i: io, tebal: t === "BENC" }, { label: `${t} NTB`, s: d.tahap[t], i: in_, tebal: t === "BENC" });
    }
    baris.push({ label: "Rasio KA BENC (1 − NTB/Output)", s: d.tahap.BENC, i: -1, jenis: "rasio" },
      { label: "Laju y-on-y NTB BENC (%)", s: d.tahap.BENC, i: in_, jenis: "laju" },
      { label: "Laju y-on-y NTB FINAL (%)", s: d.tahap.FINAL, i: in_, jenis: "laju" });
  }
  const isiSel = (b: (typeof baris)[number], u: number) => {
    if (b.jenis === "laju") return formatPersen(laju(b.s ?? {}, u, b.i));
    if (b.jenis === "rasio") {
      const o = sel(b.s, u, io);
      const n = sel(b.s, u, in_);
      return o ? formatPersen(1 - (n ?? 0) / o) : "";
    }
    return formatNilai(sel(b.s, u, b.i));
  };
  const akhir = d?.periode[d.periode.length - 1]?.urut;
  const totalOut = akhir !== undefined ? d?.item.reduce((a, it) => a + (sel(it.nilai, akhir, io) ?? 0), 0) ?? 0 : 0;

  return (
    <div>
      <h1 className="mb-2 text-xl font-semibold">LK Hitung NTB</h1>
      <PemilihPutaran p={pil} />
      <div className="mb-3 flex flex-wrap items-end gap-3">
        <div className="w-64"><Isian label="Kategori">
          <Pilihan value={kat ?? ""} onChange={(e) => setKat(Number(e.target.value))} aria-label="Kategori">
            {akar.map((a) => <option key={a.id} value={a.id}>{a.kode} — {a.nama}</option>)}
          </Pilihan>
        </Isian></div>
        <div className="w-72"><Isian label="Lapus">
          <Pilihan value={lid ?? ""} onChange={(e) => setLid(Number(e.target.value))} aria-label="Lapus">
            {pilihan.map((l) => <option key={l.id} value={l.id}>{l.kode} — {l.nama}</option>)}
          </Pilihan>
        </Isian></div>
        <div className="w-32"><Isian label="Harga">
          <Pilihan value={harga} onChange={(e) => setHarga(e.target.value as "CP" | "K")} aria-label="Harga">
            <option value="K">ADHK</option><option value="CP">ADHB</option>
          </Pilihan>
        </Isian></div>
        <Centang label="Pratinjau (ikut draf/diajukan)" checked={pratinjau} onChange={(e) => setPratinjau(e.target.checked)} />
        <Centang label="Semua triwulan" checked={semua} onChange={(e) => setSemua(e.target.checked)} />
      </div>
      {pratinjau && <div className="mb-2 rounded border-2 border-dashed border-amber-400 bg-amber-50 px-3 py-1.5 text-sm font-semibold text-amber-800" role="status">PRATINJAU – belum resmi (dihitung di memori, tidak disimpan, tidak masuk tabel pokok)</div>}
      {d && (
        <div className="mb-2 flex flex-wrap items-center gap-2">
          <span className="text-sm">Status lapus:</span> <Lencana warna={WARNA_STATUS[d.status]}>{LABEL_STATUS[d.status]}</Lencana>
          {aksi.includes("ajukan") && <Tombol varian="utama" onClick={ajukan}>Ajukan</Tombol>}
          {!terkunci && tahapBoleh.length > 0 && <Tombol onClick={() => setTambah(true)}>+ Adjustment</Tombol>}
        </div>
      )}
      {pesan && (
        <div className="mb-2"><Pesan jenis={pesan.jenis}>{pesan.teks}
          {pesan.rincian && <ul className="mt-1 list-disc pl-5 text-xs">{pesan.rincian.map((r, i) => <li key={i}>{r}</li>)}</ul>}
        </Pesan></div>
      )}
      {q.isLoading && <p className="text-sm text-slate-500">Memuat hasil…</p>}
      {q.isError && <Pesan jenis="galat">{q.error instanceof GalatApi ? q.error.message : "Gagal memuat hasil."}</Pesan>}
      {d && (
        <div className="grid gap-3 2xl:grid-cols-[1fr_340px]">
          <div className="space-y-3">
            <div className="overflow-auto rounded border border-slate-200 bg-white">
              <table className={kelasTabel} aria-label="Ringkasan tahap">
                <thead><tr><th className={kelasTh}>{harga === "CP" ? "ADHB" : "ADHK"}</th>{periode.map((p) => <th key={p.urut} className={`${kelasTh} text-right`}>{p.label}</th>)}</tr></thead>
                <tbody>
                  {baris.map((b) => (
                    <tr key={b.label} className={b.tebal ? "font-semibold" : b.jenis ? "text-slate-600" : ""}>
                      <td className={`${kelasTd} whitespace-nowrap`}>{b.label}</td>
                      {periode.map((p) => <td key={p.urut} className={`${kelasTd} text-right tabular-nums`}>{isiSel(b, p.urut)}</td>)}
                    </tr>
                  ))}
                  {!Object.keys(d.tahap).length && <tr><td className={kelasTd} colSpan={periode.length + 1}>Belum ada hasil hitung (tambahkan item atau tunggu hitung otomatis).</td></tr>}
                </tbody>
              </table>
            </div>
            <div className="overflow-auto rounded border border-slate-200 bg-white">
              <table className={kelasTabel} aria-label="Output per item">
                <thead><tr><th className={kelasTh}>Item (output {harga === "CP" ? "ADHB" : "ADHK"})</th>{periode.map((p) => <th key={p.urut} className={`${kelasTh} text-right`}>{p.label}</th>)}<th className={`${kelasTh} text-right`}>Kontribusi {akhir !== undefined ? labelPeriode(akhir) : ""}</th></tr></thead>
                <tbody>
                  {d.item.map((it) => (
                    <tr key={it.id} className={it.status === "nonaktif" ? "text-slate-400" : ""}>
                      <td className={`${kelasTd} whitespace-nowrap`}>{it.metode} {it.nomor} · {it.nama}</td>
                      {periode.map((p) => <td key={p.urut} className={`${kelasTd} text-right tabular-nums`}>{formatNilai(sel(it.nilai, p.urut, io))}</td>)}
                      <td className={`${kelasTd} text-right tabular-nums`}>{akhir !== undefined && totalOut ? formatPersen(((sel(it.nilai, akhir, io) ?? 0) / totalOut) * 100) : ""}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
          <aside className="space-y-3">
            <section className="rounded border border-slate-200 bg-white p-3">
              <h2 className="mb-1 text-sm font-semibold">Data kurang & validasi</h2>
              {!d.validasi.length && <p className="text-xs text-slate-500">Tidak ada temuan.</p>}
              <ul className="max-h-72 space-y-1 overflow-auto text-xs">
                {d.validasi.map((t, i) => (
                  <li key={i} className={t.dikonfirmasi ? "text-slate-400" : ""}>
                    <Lencana warna={t.dikonfirmasi ? "hijau" : t.tingkat.startsWith("blokir") ? "merah" : t.tingkat === "peringatan" ? "kuning" : "biru"}>{t.kode}</Lencana>{" "}
                    <span className="text-slate-500">{LABEL_TINGKAT[t.tingkat]}</span> {t.pesan}
                  </li>
                ))}
              </ul>
            </section>
            <section className="rounded border border-slate-200 bg-white p-3">
              <h2 className="mb-1 text-sm font-semibold">Adjustment lapus</h2>
              {!qAdj.data?.length && <p className="text-xs text-slate-500">Belum ada.</p>}
              <ul className="space-y-1 text-xs">
                {(qAdj.data ?? []).map((a) => (
                  <li key={a.id}>{a.tahap}{a.metode ? ` ${a.metode}` : ""} {a.jenis} {a.harga === "CP" ? "ADHB" : "ADHK"} {a.label_periode}: <b className="tabular-nums">{formatNilai(a.nilai)}</b> · {a.status}</li>
                ))}
              </ul>
            </section>
          </aside>
        </div>
      )}
      {tambah && put && lap && (
        <DialogPenyesuaian putaran={put} wilayah={wil} lapus={[{ id: lap.id, kode: lap.kode, nama: lap.nama }]} tahapBoleh={tahapBoleh}
          metodeBoleh={Object.keys(d?.metode ?? {}).length ? Object.keys(d?.metode ?? {}) : undefined}
          tutup={() => setTambah(false)}
          selesai={(t) => { setTambah(false); setPesan({ jenis: "ok", teks: t }); qc.invalidateQueries({ queryKey: ["penyesuaian"] }); qc.invalidateQueries({ queryKey: ["hasil-lapus"] }); }} />
      )}
    </div>
  );
}
