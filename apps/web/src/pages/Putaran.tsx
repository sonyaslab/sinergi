// Layar Putaran & Adjustment (F4): putaran (buka, cut-off, kunci), status lapus, adjustment, bandingkan putaran.
import { useMemo, useState } from "react";
import { useDaftar } from "../api/hooks";
import type { Lapus } from "../api/tipe";
import { PemilihPutaran, usePilihanPutaran } from "../components/PemilihPutaran";
import { Tab } from "../components/ui";
import { Bandingkan } from "./putaran/Bandingkan";
import { DaftarPenyesuaian } from "./putaran/DaftarPenyesuaian";
import { DaftarPutaran } from "./putaran/DaftarPutaran";
import { StatusLapus } from "./putaran/StatusLapus";

type Kunci = "putaran" | "status" | "adjustment" | "banding";
const TAB: { kunci: Kunci; label: string }[] = [
  { kunci: "putaran", label: "Putaran" },
  { kunci: "status", label: "Status lapus" },
  { kunci: "adjustment", label: "Adjustment" },
  { kunci: "banding", label: "Bandingkan putaran" },
];

export function PutaranAdjustment() {
  const pil = usePilihanPutaran();
  const [tab, setTab] = useState<Kunci>("putaran");
  const qLapus = useDaftar<Lapus[]>(["lapus", pil.td?.id], pil.td ? `/api/tahun-dasar/${pil.td.id}/lapus` : null).data;
  const lapus = useMemo(() => qLapus ?? [], [qLapus]);
  if (!pil.td) return <p className="text-slate-500">Memuat tahun dasar…</p>;
  return (
    <div>
      <h1 className="mb-2 text-xl font-semibold">Putaran & Adjustment</h1>
      <Tab daftar={TAB} aktif={tab} ubah={setTab} />
      {tab !== "putaran" && <PemilihPutaran p={pil} />}
      {tab === "putaran" && <DaftarPutaran pil={pil} />}
      {tab !== "putaran" && !pil.put && <p className="text-sm text-slate-500">Belum ada putaran. Buka putaran di tab Putaran.</p>}
      {pil.put && tab === "status" && <StatusLapus putaran={pil.put} wilayah={pil.wil} />}
      {pil.put && tab === "adjustment" && <DaftarPenyesuaian putaran={pil.put} wilayah={pil.wil} lapus={lapus} />}
      {pil.put && tab === "banding" && <Bandingkan putaran={pil.put} wilayah={pil.wil} semua={pil.putaran} />}
    </div>
  );
}
