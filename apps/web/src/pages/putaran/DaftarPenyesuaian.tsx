// Daftar adjustment satu wilayah (tiga tahap), putusan supervisor (setujui/tolak beralasan), hapus, + Adjustment.
import { useMemo, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { api, GalatApi } from "../../api/klien";
import { useDaftar, useIzin } from "../../api/hooks";
import type { Lapus } from "../../api/tipe";
import { DialogPenyesuaian, type Tahap } from "../../components/DialogPenyesuaian";
import { Lencana, Pesan, Pilihan, Tombol, kelasTabel, kelasTd, kelasTh } from "../../components/ui";
import { formatNilai, LABEL_STATUS_ADJ } from "../../lib/putaran";
import type { Putaran } from "../DataDasar";
import { DialogCatatan } from "./StatusLapus";

export interface Adj {
  id: number;
  wilayah: string;
  lapus_id: number;
  kode_lapus: string;
  nama_lapus: string;
  tahap: Tahap;
  metode: string | null;
  jenis: string;
  nama_jenis: string;
  ubah_angka: boolean;
  harga: "CP" | "K";
  periode: number;
  label_periode: string;
  nilai: number;
  alasan: string | null;
  status: string;
  diusulkan_oleh: string | null;
  diputus_oleh: string | null;
  catatan_putusan: string | null;
}

export function DaftarPenyesuaian({ putaran, wilayah, lapus }: { putaran: Putaran; wilayah: string; lapus: Lapus[] }) {
  const qc = useQueryClient();
  const izin = useIzin();
  const [tahap, setTahap] = useState("");
  const [status, setStatus] = useState("");
  const jalur = `/api/penyesuaian?putaran_id=${putaran.id}&wilayah=${wilayah}${tahap ? `&tahap=${tahap}` : ""}${status ? `&status=${status}` : ""}`;
  const q = useDaftar<Adj[]>(["penyesuaian", putaran.id, wilayah, tahap, status], jalur);
  const [pilih, setPilih] = useState<Set<number>>(new Set());
  const [tambah, setTambah] = useState(false);
  const [tolak, setTolak] = useState(false);
  const [pesan, setPesan] = useState<{ jenis: "ok" | "galat"; teks: string } | null>(null);
  const terkunci = putaran.status === "terkunci";
  const berdata = useMemo(() => lapus.filter((l) => l.aktif && ["daun", "top", "sop"].includes(l.jenis)), [lapus]);
  const tahapBoleh: Tahap[] = [
    ...((izin.has("penyesuaian.usul") || izin.has("penyesuaian.putus")) ? (["METODE", "REKON"] as Tahap[]) : []),
    ...(izin.has("simulasi.edit") ? (["SIMULASI"] as Tahap[]) : []),
  ];
  const daftar = q.data ?? [];

  async function aksi(fn: () => Promise<{ pesan: string }>) {
    setPesan(null);
    try {
      const r = await fn();
      setPesan({ jenis: "ok", teks: r.pesan });
      setPilih(new Set());
      qc.invalidateQueries({ queryKey: ["penyesuaian"] });
      qc.invalidateQueries({ queryKey: ["status"] });
    } catch (e) {
      setPesan({ jenis: "galat", teks: e instanceof GalatApi ? e.message : "Aksi gagal." });
    }
  }
  const putus = (keputusan: "setujui" | "tolak", catatan: string | null) =>
    aksi(() => api("/api/penyesuaian/putus", { metode: "POST", isi: { putaran_id: putaran.id, id: [...pilih], keputusan, catatan } }));

  return (
    <div>
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <div className="w-44">
          <Pilihan value={tahap} onChange={(e) => setTahap(e.target.value)} aria-label="Saring tahap">
            <option value="">Semua tahap</option>
            <option value="METODE">Metode</option>
            <option value="REKON">Rekonsiliasi</option>
            <option value="SIMULASI">Simulasi</option>
          </Pilihan>
        </div>
        <div className="w-40">
          <Pilihan value={status} onChange={(e) => setStatus(e.target.value)} aria-label="Saring status">
            <option value="">Semua status</option>
            {Object.entries(LABEL_STATUS_ADJ).map(([k, v]) => <option key={k} value={k}>{v.teks}</option>)}
          </Pilihan>
        </div>
        {!terkunci && tahapBoleh.length > 0 && <Tombol varian="utama" onClick={() => setTambah(true)}>+ Adjustment</Tombol>}
        {!terkunci && izin.has("penyesuaian.putus") && (
          <>
            <Tombol disabled={!pilih.size} onClick={() => putus("setujui", null)}>Setujui terpilih ({pilih.size})</Tombol>
            <Tombol varian="bahaya" disabled={!pilih.size} onClick={() => setTolak(true)}>Tolak terpilih</Tombol>
          </>
        )}
        <span className="text-xs text-slate-500">Hanya adjustment disetujui yang masuk angka resmi. METODE/REKON diajukan bersama lapus.</span>
      </div>
      {pesan && <div className="mb-2"><Pesan jenis={pesan.jenis}>{pesan.teks}</Pesan></div>}
      <div className="max-h-[60vh] overflow-auto rounded border border-slate-200 bg-white">
        <table className={kelasTabel}>
          <thead><tr>{["", "Lapus", "Tahap", "Jenis", "Harga", "Triwulan", "Nilai", "Status", "Alasan", "Oleh", ""].map((h, i) => <th key={i} className={kelasTh}>{h}</th>)}</tr></thead>
          <tbody>
            {daftar.map((a) => {
              const st = LABEL_STATUS_ADJ[a.status] ?? { teks: a.status, warna: "abu" as const };
              const bisaPutus = a.tahap === "SIMULASI" ? a.status === "draf" || a.status === "diajukan" : a.status === "diajukan";
              return (
                <tr key={a.id}>
                  <td className={kelasTd}>
                    {izin.has("penyesuaian.putus") && bisaPutus && !terkunci && (
                      <input type="checkbox" className="accent-merek-600" aria-label={`Pilih ${a.jenis} ${a.kode_lapus} ${a.label_periode}`} checked={pilih.has(a.id)}
                        onChange={(e) => { const s = new Set(pilih); if (e.target.checked) s.add(a.id); else s.delete(a.id); setPilih(s); }} />
                    )}
                  </td>
                  <td className={kelasTd} title={a.nama_lapus}>{a.kode_lapus}</td>
                  <td className={kelasTd}>{a.tahap}{a.metode ? ` ${a.metode}` : ""}</td>
                  <td className={kelasTd} title={a.nama_jenis}>{a.jenis}{!a.ubah_angka && <span className="text-xs text-slate-500"> (pembanding)</span>}</td>
                  <td className={kelasTd}>{a.harga === "CP" ? "ADHB" : "ADHK"}</td>
                  <td className={kelasTd}>{a.label_periode}</td>
                  <td className={`${kelasTd} text-right tabular-nums`}>{formatNilai(a.nilai)}</td>
                  <td className={kelasTd}><Lencana warna={st.warna}>{st.teks}</Lencana>{a.catatan_putusan && <div className="text-xs text-slate-500">{a.catatan_putusan}</div>}</td>
                  <td className={kelasTd}>{a.alasan}</td>
                  <td className={kelasTd}>{a.diusulkan_oleh ?? ""}{a.diputus_oleh ? ` · ${a.diputus_oleh}` : ""}</td>
                  <td className={kelasTd}>
                    {!terkunci && <Tombol kecil varian="teks" onClick={() => window.confirm(`Hapus ${a.jenis} ${a.kode_lapus} ${a.label_periode}?`) && aksi(() => api(`/api/penyesuaian/${a.id}`, { metode: "DELETE" }))}>Hapus</Tombol>}
                  </td>
                </tr>
              );
            })}
            {!daftar.length && <tr><td className={kelasTd} colSpan={11}>{q.isLoading ? "Memuat…" : "Belum ada adjustment."}</td></tr>}
          </tbody>
        </table>
      </div>
      {tambah && (
        <DialogPenyesuaian putaran={putaran} wilayah={wilayah} lapus={berdata} tahapBoleh={tahapBoleh} tutup={() => setTambah(false)}
          selesai={(t) => { setTambah(false); setPesan({ jenis: "ok", teks: t }); qc.invalidateQueries({ queryKey: ["penyesuaian"] }); }} />
      )}
      {tolak && <DialogCatatan judul={`Tolak ${pilih.size} adjustment`} tutup={() => setTolak(false)} kirim={(c) => { setTolak(false); void putus("tolak", c); }} />}
    </div>
  );
}
