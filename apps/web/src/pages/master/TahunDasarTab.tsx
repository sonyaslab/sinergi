import { useState, type FormEvent } from "react";
import { api, type TahunDasar } from "../../api/klien";
import { useAksi, useDaftar } from "../../api/hooks";
import type { HasilHapus } from "../../api/tipe";
import { Centang, Isian, Lencana, Masukan, Panel, Pesan, Pilihan, Tombol, kelasTabel, kelasTd, kelasTh } from "../../components/ui";

type TD = TahunDasar & { jangkar_dari_data: boolean };
const STATUS = ["rencana", "paralel", "produksi", "arsip"] as const;

function Formulir({ lama, daftar, selesai }: { lama: TD | null; daftar: TD[]; selesai: (p?: string) => void }) {
  const [f, setF] = useState({
    kode: lama?.kode ?? "", tahun_dasar: String(lama?.tahun_dasar ?? ""), status: lama?.status ?? "rencana",
    klasifikasi: lama?.klasifikasi ?? "KBLI2025", tahun_awal_seri: String(lama?.tahun_awal_seri ?? ""),
    tahun_baseline_eks: String(lama?.tahun_baseline_eks ?? ""), keterangan: lama?.keterangan ?? "",
    jangkar_dari_data: lama?.jangkar_dari_data ?? true, salin: "",
  });
  const aksi = useAksi([["tahun-dasar"]]);
  const set = (k: keyof typeof f, v: string | boolean) => setF({ ...f, [k]: v });

  async function kirim(e: FormEvent) {
    e.preventDefault();
    const umum = { status: f.status, tahun_awal_seri: Number(f.tahun_awal_seri), tahun_baseline_eks: Number(f.tahun_baseline_eks), keterangan: f.keterangan || null, jangkar_dari_data: f.jangkar_dari_data };
    const r = lama
      ? await aksi.jalankan(() => api(`/api/tahun-dasar/${lama.id}`, { metode: "PATCH", isi: umum }))
      : await aksi.jalankan(() => api(`/api/tahun-dasar`, { metode: "POST", isi: { ...umum, kode: f.kode, tahun_dasar: Number(f.tahun_dasar), klasifikasi: f.klasifikasi, salin_pohon_dari: f.salin ? Number(f.salin) : null } }));
    if (r) selesai(lama ? "Tahun dasar tersimpan." : "Tahun dasar ditambahkan.");
  }

  return (
    <Panel judul={lama ? `Ubah ${lama.kode}` : "Tambah tahun dasar"} tutup={() => selesai()}>
      <form onSubmit={kirim} className="space-y-2">
        {aksi.pesan && <Pesan jenis={aksi.pesan.jenis}>{aksi.pesan.teks}</Pesan>}
        <div className="grid grid-cols-2 gap-2">
          <Isian label="Kode"><Masukan required disabled={!!lama} pattern="TD[0-9]{4}" placeholder="TD2025" value={f.kode} onChange={(e) => set("kode", e.target.value)} /></Isian>
          <Isian label="Tahun dasar"><Masukan required disabled={!!lama} type="number" value={f.tahun_dasar} onChange={(e) => set("tahun_dasar", e.target.value)} /></Isian>
          <Isian label="Klasifikasi">
            <Pilihan disabled={!!lama} value={f.klasifikasi} onChange={(e) => set("klasifikasi", e.target.value)}>
              <option value="KBLI2020">KBLI 2020</option><option value="KBLI2025">KBLI 2025</option>
            </Pilihan>
          </Isian>
          <Isian label="Status">
            <Pilihan value={f.status} onChange={(e) => set("status", e.target.value)}>{STATUS.map((s) => <option key={s}>{s}</option>)}</Pilihan>
          </Isian>
          <Isian label="Tahun awal seri"><Masukan required type="number" value={f.tahun_awal_seri} onChange={(e) => set("tahun_awal_seri", e.target.value)} /></Isian>
          <Isian label="Tahun baseline" petunjuk="Titik awal rantai EKS"><Masukan required type="number" value={f.tahun_baseline_eks} onChange={(e) => set("tahun_baseline_eks", e.target.value)} /></Isian>
        </div>
        <Centang label="Jangkar boleh dihitung dari data tahun baseline" checked={f.jangkar_dari_data} onChange={(e) => set("jangkar_dari_data", e.target.checked)} />
        <p className="text-xs text-slate-500">Tidak dicentang: harga/IH/RKA tahun dasar wajib diisi untuk semua item (pola TD2010).</p>
        <Isian label="Keterangan"><Masukan value={f.keterangan} onChange={(e) => set("keterangan", e.target.value)} /></Isian>
        {!lama && (
          <Isian label="Salin pohon lapus dari" petunjuk="Opsional: urutan, induk, kelompok ikut tersalin">
            <Pilihan value={f.salin} onChange={(e) => set("salin", e.target.value)}>
              <option value="">(pohon kosong)</option>
              {daftar.map((t) => <option key={t.id} value={t.id}>{t.kode}</option>)}
            </Pilihan>
          </Isian>
        )}
        <Tombol varian="utama" type="submit" disabled={aksi.sibuk}>Simpan</Tombol>
      </form>
    </Panel>
  );
}

export function TahunDasarTab() {
  const q = useDaftar<TD[]>(["tahun-dasar"], "/api/tahun-dasar");
  const aksi = useAksi([["tahun-dasar"]]);
  const [mode, setMode] = useState<{ lama: TD | null } | null>(null);
  const daftar = q.data ?? [];
  async function hapus(t: TD) {
    if (!window.confirm(`Hapus ${t.kode}? Bila sudah dipakai data, tahun dasar diarsipkan (baca saja).`)) return;
    await aksi.jalankan(() => api<HasilHapus>(`/api/tahun-dasar/${t.id}`, { metode: "DELETE" }), (r) => r.pesan);
  }
  return (
    <div className="grid gap-4 xl:grid-cols-[minmax(0,2fr)_minmax(300px,1fr)]">
      <div className="min-w-0 space-y-2">
        <Tombol varian="utama" onClick={() => setMode({ lama: null })}>+ Tahun dasar</Tombol>
        {aksi.pesan && <Pesan jenis={aksi.pesan.jenis}>{aksi.pesan.teks}</Pesan>}
        <table className={`${kelasTabel} rounded border border-slate-200 bg-white`} aria-label="Tahun dasar">
          <thead><tr>{["Kode", "Klasifikasi", "Status", "Seri", "Baseline", "Jangkar dari data", "Aksi"].map((h) => <th key={h} className={kelasTh}>{h}</th>)}</tr></thead>
          <tbody>
            {daftar.map((t) => (
              <tr key={t.id}>
                <td className={`${kelasTd} font-semibold`}>{t.kode}</td>
                <td className={kelasTd}>{t.klasifikasi.replace("KBLI", "KBLI ")}</td>
                <td className={kelasTd}><Lencana warna={t.status === "produksi" ? "hijau" : t.status === "arsip" ? "abu" : "biru"}>{t.status}</Lencana></td>
                <td className={kelasTd}>{t.tahun_awal_seri}+</td>
                <td className={kelasTd}>{t.tahun_baseline_eks}</td>
                <td className={kelasTd}>{t.jangkar_dari_data ? "ya" : "tidak (wajib isi)"}</td>
                <td className={`${kelasTd} whitespace-nowrap`}>
                  <Tombol kecil varian="teks" onClick={() => setMode({ lama: t })}>Ubah</Tombol>
                  <Tombol kecil varian="teks" className="text-red-700" onClick={() => hapus(t)}>Hapus</Tombol>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div>{mode && <Formulir key={mode.lama?.id ?? "baru"} lama={mode.lama} daftar={daftar} selesai={(p) => { setMode(null); if (p) aksi.setPesan({ jenis: "ok", teks: p }); }} />}</div>
    </div>
  );
}
