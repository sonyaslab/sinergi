import { Link } from "react-router-dom";
import type { Profil } from "../api/klien";
import { useDaftar } from "../api/hooks";
import { usePilihanPutaran } from "../components/PemilihPutaran";
import { Lencana } from "../components/ui";
import { useTahunDasar } from "../konteks/TahunDasar";
import { LABEL_STATUS, SEL_STATUS, type StatusLapus } from "../lib/putaran";

interface Ringkasan {
  putaran: { id: number; nama: string; status: string };
  lapus: { id: number; kode: string; nama: string; jenis: string }[];
  wilayah: { kode: string; nama: string }[];
  sel: Record<string, Record<string, { status: StatusLapus; item: number }>>;
}

/** Tugas pengguna: operator = lapus ditugaskan yang perlu diisi/diajukan; pemeriksa = lapus diajukan. */
export function tugasSaya(r: Ringkasan, profil: Pick<Profil, "izin" | "penugasan">, td: string): { kode: string; wilayah: string; status: StatusLapus; aksi: string }[] {
  const out: { kode: string; wilayah: string; status: StatusLapus; aksi: string }[] = [];
  const kode = new Map(r.lapus.map((l) => [l.kode, l.id]));
  for (const p of profil.penugasan.filter((x) => x.tahun_dasar === td && x.peran_tugas === "operator")) {
    const id = kode.get(p.lapus);
    if (id === undefined) continue;
    const st = r.sel[p.wilayah_kode]?.[String(id)]?.status ?? "belum";
    if (st === "belum" || st === "draf" || st === "dikembalikan") out.push({ kode: p.lapus, wilayah: p.wilayah_kode, status: st, aksi: st === "dikembalikan" ? "perbaiki lalu ajukan" : "isi lalu ajukan" });
  }
  if (profil.izin.includes("lk.setujui")) {
    for (const [w, m] of Object.entries(r.sel))
      for (const l of r.lapus) if (m[String(l.id)]?.status === "diajukan") out.push({ kode: l.kode, wilayah: w, status: "diajukan", aksi: "periksa" });
  }
  return out;
}

export function Beranda({ profil }: { profil: Profil }) {
  const { aktif } = useTahunDasar();
  const pil = usePilihanPutaran();
  const put = pil.putaran.find((p) => p.status !== "terkunci") ?? pil.putaran[0] ?? null;
  const q = useDaftar<Ringkasan>(["status-ringkasan", put?.id], put ? `/api/status/ringkasan?putaran_id=${put.id}` : null);
  const r = q.data;
  const tugas = profil.penugasan.filter((p) => !aktif || p.tahun_dasar === aktif.kode);
  const daftarTugas = r && aktif ? tugasSaya(r, profil, aktif.kode) : [];
  const wil = r?.wilayah.filter((w) => Object.keys(r.sel[w.kode] ?? {}).length) ?? [];
  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">Selamat datang, {profil.nama}</h1>
      <div className="grid gap-4 md:grid-cols-4">
        <div className="rounded-lg border border-slate-200 bg-white p-4">
          <div className="text-xs uppercase text-slate-500">Tahun dasar</div>
          <div className="text-2xl font-bold text-merek-700">{aktif?.kode ?? "-"}</div>
          <div className="text-sm text-slate-600">{aktif ? `${aktif.klasifikasi.replace("KBLI", "KBLI ")} · seri ${aktif.tahun_awal_seri}+ · ${aktif.status}` : ""}</div>
        </div>
        <div className="rounded-lg border border-slate-200 bg-white p-4">
          <div className="text-xs uppercase text-slate-500">Putaran aktif</div>
          <div className="text-lg font-semibold">{put?.nama ?? "-"}</div>
          <div className="text-sm text-slate-600">{put ? `${put.label_awal}–${put.label_akhir} · ${put.status}` : "Belum ada putaran"}</div>
          {put?.lewat_cutoff && <Lencana warna="kuning">lewat cut-off</Lencana>}
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
      {daftarTugas.length > 0 && (
        <section className="rounded-lg border border-slate-200 bg-white p-4">
          <h2 className="mb-2 font-semibold">Tugas saya</h2>
          <ul className="grid gap-1 text-sm md:grid-cols-2">
            {daftarTugas.slice(0, 30).map((t, i) => (
              <li key={i}><span className={`mr-1 inline-block rounded px-1.5 text-xs ${SEL_STATUS[t.status]}`}>{LABEL_STATUS[t.status]}</span>{t.wilayah} · {t.kode}: {t.aksi}{" "}
                <Link className="text-merek-700 hover:underline" to={t.aksi === "periksa" ? "/putaran" : "/data-dasar"}>buka</Link></li>
            ))}
          </ul>
        </section>
      )}
      {r && (
        <section className="rounded-lg border border-slate-200 bg-white p-4">
          <h2 className="mb-2 font-semibold">Status lapus × wilayah · {r.putaran.nama}</h2>
          {!wil.length && <p className="text-sm text-slate-500">Belum ada lapus berisi pada putaran ini.</p>}
          {wil.length > 0 && (
            <div className="overflow-auto">
              <table className="border-collapse text-xs" aria-label="Heatmap status lapus">
                <thead><tr><th className="px-1 text-left">Wilayah</th>{r.lapus.map((l) => <th key={l.id} className="px-0.5 font-normal text-slate-500" title={l.nama}><span className="inline-block [writing-mode:vertical-rl]">{l.kode}</span></th>)}</tr></thead>
                <tbody>
                  {wil.map((w) => (
                    <tr key={w.kode}>
                      <th className="whitespace-nowrap px-1 text-left font-medium" title={w.nama}>{w.kode}</th>
                      {r.lapus.map((l) => {
                        const s = r.sel[w.kode]?.[String(l.id)];
                        const st = s?.status ?? "belum";
                        return <td key={l.id} className={`h-5 w-5 border border-white ${SEL_STATUS[st]}`} title={`${w.kode} ${l.kode}: ${LABEL_STATUS[st]}${s?.item ? ` · ${s.item} item` : ""}`} />;
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
              <div className="mt-2 flex flex-wrap gap-2 text-xs">
                {(Object.keys(LABEL_STATUS) as StatusLapus[]).map((k) => <span key={k}><span className={`mr-1 inline-block h-3 w-3 align-middle ${SEL_STATUS[k]}`} />{LABEL_STATUS[k]}</span>)}
              </div>
            </div>
          )}
        </section>
      )}
    </div>
  );
}
