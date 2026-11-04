import { useTahunDasar } from "../konteks/TahunDasar";

const LABEL_STATUS: Record<string, string> = {
  produksi: "produksi",
  paralel: "paralel",
  rencana: "rencana",
  arsip: "arsip (baca saja)",
};

export function PemilihTahunDasar() {
  const { daftar, aktif, pilih, memuat } = useTahunDasar();
  if (memuat) return <span className="text-sm text-slate-500">Memuat…</span>;
  return (
    <label className="flex items-center gap-2 text-sm">
      <span className="text-slate-600">Tahun dasar</span>
      <select
        aria-label="Pilih tahun dasar"
        className="rounded border border-slate-300 bg-white px-2 py-1 font-semibold text-merek-700 focus:outline-none focus:ring-2 focus:ring-merek-500"
        value={aktif?.kode ?? ""}
        onChange={(e) => pilih(e.target.value)}
      >
        {daftar.map((t) => (
          <option key={t.kode} value={t.kode}>
            {t.kode} · {t.klasifikasi.replace("KBLI", "KBLI ")} · {LABEL_STATUS[t.status] ?? t.status}
          </option>
        ))}
      </select>
    </label>
  );
}
