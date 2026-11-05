import { useState } from "react";
import { api } from "../../api/klien";
import { useAksi, useDaftar } from "../../api/hooks";
import type { Lapus, PenggunaAdmin, Penugasan, Wilayah } from "../../api/tipe";
import { useTahunDasar } from "../../konteks/TahunDasar";
import { Centang, Isian, Lencana, Masukan, Panel, Pesan, Pilihan, Tombol, kelasTabel, kelasTd, kelasTh } from "../../components/ui";

const BERDATA = new Set(["kategori", "sub", "daun", "top", "sop"]);

export function PenugasanTab() {
  const { aktif: td } = useTahunDasar();
  const pengguna = (useDaftar<PenggunaAdmin[]>(["pengguna"], "/api/pengguna").data ?? []).filter((u) => u.aktif && !u.akun_sistem);
  const wilayah = (useDaftar<Wilayah[]>(["/api/wilayah", ""], "/api/wilayah").data ?? []).filter((w) => w.aktif);
  const lapus = (useDaftar<Lapus[]>(["lapus", td?.id], td ? `/api/tahun-dasar/${td.id}/lapus` : null).data ?? []).filter((x) => x.aktif && BERDATA.has(x.jenis));
  const [filterPengguna, setFilterPengguna] = useState("");
  const daftar = useDaftar<Penugasan[]>(["penugasan", td?.id, filterPengguna], td ? `/api/penugasan?tahun_dasar_id=${td.id}${filterPengguna ? `&pengguna_id=${filterPengguna}` : ""}` : null);
  const aksi = useAksi([["penugasan"]]);
  const [f, setF] = useState({ pengguna: "", peran_tugas: "operator", sampai: "" });
  const [wil, setWil] = useState<Set<string>>(new Set());
  const [lp, setLp] = useState<Set<number>>(new Set());
  const toggle = <T,>(set: Set<T>, v: T, on: boolean) => { const n = new Set(set); if (on) n.add(v); else n.delete(v); return n; };

  if (!td) return <p className="text-slate-500">Pilih tahun dasar di header.</p>;

  async function simpan() {
    const r = await aksi.jalankan(() => api<{ jumlah: number; lapus_daun: number; wilayah: number }>("/api/penugasan", { metode: "POST", isi: {
      pengguna_id: Number(f.pengguna), tahun_dasar_id: td!.id, wilayah_kode: [...wil], lapus_ids: [...lp], peran_tugas: f.peran_tugas, berlaku_sampai: f.sampai || null,
    } }), (x) => `${x.jumlah} penugasan disimpan (${x.lapus_daun} lapus daun × ${x.wilayah} wilayah).`);
    if (r) { setLp(new Set()); }
  }

  return (
    <div className="grid gap-4 xl:grid-cols-[minmax(0,2fr)_minmax(340px,1fr)]">
      <div className="min-w-0 space-y-2">
        <div className="flex items-end gap-2">
          <div className="w-72"><Isian label="Saring pengguna"><Pilihan value={filterPengguna} onChange={(e) => setFilterPengguna(e.target.value)}><option value="">(semua)</option>{pengguna.map((u) => <option key={u.id} value={u.id}>{u.nama} ({u.username})</option>)}</Pilihan></Isian></div>
          <span className="pb-2 text-xs text-slate-500">Tahun dasar: <b>{td.kode}</b> (ganti di header)</span>
        </div>
        {aksi.pesan && <Pesan jenis={aksi.pesan.jenis}>{aksi.pesan.teks}</Pesan>}
        <div className="overflow-auto rounded border border-slate-200 bg-white">
          <table className={kelasTabel} aria-label="Penugasan">
            <thead><tr>{["Pengguna", "Wilayah", "Lapus", "Tugas", "Berlaku", ""].map((h) => <th key={h} className={kelasTh}>{h}</th>)}</tr></thead>
            <tbody>
              {(daftar.data ?? []).map((p) => (
                <tr key={p.id} className={p.aktif ? "" : "text-slate-400"}>
                  <td className={kelasTd}>{p.nama} <span className="font-mono text-xs text-slate-500">{p.username}</span></td>
                  <td className={kelasTd}>{p.wilayah_kode}</td>
                  <td className={kelasTd}><span className="font-mono text-xs">{p.kode_lapus}</span> {p.nama_lapus}</td>
                  <td className={kelasTd}><Lencana warna={p.peran_tugas === "operator" ? "biru" : "abu"}>{p.peran_tugas}</Lencana></td>
                  <td className={`${kelasTd} text-xs`}>{p.berlaku_mulai} – {p.berlaku_sampai ?? "…"}</td>
                  <td className={kelasTd}>{p.aktif && <Tombol kecil varian="teks" className="text-red-700" onClick={() => aksi.jalankan(() => api(`/api/penugasan/${p.id}`, { metode: "DELETE" }), "Penugasan diakhiri.")}>Akhiri</Tombol>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
      <Panel judul="Tugaskan">
        <div className="space-y-2">
          <Isian label="Pengguna"><Pilihan value={f.pengguna} onChange={(e) => setF({ ...f, pengguna: e.target.value })}><option value="">—</option>{pengguna.map((u) => <option key={u.id} value={u.id}>{u.nama} ({u.username})</option>)}</Pilihan></Isian>
          <fieldset className="text-sm"><legend className="mb-1 text-slate-700">Wilayah</legend>
            <div className="flex flex-wrap gap-3">{wilayah.map((w) => <Centang key={w.kode} label={`${w.kode}`} title={w.nama} checked={wil.has(w.kode)} onChange={(e) => setWil(toggle(wil, w.kode, e.target.checked))} />)}</div>
          </fieldset>
          <fieldset className="text-sm"><legend className="mb-1 text-slate-700">Lapus <span className="text-xs text-slate-500">(kategori = semua lapus di bawahnya)</span></legend>
            <div className="max-h-64 overflow-auto rounded border border-slate-200 p-2">
              {lapus.map((x) => (
                <div key={x.id} style={{ paddingLeft: `${Math.max(0, x.level - 1) * 14}px` }}>
                  <Centang label={`${x.kode} ${x.nama}`} checked={lp.has(x.id)} onChange={(e) => setLp(toggle(lp, x.id, e.target.checked))} />
                </div>
              ))}
            </div>
          </fieldset>
          <div className="grid grid-cols-2 gap-2">
            <Isian label="Tugas"><Pilihan value={f.peran_tugas} onChange={(e) => setF({ ...f, peran_tugas: e.target.value })}><option value="operator">operator (isi data)</option><option value="pemeriksa">pemeriksa</option></Pilihan></Isian>
            <Isian label="Berlaku sampai"><Masukan type="date" value={f.sampai} onChange={(e) => setF({ ...f, sampai: e.target.value })} /></Isian>
          </div>
          <Tombol varian="utama" disabled={!f.pengguna || wil.size === 0 || lp.size === 0 || aksi.sibuk} onClick={simpan}>Simpan penugasan</Tombol>
        </div>
      </Panel>
    </div>
  );
}
