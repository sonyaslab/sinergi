import type { Profil } from "../api/klien";
import { useTahunDasar } from "../konteks/TahunDasar";

export function Beranda({ profil }: { profil: Profil }) {
  const { aktif } = useTahunDasar();
  const tugas = profil.penugasan.filter((p) => !aktif || p.tahun_dasar === aktif.kode);
  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">Selamat datang, {profil.nama}</h1>
      <div className="grid gap-4 md:grid-cols-3">
        <div className="rounded-lg border border-slate-200 bg-white p-4">
          <div className="text-xs uppercase text-slate-500">Tahun dasar</div>
          <div className="text-2xl font-bold text-merek-700">{aktif?.kode ?? "-"}</div>
          <div className="text-sm text-slate-600">{aktif ? `${aktif.klasifikasi.replace("KBLI", "KBLI ")} · seri ${aktif.tahun_awal_seri}+ · ${aktif.status}` : ""}</div>
        </div>
        <div className="rounded-lg border border-slate-200 bg-white p-4">
          <div className="text-xs uppercase text-slate-500">Peran</div>
          <div className="text-lg font-semibold">{profil.peran.join(", ") || "-"}</div>
        </div>
        <div className="rounded-lg border border-slate-200 bg-white p-4">
          <div className="text-xs uppercase text-slate-500">Lapus ditugaskan ({aktif?.kode ?? "-"})</div>
          <div className="text-2xl font-bold">{tugas.length}</div>
          <div className="truncate text-sm text-slate-600">{tugas.map((t) => `${t.wilayah_kode}:${t.lapus}`).join(", ")}</div>
        </div>
      </div>
      <p className="text-sm text-slate-500">Putaran aktif, heatmap status lapus × wilayah, dan daftar tugas tampil di sini mulai fase F4.</p>
    </div>
  );
}
