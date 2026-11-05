// Layar Data Dasar (F3): kategori -> tab subkategori -> grid item x seri; seri referensi; impor/ekspor; validasi.
import { useEffect, useMemo, useState } from "react";
import { useDaftar } from "../api/hooks";
import type { Lapus, Wilayah } from "../api/tipe";
import { Isian, Pilihan, Tab } from "../components/ui";
import { useTahunDasar } from "../konteks/TahunDasar";
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
}

type Kunci = "isian" | "referensi" | "impor" | "validasi";
const TAB: { kunci: Kunci; label: string }[] = [
  { kunci: "isian", label: "Isian data" },
  { kunci: "referensi", label: "Seri referensi" },
  { kunci: "impor", label: "Impor & ekspor" },
  { kunci: "validasi", label: "Validasi" },
];

export function DataDasar() {
  const { aktif: td } = useTahunDasar();
  const [tab, setTab] = useState<Kunci>("isian");
  const qPutaran = useDaftar<Putaran[]>(["putaran", td?.id], td ? `/api/putaran?tahun_dasar_id=${td.id}` : null).data;
  const putaran = useMemo(() => qPutaran ?? [], [qPutaran]);
  const wilayah = (useDaftar<Wilayah[]>(["/api/wilayah", ""], "/api/wilayah").data ?? []).filter((w) => w.aktif);
  const qLapus = useDaftar<Lapus[]>(["lapus", td?.id], td ? `/api/tahun-dasar/${td.id}/lapus` : null).data;
  const lapus = useMemo(() => qLapus ?? [], [qLapus]);
  const [putId, setPutId] = useState<number | null>(null);
  const [wil, setWil] = useState("6500");
  useEffect(() => {
    if (putaran.length && !putaran.some((p) => p.id === putId)) setPutId(putaran[0].id);
  }, [putaran, putId]);
  const put = putaran.find((p) => p.id === putId) ?? null;
  const akar = useMemo(() => lapus.filter((l) => l.aktif && l.induk_id === null && (l.jenis === "kategori" || l.jenis === "daun" || l.jenis === "top" || l.jenis === "sop")), [lapus]);

  if (!td) return <p className="text-slate-500">Memuat tahun dasar…</p>;
  return (
    <div>
      <h1 className="mb-2 text-xl font-semibold">Data dasar</h1>
      <div className="mb-3 flex flex-wrap items-end gap-3">
        <div className="w-72">
          <Isian label="Putaran">
            <Pilihan value={putId ?? ""} onChange={(e) => setPutId(Number(e.target.value))} aria-label="Putaran">
              {putaran.length === 0 && <option value="">Belum ada putaran {td.kode}</option>}
              {putaran.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.nama} · {p.label_awal}–{p.label_akhir} {p.status === "terkunci" ? "(terkunci)" : ""}
                </option>
              ))}
            </Pilihan>
          </Isian>
        </div>
        <div className="w-60">
          <Isian label="Wilayah">
            <Pilihan value={wil} onChange={(e) => setWil(e.target.value)} aria-label="Wilayah">
              {wilayah.map((w) => <option key={w.kode} value={w.kode}>{w.kode} {w.nama}</option>)}
            </Pilihan>
          </Isian>
        </div>
        {put && <p className="pb-1.5 text-xs text-slate-500">Triwulan berjalan: {labelPeriode(put.akhir)} · status {put.status}</p>}
      </div>
      <Tab daftar={TAB} aktif={tab} ubah={setTab} />
      {!put && <p className="text-sm text-slate-500">Pilih atau buka putaran terlebih dahulu (menu Putaran, fase F4).</p>}
      {put && tab === "isian" && <IsianData putaran={put} wilayah={wil} lapus={lapus} akar={akar} />}
      {put && tab === "referensi" && <SeriReferensi putaran={put} wilayah={wil} />}
      {put && tab === "impor" && <ImporEkspor putaran={put} wilayah={wil} />}
      {put && tab === "validasi" && <DaftarValidasi putaran={put} wilayah={wil} />}
    </div>
  );
}
