import { useState } from "react";
import { api } from "../../api/klien";
import { useAksi, useDaftar } from "../../api/hooks";
import type { HasilHapus, Izin, Peran } from "../../api/tipe";
import { Lencana, Masukan, Pesan, Tombol, kelasTabel, kelasTd, kelasTh } from "../../components/ui";

export function PeranIzinTab() {
  const peran = useDaftar<Peran[]>(["peran"], "/api/peran").data ?? [];
  const izin = useDaftar<Izin[]>(["izin"], "/api/izin").data ?? [];
  const aksi = useAksi([["peran"], ["saya"]]);
  const [baru, setBaru] = useState({ kode: "", nama: "" });
  // Tampilan optimistis: centang langsung berubah; kembali ke data server bila ditolak.
  const [lokal, setLokal] = useState<Record<number, string[]>>({});
  const izinDari = (p: Peran) => lokal[p.id] ?? p.izin;

  async function ubahIzin(p: Peran, kode: string, nyala: boolean) {
    const sekarang = izinDari(p);
    const target = nyala ? [...sekarang, kode] : sekarang.filter((x) => x !== kode);
    setLokal((l) => ({ ...l, [p.id]: target }));
    await aksi.jalankan(() => api(`/api/peran/${p.id}`, { metode: "PATCH", isi: { izin: target } }), `Izin ${p.nama} diperbarui.`);
    setLokal((l) => { const n = { ...l }; delete n[p.id]; return n; });
  }

  return (
    <div className="space-y-3">
      <p className="text-sm text-slate-600">Centang = peran memiliki izin. Perubahan berlaku pada permintaan berikutnya pengguna terkait.</p>
      {aksi.pesan && <Pesan jenis={aksi.pesan.jenis}>{aksi.pesan.teks}</Pesan>}
      <div className="flex flex-wrap items-end gap-2">
        <div className="w-40"><Masukan placeholder="kode (mis. analis)" aria-label="Kode peran baru" value={baru.kode} onChange={(e) => setBaru({ ...baru, kode: e.target.value })} /></div>
        <div className="w-56"><Masukan placeholder="Nama peran" aria-label="Nama peran baru" value={baru.nama} onChange={(e) => setBaru({ ...baru, nama: e.target.value })} /></div>
        <Tombol varian="utama" disabled={!baru.kode || !baru.nama}
          onClick={async () => { if (await aksi.jalankan(() => api("/api/peran", { metode: "POST", isi: { ...baru, izin: [] } }), "Peran ditambahkan.")) setBaru({ kode: "", nama: "" }); }}>
          + Peran
        </Tombol>
      </div>
      <div className="overflow-auto rounded border border-slate-200 bg-white">
        <table className={kelasTabel} aria-label="Matriks peran dan izin">
          <thead>
            <tr>
              <th className={kelasTh}>Izin</th>
              {peran.map((p) => (
                <th key={p.id} className={`${kelasTh} text-center`}>
                  <div>{p.nama}</div>
                  <div className="text-xs font-normal text-slate-500">{p.jumlah_pengguna} pengguna {!p.aktif && <Lencana>nonaktif</Lencana>}</div>
                  <Tombol kecil varian="teks" className="text-red-700"
                    onClick={() => window.confirm(`Hapus peran ${p.nama}? Bila masih dipakai, peran dinonaktifkan dan tidak memberi izin.`) && aksi.jalankan(() => api<HasilHapus>(`/api/peran/${p.id}`, { metode: "DELETE" }), (r) => r.pesan)}>
                    Hapus
                  </Tombol>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {izin.map((i) => (
              <tr key={i.kode}>
                <td className={kelasTd}><div>{i.nama}</div><div className="font-mono text-xs text-slate-500">{i.kode}</div></td>
                {peran.map((p) => (
                  <td key={p.id} className={`${kelasTd} text-center`}>
                    <input type="checkbox" className="h-4 w-4 accent-merek-600" aria-label={`${p.nama}: ${i.kode}`}
                      checked={izinDari(p).includes(i.kode)} onChange={(e) => ubahIzin(p, i.kode, e.target.checked)} />
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
