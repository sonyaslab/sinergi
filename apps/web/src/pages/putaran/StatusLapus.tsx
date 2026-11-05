// Status lapus satu wilayah: belum → draf → diajukan → disetujui / dikembalikan; NIHIL dan DIKECUALIKAN (V14, admin).
import { Fragment, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { api, GalatApi } from "../../api/klien";
import { useDaftar, useIzin } from "../../api/hooks";
import { Dialog } from "../../components/Dialog";
import { Isian, Lencana, Pesan, Tombol, kelasInput, kelasTabel, kelasTd, kelasTh } from "../../components/ui";
import { AKSI_CATATAN, aksiTersedia, LABEL_AKSI, LABEL_STATUS, WARNA_STATUS, type AksiStatus, type BarisStatus } from "../../lib/putaran";
import type { Putaran } from "../DataDasar";

interface Baris extends BarisStatus {
  catatan: string | null;
  diperbarui_pada: string | null;
  diperbarui_oleh: string | null;
  penyesuaian: Record<string, number>;
  blokir_ajukan: number;
}
interface Riwayat { dari: string | null; ke: string; pada: string; catatan: string | null; oleh: string | null }

export function StatusLapus({ putaran, wilayah }: { putaran: Putaran; wilayah: string }) {
  const qc = useQueryClient();
  const izin = useIzin();
  const kunci = ["status", putaran.id, wilayah];
  const q = useDaftar<{ lapus: Baris[] }>(kunci, `/api/status?putaran_id=${putaran.id}&wilayah=${wilayah}`);
  const [aksi, setAksi] = useState<{ b: Baris; a: AksiStatus } | null>(null);
  const [buka, setBuka] = useState<number | null>(null);
  const [pesan, setPesan] = useState<{ jenis: "ok" | "galat"; teks: string; rincian?: string[] } | null>(null);
  const [saring, setSaring] = useState<"semua" | "berisi">("berisi");
  const terkunci = putaran.status === "terkunci";
  const baris = (q.data?.lapus ?? []).filter((b) => saring === "semua" || b.jumlah_item > 0 || b.status !== "belum");
  const jumlah = (q.data?.lapus ?? []).reduce<Record<string, number>>((a, b) => ({ ...a, [b.status]: (a[b.status] ?? 0) + 1 }), {});

  async function jalankan(b: Baris, a: AksiStatus, catatan: string | null, putus?: "setujui" | "tolak") {
    setPesan(null);
    try {
      const r = await api<{ pesan: string }>(`/api/status/${b.id}/${a}`, { metode: "POST", isi: {
        putaran_id: putaran.id, wilayah, catatan, ...(putus ? { putus_penyesuaian: putus } : {}) } });
      setAksi(null);
      setPesan({ jenis: "ok", teks: r.pesan });
      qc.invalidateQueries({ queryKey: kunci });
      qc.invalidateQueries({ queryKey: ["status-ringkasan"] });
    } catch (e) {
      if (e instanceof GalatApi && e.kode === "PENYESUAIAN_BELUM_DIPUTUS") {
        if (window.confirm(`${e.message}\n\nSetujui semua penyesuaian yang diajukan sekaligus?`)) return jalankan(b, a, catatan, "setujui");
      }
      const rincian = e instanceof GalatApi && Array.isArray(e.rincian) ? (e.rincian as { kode: string; pesan: string }[]).map((x) => `${x.kode}: ${x.pesan}`) : undefined;
      setPesan({ jenis: "galat", teks: e instanceof GalatApi ? e.message : "Aksi gagal.", rincian });
      setAksi(null);
    }
  }

  function klik(b: Baris, a: AksiStatus) {
    if (AKSI_CATATAN.has(a)) setAksi({ b, a });
    else void jalankan(b, a, null);
  }

  return (
    <div>
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <label className="text-sm">
          <input type="checkbox" className="mr-1 accent-merek-600" checked={saring === "semua"} onChange={(e) => setSaring(e.target.checked ? "semua" : "berisi")} />
          Tampilkan semua lapus (termasuk yang belum berisi)
        </label>
        {Object.entries(jumlah).map(([k, n]) => <Lencana key={k} warna={WARNA_STATUS[k as keyof typeof WARNA_STATUS]}>{LABEL_STATUS[k as keyof typeof LABEL_STATUS]}: {n}</Lencana>)}
      </div>
      {pesan && (
        <div className="mb-2">
          <Pesan jenis={pesan.jenis}>
            {pesan.teks}
            {pesan.rincian && <ul className="mt-1 list-disc pl-5 text-xs">{pesan.rincian.map((r, i) => <li key={i}>{r}</li>)}</ul>}
          </Pesan>
        </div>
      )}
      <div className="max-h-[65vh] overflow-auto rounded border border-slate-200 bg-white">
        <table className={kelasTabel}>
          <thead><tr>{["Lapus", "Status", "Item", "Adjustment", "Blokir ajukan", "Diperbarui", "Aksi"].map((h) => <th key={h} className={kelasTh}>{h}</th>)}</tr></thead>
          <tbody>
            {baris.map((b) => (
              <Fragment key={b.id}>
                <tr>
                  <td className={kelasTd} title={b.nama}><span className="font-medium">{b.kode}</span> <span className="text-slate-500">{b.nama}</span></td>
                  <td className={kelasTd}><Lencana warna={WARNA_STATUS[b.status]}>{LABEL_STATUS[b.status]}</Lencana>{b.catatan && <div className="text-xs text-slate-500">{b.catatan}</div>}</td>
                  <td className={kelasTd}>{b.jumlah_item}</td>
                  <td className={kelasTd}>{Object.entries(b.penyesuaian).map(([k, n]) => `${k} ${n}`).join(", ")}</td>
                  <td className={kelasTd}>{b.blokir_ajukan > 0 && <Lencana warna="merah">{b.blokir_ajukan}</Lencana>}</td>
                  <td className={kelasTd}>{b.diperbarui_oleh ?? ""}</td>
                  <td className={`${kelasTd} whitespace-nowrap`}>
                    {aksiTersedia(b, izin, terkunci).map((a) => (
                      <Tombol key={a} kecil varian={a === "setujui" || a === "ajukan" ? "utama" : a === "kembalikan" ? "bahaya" : "biasa"} className="mr-1" onClick={() => klik(b, a)}>{LABEL_AKSI[a]}</Tombol>
                    ))}
                    <Tombol kecil varian="teks" onClick={() => setBuka(buka === b.id ? null : b.id)}>Riwayat</Tombol>
                  </td>
                </tr>
                {buka === b.id && <tr><td colSpan={7} className="bg-slate-50 px-4 py-2"><RiwayatLapus putaran={putaran.id} wilayah={wilayah} lapus={b.id} /></td></tr>}
              </Fragment>
            ))}
            {!baris.length && <tr><td className={kelasTd} colSpan={7}>{q.isLoading ? "Memuat…" : "Belum ada lapus berisi pada wilayah ini."}</td></tr>}
          </tbody>
        </table>
      </div>
      {aksi && <DialogCatatan judul={`${LABEL_AKSI[aksi.a]} ${aksi.b.kode}`} tutup={() => setAksi(null)} kirim={(c) => jalankan(aksi.b, aksi.a, c)} />}
    </div>
  );
}

function RiwayatLapus({ putaran, wilayah, lapus }: { putaran: number; wilayah: string; lapus: number }) {
  const q = useDaftar<Riwayat[]>(["riwayat", putaran, wilayah, lapus], `/api/status/${lapus}/riwayat?putaran_id=${putaran}&wilayah=${wilayah}`);
  if (q.isLoading) return <span className="text-xs text-slate-500">Memuat…</span>;
  if (!q.data?.length) return <span className="text-xs text-slate-500">Belum ada riwayat.</span>;
  return (
    <ul className="text-xs">
      {q.data.map((r, i) => (
        <li key={i}>{new Date(r.pada).toLocaleString("id-ID")} · {r.oleh ?? "-"}: {r.dari ?? "-"} → <b>{r.ke}</b>{r.catatan ? ` (${r.catatan})` : ""}</li>
      ))}
    </ul>
  );
}

export function DialogCatatan({ judul, tutup, kirim }: { judul: string; tutup: () => void; kirim: (c: string) => void }) {
  const [c, setC] = useState("");
  return (
    <Dialog judul={judul} tutup={tutup}>
      <Isian label="Catatan (wajib, min. 10 karakter)">
        <textarea className={kelasInput} rows={3} value={c} onChange={(e) => setC(e.target.value)} aria-label="Catatan" />
      </Isian>
      <div className="mt-4 flex justify-end gap-2">
        <Tombol onClick={tutup}>Batal</Tombol>
        <Tombol varian="utama" disabled={c.trim().length < 10} onClick={() => kirim(c.trim())}>Kirim</Tombol>
      </div>
    </Dialog>
  );
}
