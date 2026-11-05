// Daftar putaran: buka (salin dari putaran sumber), cakupan, cut-off, kunci / buka kunci beralasan (syarat V13–V15 + status).
import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { api, GalatApi } from "../../api/klien";
import { useIzin } from "../../api/hooks";
import { Dialog } from "../../components/Dialog";
import type { PilihanPutaran } from "../../components/PemilihPutaran";
import { Isian, Lencana, Masukan, Pesan, Pilihan, Tombol, kelasInput, kelasTabel, kelasTd, kelasTh } from "../../components/ui";
import { labelPeriode } from "../../lib/dataDasar";
import { urut } from "../../lib/putaran";
import type { Putaran } from "../DataDasar";

interface Syarat {
  wilayah: string[];
  blokir: { wilayah: string; kode: string; kode_lapus: string; pesan: string }[];
  boleh_kunci: boolean;
}

function waktu(t: string | null | undefined): string {
  return t ? new Date(t).toLocaleString("id-ID", { dateStyle: "medium", timeStyle: "short" }) : "";
}

/** ISO -> nilai input datetime-local (waktu lokal). */
function keLokal(t: string | null | undefined): string {
  if (!t) return "";
  const d = new Date(t);
  const z = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${z(d.getMonth() + 1)}-${z(d.getDate())}T${z(d.getHours())}:${z(d.getMinutes())}`;
}

export function DaftarPutaran({ pil }: { pil: PilihanPutaran }) {
  const qc = useQueryClient();
  const izin = useIzin();
  const [dialog, setDialog] = useState<{ jenis: "buka" } | { jenis: "cutoff" | "kunci" | "buka_kunci"; p: Putaran } | null>(null);
  const [pesan, setPesan] = useState<{ jenis: "ok" | "galat"; teks: string } | null>(null);
  const segarkan = () => qc.invalidateQueries({ queryKey: ["putaran"] });
  const selesai = (teks: string) => {
    setDialog(null);
    setPesan({ jenis: "ok", teks });
    segarkan();
  };
  return (
    <div>
      <div className="mb-2 flex items-center gap-2">
        {izin.has("putaran.kelola") && <Tombol varian="utama" onClick={() => setDialog({ jenis: "buka" })}>Buka putaran baru</Tombol>}
        <span className="text-xs text-slate-500">Putaran terkunci menolak semua perubahan. Buka kunci hanya admin, beralasan, tercatat di audit.</span>
      </div>
      {pesan && <div className="mb-2"><Pesan jenis={pesan.jenis}>{pesan.teks}</Pesan></div>}
      <div className="overflow-auto rounded border border-slate-200 bg-white">
        <table className={kelasTabel}>
          <thead>
            <tr>{["Putaran", "Jenis", "Cakupan", "Status", "Cut-off", "Sumber", "Dibuka", "Dikunci", ""].map((h) => <th key={h} className={kelasTh}>{h}</th>)}</tr>
          </thead>
          <tbody>
            {pil.putaran.map((p) => (
              <tr key={p.id} className={p.id === pil.put?.id ? "bg-merek-50" : ""}>
                <td className={kelasTd}><button type="button" className="text-left font-medium text-merek-700 hover:underline" onClick={() => pil.setPutId(p.id)}>{p.nama}</button></td>
                <td className={kelasTd}>{p.jenis}</td>
                <td className={kelasTd}>{p.label_awal}–{p.label_akhir}</td>
                <td className={kelasTd}><Lencana warna={p.status === "terkunci" ? "abu" : "hijau"}>{p.status}</Lencana></td>
                <td className={kelasTd}>{waktu(p.tanggal_cutoff)} {p.lewat_cutoff && <Lencana warna="kuning">lewat</Lencana>}</td>
                <td className={kelasTd}>{p.sumber ?? ""}</td>
                <td className={kelasTd}>{p.dibuka_oleh ?? ""} {waktu(p.dibuka_pada)}</td>
                <td className={kelasTd}>{p.status === "terkunci" ? `${p.dikunci_oleh ?? ""} ${waktu(p.dikunci_pada)}` : ""}</td>
                <td className={`${kelasTd} whitespace-nowrap`}>
                  {p.status !== "terkunci" && izin.has("putaran.kelola") && <Tombol kecil onClick={() => setDialog({ jenis: "cutoff", p })}>Cut-off</Tombol>}{" "}
                  {p.status !== "terkunci" && izin.has("putaran.kunci") && <Tombol kecil onClick={() => setDialog({ jenis: "kunci", p })}>Kunci…</Tombol>}
                  {p.status === "terkunci" && izin.has("putaran.buka_kunci") && <Tombol kecil varian="bahaya" onClick={() => setDialog({ jenis: "buka_kunci", p })}>Buka kunci…</Tombol>}
                </td>
              </tr>
            ))}
            {!pil.putaran.length && <tr><td className={kelasTd} colSpan={9}>{pil.memuat ? "Memuat…" : "Belum ada putaran pada tahun dasar ini."}</td></tr>}
          </tbody>
        </table>
      </div>
      {dialog?.jenis === "buka" && pil.td && (
        <DialogBuka td={pil.td} putaran={pil.putaran} tutup={() => setDialog(null)} selesai={(t, id) => { pil.setPutId(id); selesai(t); }} />
      )}
      {dialog?.jenis === "cutoff" && <DialogCutoff p={dialog.p} tutup={() => setDialog(null)} selesai={selesai} />}
      {dialog?.jenis === "kunci" && <DialogKunci p={dialog.p} tutup={() => setDialog(null)} selesai={selesai} />}
      {dialog?.jenis === "buka_kunci" && <DialogBukaKunci p={dialog.p} tutup={() => setDialog(null)} selesai={selesai} />}
    </div>
  );
}

/** Q1 setiap tahun dari awal seri sampai triwulan berjalan (pilihan awal cakupan). */
function triwulanPertama(tahunAwal: number, akhir: number): number[] {
  return Array.from({ length: Math.max(0, Math.floor((akhir - urut(tahunAwal, 1)) / 4) + 1) }, (_, i) => urut(tahunAwal + i, 1));
}

function DialogBuka({ td, putaran, tutup, selesai }: { td: { id: number; kode: string; tahun_awal_seri: number }; putaran: Putaran[];
  tutup: () => void; selesai: (t: string, id: number) => void }) {
  const terakhir = putaran.length ? putaran[0] : null;
  const lanjut = terakhir ? terakhir.akhir + 1 : urut(new Date().getFullYear(), 1);
  const awalBawaan = terakhir ? terakhir.awal : urut(Math.max(td.tahun_awal_seri, 2019), 1);
  const terkunci = putaran.find((p) => p.status === "terkunci");
  const sumberBawaan: number | "" = terkunci ? terkunci.id : terakhir ? terakhir.id : "";
  const [tahun, setTahun] = useState(Math.floor(lanjut / 4));
  const [tw, setTw] = useState((lanjut % 4) + 1);
  const [nama, setNama] = useState(`Putaran ${labelPeriode(lanjut)}`);
  const [jenis, setJenis] = useState(putaran.length ? "REGULER" : "BACKCAST");
  const [awal, setAwal] = useState(awalBawaan);
  const [sumber, setSumber] = useState<number | "">(sumberBawaan);
  const [cutoff, setCutoff] = useState("");
  const [catatan, setCatatan] = useState("");
  const [galat, setGalat] = useState<string | null>(null);
  const [sibuk, setSibuk] = useState(false);
  const akhir = urut(tahun, tw);
  const opsiAwal = triwulanPertama(td.tahun_awal_seri, akhir);
  async function kirim() {
    setSibuk(true);
    setGalat(null);
    try {
      const r = await api<{ id: number; pesan: string }>("/api/putaran", { metode: "POST", isi: {
        tahun_dasar_id: td.id, tahun, triwulan: tw, nama, jenis, periode_awal: awal, sumber_putaran_id: sumber || null,
        tanggal_cutoff: cutoff ? new Date(cutoff).toISOString() : null, catatan: catatan || null } });
      selesai(r.pesan, r.id);
    } catch (e) {
      setGalat(e instanceof GalatApi ? e.message : "Gagal membuka putaran.");
    } finally {
      setSibuk(false);
    }
  }
  return (
    <Dialog judul={`Buka putaran ${td.kode}`} tutup={tutup}>
      <div className="grid grid-cols-2 gap-3">
        <Isian label="Nama"><Masukan value={nama} onChange={(e) => setNama(e.target.value)} aria-label="Nama putaran" /></Isian>
        <Isian label="Jenis">
          <Pilihan value={jenis} onChange={(e) => setJenis(e.target.value)} aria-label="Jenis putaran">
            {["BACKCAST", "REGULER", "REVISI", "RILIS"].map((j) => <option key={j}>{j}</option>)}
          </Pilihan>
        </Isian>
        <Isian label="Tahun berjalan"><Masukan type="number" value={tahun} onChange={(e) => setTahun(Number(e.target.value))} aria-label="Tahun" /></Isian>
        <Isian label="Triwulan berjalan">
          <Pilihan value={tw} onChange={(e) => setTw(Number(e.target.value))} aria-label="Triwulan">
            {[1, 2, 3, 4].map((q) => <option key={q} value={q}>Q{q}</option>)}
          </Pilihan>
        </Isian>
        <Isian label="Cakupan mulai" petunjuk={`Sampai ${labelPeriode(akhir)} (triwulan berjalan)`}>
          <Pilihan value={awal} onChange={(e) => setAwal(Number(e.target.value))} aria-label="Cakupan mulai">
            {opsiAwal.map((u) => <option key={u} value={u}>{labelPeriode(u)}</option>)}
          </Pilihan>
        </Isian>
        <Isian label="Salin dari putaran" petunjuk="Data, jangkar, seri referensi; adjustment menjadi draf.">
          <Pilihan value={sumber} onChange={(e) => setSumber(e.target.value ? Number(e.target.value) : "")} aria-label="Salin dari putaran">
            <option value="">(tanpa salinan)</option>
            {putaran.map((p) => <option key={p.id} value={p.id}>{p.nama} {p.status === "terkunci" ? "(terkunci)" : ""}</option>)}
          </Pilihan>
        </Isian>
        <Isian label="Cut-off data (opsional)" petunjuk="Sesudah cut-off, perubahan data dasar wajib beralasan.">
          <Masukan type="datetime-local" value={cutoff} onChange={(e) => setCutoff(e.target.value)} aria-label="Cut-off" />
        </Isian>
        <Isian label="Catatan"><Masukan value={catatan} onChange={(e) => setCatatan(e.target.value)} aria-label="Catatan putaran" /></Isian>
      </div>
      {galat && <div className="mt-3"><Pesan jenis="galat">{galat}</Pesan></div>}
      <div className="mt-4 flex justify-end gap-2">
        <Tombol onClick={tutup}>Batal</Tombol>
        <Tombol varian="utama" disabled={sibuk || nama.trim().length < 2} onClick={kirim}>Buka putaran</Tombol>
      </div>
    </Dialog>
  );
}

function DialogCutoff({ p, tutup, selesai }: { p: Putaran; tutup: () => void; selesai: (t: string) => void }) {
  const [cutoff, setCutoff] = useState(keLokal(p.tanggal_cutoff));
  const [galat, setGalat] = useState<string | null>(null);
  async function kirim() {
    try {
      await api(`/api/putaran/${p.id}`, { metode: "PATCH", isi: { tanggal_cutoff: cutoff ? new Date(cutoff).toISOString() : null } });
      selesai(`Cut-off ${p.nama} diperbarui.`);
    } catch (e) {
      setGalat(e instanceof GalatApi ? e.message : "Gagal menyimpan.");
    }
  }
  return (
    <Dialog judul={`Cut-off ${p.nama}`} tutup={tutup}>
      <Isian label="Tanggal dan jam cut-off" petunjuk="Kosongkan untuk tanpa cut-off.">
        <Masukan type="datetime-local" value={cutoff} onChange={(e) => setCutoff(e.target.value)} aria-label="Cut-off" />
      </Isian>
      {galat && <div className="mt-3"><Pesan jenis="galat">{galat}</Pesan></div>}
      <div className="mt-4 flex justify-end gap-2"><Tombol onClick={tutup}>Batal</Tombol><Tombol varian="utama" onClick={kirim}>Simpan</Tombol></div>
    </Dialog>
  );
}

export function DialogKunci({ p, tutup, selesai }: { p: Putaran; tutup: () => void; selesai: (t: string) => void }) {
  const [syarat, setSyarat] = useState<Syarat | null>(null);
  const [alasan, setAlasan] = useState("");
  const [galat, setGalat] = useState<string | null>(null);
  const [sibuk, setSibuk] = useState(false);
  async function periksa() {
    setGalat(null);
    setSibuk(true);
    try {
      setSyarat(await api<Syarat>(`/api/putaran/${p.id}/syarat-kunci`));
    } catch (e) {
      setGalat(e instanceof GalatApi ? e.message : "Gagal memeriksa syarat.");
    } finally {
      setSibuk(false);
    }
  }
  async function kunci() {
    setGalat(null);
    setSibuk(true);
    try {
      const r = await api<{ pesan: string }>(`/api/putaran/${p.id}/kunci`, { metode: "POST", isi: { alasan } });
      selesai(r.pesan);
    } catch (e) {
      if (e instanceof GalatApi && e.kode === "SYARAT_KUNCI" && Array.isArray(e.rincian))
        setSyarat({ wilayah: [], blokir: e.rincian as Syarat["blokir"], boleh_kunci: false });
      setGalat(e instanceof GalatApi ? e.message : "Gagal mengunci.");
    } finally {
      setSibuk(false);
    }
  }
  return (
    <Dialog judul={`Kunci ${p.nama}`} tutup={tutup} lebar="max-w-2xl">
      <p className="mb-2 text-sm text-slate-600">Syarat: V13–V15 lolos (V14 boleh dikecualikan admin), semua lapus berdata disetujui, simulasi diputus, hitung ulang selesai.</p>
      <Tombol onClick={periksa} disabled={sibuk}>Periksa syarat</Tombol>
      {syarat && (
        <div className="mt-2 max-h-64 overflow-auto rounded border border-slate-200">
          {syarat.boleh_kunci ? (
            <p className="p-2 text-sm text-green-700">Semua syarat terpenuhi{syarat.wilayah.length ? ` (wilayah ${syarat.wilayah.join(", ")})` : ""}.</p>
          ) : (
            <table className={kelasTabel} aria-label="Syarat kunci belum terpenuhi">
              <thead><tr>{["Wilayah", "Kode", "Lapus", "Pesan"].map((h) => <th key={h} className={kelasTh}>{h}</th>)}</tr></thead>
              <tbody>{syarat.blokir.map((b, i) => <tr key={i}><td className={kelasTd}>{b.wilayah}</td><td className={kelasTd}>{b.kode}</td><td className={kelasTd}>{b.kode_lapus}</td><td className={kelasTd}>{b.pesan}</td></tr>)}</tbody>
            </table>
          )}
        </div>
      )}
      <div className="mt-3">
        <Isian label="Alasan kunci (wajib, min. 10 karakter)">
          <textarea className={kelasInput} rows={2} value={alasan} onChange={(e) => setAlasan(e.target.value)} aria-label="Alasan kunci" />
        </Isian>
      </div>
      {galat && <div className="mt-3"><Pesan jenis="galat">{galat}</Pesan></div>}
      <div className="mt-4 flex justify-end gap-2">
        <Tombol onClick={tutup}>Batal</Tombol>
        <Tombol varian="utama" disabled={sibuk || alasan.trim().length < 10} onClick={kunci}>Kunci putaran</Tombol>
      </div>
    </Dialog>
  );
}

function DialogBukaKunci({ p, tutup, selesai }: { p: Putaran; tutup: () => void; selesai: (t: string) => void }) {
  const [alasan, setAlasan] = useState("");
  const [galat, setGalat] = useState<string | null>(null);
  async function kirim() {
    try {
      const r = await api<{ pesan: string }>(`/api/putaran/${p.id}/buka-kunci`, { metode: "POST", isi: { alasan } });
      selesai(r.pesan);
    } catch (e) {
      setGalat(e instanceof GalatApi ? e.message : "Gagal membuka kunci.");
    }
  }
  return (
    <Dialog judul={`Buka kunci ${p.nama}`} tutup={tutup}>
      <Pesan jenis="info">Angka putaran ini dapat berubah lagi setelah kunci dibuka. Perubahan tercatat di jejak audit.</Pesan>
      <div className="mt-3">
        <Isian label="Alasan buka kunci (wajib, min. 10 karakter)">
          <textarea className={kelasInput} rows={2} value={alasan} onChange={(e) => setAlasan(e.target.value)} aria-label="Alasan buka kunci" />
        </Isian>
      </div>
      {galat && <div className="mt-3"><Pesan jenis="galat">{galat}</Pesan></div>}
      <div className="mt-4 flex justify-end gap-2">
        <Tombol onClick={tutup}>Batal</Tombol>
        <Tombol varian="bahaya" disabled={alasan.trim().length < 10} onClick={kirim}>Buka kunci</Tombol>
      </div>
    </Dialog>
  );
}
