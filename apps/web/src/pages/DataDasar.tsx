// Layar Data Dasar (F3): kategori -> tab subkategori -> grid item x seri; seri referensi; impor/ekspor; validasi.
import { useMemo, useState } from "react";
import { useDaftar } from "../api/hooks";
import type { Lapus } from "../api/tipe";
import { PemilihPutaran, usePilihanPutaran } from "../components/PemilihPutaran";
import { Tab } from "../components/ui";
import { labelPeriode } from "../lib/dataDasar";
import { DaftarValidasi } from "./data-dasar/DaftarValidasi";
import { ImporEkspor } from "./data-dasar/ImporEkspor";
import { IsianData } from "./data-dasar/IsianData";
import { SeriReferensi } from "./data-dasar/SeriReferensi";

export interface Putaran {
  id: number;
  tahun_dasar_id: number;
  tahun_dasar: string;
  nama: string;
  jenis: string;
  status: string;
  tahun: number;
  triwulan: number;
  awal: number;
  akhir: number;
  label_awal: string;
  label_akhir: string;
  nomor?: number;
  catatan?: string | null;
  tanggal_cutoff?: string | null;
  lewat_cutoff?: boolean;
  sumber_putaran_id?: number | null;
  sumber?: string | null;
  dibuka_oleh?: string | null;
  dibuka_pada?: string | null;
  dikunci_oleh?: string | null;
  dikunci_pada?: string | null;
}

type Kunci = "isian" | "referensi" | "impor" | "validasi";
const TAB: { kunci: Kunci; label: string }[] = [
  { kunci: "isian", label: "Isian data" },
  { kunci: "referensi", label: "Seri referensi" },
  { kunci: "impor", label: "Impor & ekspor" },
  { kunci: "validasi", label: "Validasi" },
];

export function DataDasar() {
  const pil = usePilihanPutaran();
  const { td, put, wil } = pil;
  const [tab, setTab] = useState<Kunci>("isian");
  const qLapus = useDaftar<Lapus[]>(["lapus", td?.id], td ? `/api/tahun-dasar/${td.id}/lapus` : null).data;
  const lapus = useMemo(() => qLapus ?? [], [qLapus]);
  const akar = useMemo(() => lapus.filter((l) => l.aktif && l.induk_id === null && (l.jenis === "kategori" || l.jenis === "daun" || l.jenis === "top" || l.jenis === "sop")), [lapus]);

  if (!td) return <p className="text-slate-500">Memuat tahun dasar…</p>;
  return (
    <div>
      <h1 className="mb-2 text-xl font-semibold">Data dasar</h1>
      <PemilihPutaran p={pil} />
      {put && <p className="-mt-2 mb-2 text-xs text-slate-500">Triwulan berjalan: {labelPeriode(put.akhir)} · status {put.status}</p>}
      <Tab daftar={TAB} aktif={tab} ubah={setTab} />
      {!put && <p className="text-sm text-slate-500">Pilih atau buka putaran terlebih dahulu (menu Putaran & Adjustment).</p>}
      {put && tab === "isian" && <IsianData putaran={put} wilayah={wil} lapus={lapus} akar={akar} />}
      {put && tab === "referensi" && <SeriReferensi putaran={put} wilayah={wil} />}
      {put && tab === "impor" && <ImporEkspor putaran={put} wilayah={wil} />}
      {put && tab === "validasi" && <DaftarValidasi putaran={put} wilayah={wil} />}
    </div>
  );
}
