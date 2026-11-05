import { useState } from "react";
import { api, type TahunDasar } from "../../api/klien";
import { useAksi, useDaftar } from "../../api/hooks";
import type { Konkordansi, Lapus, RingkasanAsal } from "../../api/tipe";
import { Isian, Lencana, Masukan, Pesan, Pilihan, Tombol, kelasTabel, kelasTd, kelasTh } from "../../components/ui";

function SelBobot({ k, simpan }: { k: Konkordansi; simpan: (id: number, bobot: number | null) => void }) {
  const [v, setV] = useState(k.bobot === null ? "" : String(k.bobot));
  const kirim = () => {
    const baru = v.trim() === "" ? null : Number(v.replace(",", "."));
    if (baru !== k.bobot && (baru === null || !Number.isNaN(baru))) simpan(k.id, baru);
  };
  return (
    <input aria-label={`Bobot ${k.kode_asal} ke ${k.kode_tujuan}`} className="w-20 rounded border border-amber-300 bg-amber-50 px-1 py-0.5 text-right text-sm"
      value={v} inputMode="decimal" onChange={(e) => setV(e.target.value)} onBlur={kirim} onKeyDown={(e) => e.key === "Enter" && kirim()} />
  );
}

export function KonkordansiTab() {
  const tds = useDaftar<TahunDasar[]>(["tahun-dasar"], "/api/tahun-dasar").data ?? [];
  const asalBawaan = tds.find((t) => t.klasifikasi === "KBLI2020")?.id;
  const tujuanBawaan = tds.find((t) => t.klasifikasi === "KBLI2025")?.id;
  const [asal, setAsal] = useState<number | undefined>();
  const [tujuan, setTujuan] = useState<number | undefined>();
  const a = asal ?? asalBawaan;
  const t = tujuan ?? tujuanBawaan;
  const jalur = a && t ? `/api/konkordansi?asal_td=${a}&tujuan_td=${t}` : null;
  const q = useDaftar<{ baris: Konkordansi[]; ringkasan_asal: Record<string, RingkasanAsal> }>(["konkordansi", a, t], jalur);
  const lapusAsal = useDaftar<Lapus[]>(["lapus", a], a ? `/api/tahun-dasar/${a}/lapus` : null).data ?? [];
  const lapusTujuan = useDaftar<Lapus[]>(["lapus", t], t ? `/api/tahun-dasar/${t}/lapus` : null).data ?? [];
  const aksi = useAksi([["konkordansi"]]);
  const [baru, setBaru] = useState({ asal: "", tujuan: "", bobot: "" });
  const ringkas = q.data?.ringkasan_asal ?? {};
  const berdata = (x: Lapus) => !["kelompok", "ntb", "top", "sop", "topsop", "pdrb", "pdrb_nonmigas"].includes(x.jenis);

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-end gap-3">
        <div className="w-40"><Isian label="Dari (asal)"><Pilihan value={a ?? ""} onChange={(e) => setAsal(Number(e.target.value))}>{tds.map((x) => <option key={x.id} value={x.id}>{x.kode}</option>)}</Pilihan></Isian></div>
        <div className="w-40"><Isian label="Ke (tujuan)"><Pilihan value={t ?? ""} onChange={(e) => setTujuan(Number(e.target.value))}>{tds.map((x) => <option key={x.id} value={x.id}>{x.kode}</option>)}</Pilihan></Isian></div>
        <p className="text-xs text-slate-500">Bobot 1:N diisi dari SUT/SE2026. Jumlah bobot per lapus asal = 1. Selama kosong, laporan jembatan memakai jumlah kategori.</p>
      </div>
      {aksi.pesan && <Pesan jenis={aksi.pesan.jenis}>{aksi.pesan.teks}</Pesan>}
      <div className="flex flex-wrap items-end gap-2 rounded border border-slate-200 bg-white p-2">
        <div className="w-56"><Isian label="Lapus asal"><Pilihan value={baru.asal} onChange={(e) => setBaru({ ...baru, asal: e.target.value })}><option value="">—</option>{lapusAsal.filter(berdata).map((x) => <option key={x.id} value={x.id}>{x.kode} {x.nama}</option>)}</Pilihan></Isian></div>
        <div className="w-56"><Isian label="Lapus tujuan"><Pilihan value={baru.tujuan} onChange={(e) => setBaru({ ...baru, tujuan: e.target.value })}><option value="">—</option>{lapusTujuan.filter(berdata).map((x) => <option key={x.id} value={x.id}>{x.kode} {x.nama}</option>)}</Pilihan></Isian></div>
        <div className="w-24"><Isian label="Bobot"><Masukan inputMode="decimal" value={baru.bobot} onChange={(e) => setBaru({ ...baru, bobot: e.target.value })} /></Isian></div>
        <Tombol varian="utama" disabled={!baru.asal || !baru.tujuan || aksi.sibuk}
          onClick={async () => { const r = await aksi.jalankan(() => api("/api/konkordansi", { metode: "POST", isi: { lapus_asal_id: Number(baru.asal), lapus_tujuan_id: Number(baru.tujuan), bobot: baru.bobot ? Number(baru.bobot.replace(",", ".")) : null } }), "Padanan ditambahkan."); if (r) setBaru({ asal: "", tujuan: "", bobot: "" }); }}>
          + Padanan
        </Tombol>
      </div>
      <table className={`${kelasTabel} bg-white`} aria-label="Konkordansi">
        <thead><tr>{["Asal", "Tujuan", "Bobot", "Catatan", "Jumlah bobot asal", ""].map((h) => <th key={h} className={kelasTh}>{h}</th>)}</tr></thead>
        <tbody>
          {(q.data?.baris ?? []).map((k) => {
            const r = ringkas[k.kode_asal];
            return (
              <tr key={k.id}>
                <td className={kelasTd}><span className="font-mono text-xs">{k.kode_asal}</span> {k.nama_asal}</td>
                <td className={kelasTd}><span className="font-mono text-xs">{k.kode_tujuan}</span> {k.nama_tujuan}</td>
                <td className={kelasTd}><SelBobot key={`${k.id}-${k.bobot}`} k={k} simpan={(id, bobot) => aksi.jalankan(() => api(`/api/konkordansi/${id}`, { metode: "PATCH", isi: { bobot } }), "Bobot disimpan.")} /></td>
                <td className={`${kelasTd} text-xs text-slate-600`}>{k.catatan}</td>
                <td className={kelasTd}>
                  {r && (r.lengkap ? <Lencana warna="hijau">1 ✓</Lencana> : r.jumlah_tujuan === 1 && r.bobot_kosong === 1 ? <Lencana>1:1</Lencana> : <Lencana warna="kuning">{r.jumlah_bobot.toFixed(2)}{r.bobot_kosong ? ` (+${r.bobot_kosong} kosong)` : ""}</Lencana>)}
                </td>
                <td className={kelasTd}><Tombol kecil varian="teks" className="text-red-700" onClick={() => window.confirm("Hapus padanan ini?") && aksi.jalankan(() => api(`/api/konkordansi/${k.id}`, { metode: "DELETE" }), "Padanan dihapus.")}>Hapus</Tombol></td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
