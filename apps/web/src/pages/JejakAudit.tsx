import { Fragment, useState } from "react";
import { api } from "../api/klien";
import { useDaftar } from "../api/hooks";
import type { BarisAudit } from "../api/tipe";
import { Isian, Lencana, Masukan, Pesan, Tombol, kelasTabel, kelasTd, kelasTh } from "../components/ui";

const ENTITAS = ["", "sec.pengguna", "sec.pengguna_peran", "sec.peran", "sec.peran_izin", "lk.penugasan", "ref.lapus", "ref.lapus_kelompok",
  "ref.konkordansi_lapus", "ref.tahun_dasar", "ref.katalog_komoditas", "ref.satuan", "ref.sumber_data", "ref.wilayah", "lk.item",
  "lk.nilai_item", "lk.parameter_item", "lk.penyesuaian", "lk.putaran", "audit.ekspor", "sec.sesi"];

function Rincian({ b }: { b: BarisAudit }) {
  const kunci = Array.from(new Set([...Object.keys(b.nilai_lama ?? {}), ...Object.keys(b.nilai_baru ?? {})]));
  const beda = kunci.filter((k) => JSON.stringify(b.nilai_lama?.[k]) !== JSON.stringify(b.nilai_baru?.[k]));
  const tampil = b.aksi === "UPDATE" ? beda : kunci;
  return (
    <table className="text-xs">
      <tbody>
        {tampil.map((k) => (
          <tr key={k}>
            <td className="pr-2 font-mono text-slate-500">{k}</td>
            {b.aksi !== "INSERT" && <td className="pr-2 text-red-700">{JSON.stringify(b.nilai_lama?.[k] ?? null)}</td>}
            {b.aksi !== "DELETE" && <td className="text-green-800">{JSON.stringify(b.nilai_baru?.[k] ?? null)}</td>}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export function JejakAudit() {
  const [f, setF] = useState({ entitas: "", aksi: "", dari: "", sampai: "" });
  const [hal, setHal] = useState(1);
  const [buka, setBuka] = useState<number | null>(null);
  const [cek, setCek] = useState<{ utuh: boolean; baris: number; putus: number } | null>(null);
  const qs = new URLSearchParams({ halaman: String(hal), per_halaman: "50", ...Object.fromEntries(Object.entries(f).filter(([, v]) => v)) });
  const q = useDaftar<{ total: number; baris: BarisAudit[] }>(["audit", qs.toString()], `/api/audit?${qs}`);
  const total = q.data?.total ?? 0;

  return (
    <div className="space-y-3">
      <h1 className="text-xl font-semibold">Jejak audit</h1>
      <div className="flex flex-wrap items-end gap-2">
        <div className="w-56"><Isian label="Data"><select className="w-full rounded border border-slate-300 px-2 py-1.5 text-sm" value={f.entitas} onChange={(e) => { setF({ ...f, entitas: e.target.value }); setHal(1); }}>{ENTITAS.map((x) => <option key={x} value={x}>{x || "(semua)"}</option>)}</select></Isian></div>
        <div className="w-40"><Isian label="Aksi"><Masukan placeholder="mis. LOGIN" value={f.aksi} onChange={(e) => { setF({ ...f, aksi: e.target.value.toUpperCase() }); setHal(1); }} /></Isian></div>
        <div className="w-40"><Isian label="Dari"><Masukan type="date" value={f.dari} onChange={(e) => { setF({ ...f, dari: e.target.value }); setHal(1); }} /></Isian></div>
        <div className="w-40"><Isian label="Sampai"><Masukan type="date" value={f.sampai} onChange={(e) => { setF({ ...f, sampai: e.target.value }); setHal(1); }} /></Isian></div>
        <Tombol onClick={async () => setCek(await api("/api/audit/verifikasi"))}>Verifikasi rantai hash</Tombol>
      </div>
      {cek && <Pesan jenis={cek.utuh ? "ok" : "galat"}>{cek.utuh ? `Rantai hash utuh (${cek.baris} catatan).` : `Rantai hash PUTUS di ${cek.putus} titik. Laporkan ke admin.`}</Pesan>}
      <div className="overflow-auto rounded border border-slate-200 bg-white">
        <table className={kelasTabel} aria-label="Jejak audit">
          <thead><tr>{["Waktu", "Pengguna", "Aksi", "Data", "Alasan", ""].map((h) => <th key={h} className={kelasTh}>{h}</th>)}</tr></thead>
          <tbody>
            {(q.data?.baris ?? []).map((b) => (
              <Fragment key={b.id}>
                <tr>
                  <td className={`${kelasTd} whitespace-nowrap text-xs`}>{new Date(b.waktu).toLocaleString("id-ID")}</td>
                  <td className={kelasTd}>{b.username ?? <span className="text-slate-400">sistem</span>} <span className="text-xs text-slate-400">{b.ip ?? ""}</span></td>
                  <td className={kelasTd}><Lencana warna={b.aksi.includes("GAGAL") || b.aksi.includes("TERKUNCI") || b.aksi.includes("PAKAI_ULANG") ? "merah" : b.aksi === "DELETE" ? "kuning" : "abu"}>{b.aksi}</Lencana></td>
                  <td className={`${kelasTd} font-mono text-xs`}>{b.entitas} {b.entitas_id ?? ""}</td>
                  <td className={`${kelasTd} text-xs`}>{b.alasan ?? ""}</td>
                  <td className={kelasTd}>{(b.nilai_lama || b.nilai_baru) && <Tombol kecil varian="teks" onClick={() => setBuka(buka === b.id ? null : b.id)}>{buka === b.id ? "Tutup" : "Rincian"}</Tombol>}</td>
                </tr>
                {buka === b.id && <tr><td colSpan={6} className="bg-slate-50 px-4 py-2"><Rincian b={b} /></td></tr>}
              </Fragment>
            ))}
          </tbody>
        </table>
      </div>
      <div className="flex items-center gap-2 text-sm">
        <Tombol kecil disabled={hal <= 1} onClick={() => setHal(hal - 1)}>‹ Sebelumnya</Tombol>
        <span>Halaman {hal} dari {Math.max(1, Math.ceil(total / 50))} ({total} catatan)</span>
        <Tombol kecil disabled={hal * 50 >= total} onClick={() => setHal(hal + 1)}>Berikutnya ›</Tombol>
      </div>
    </div>
  );
}
