// Pemilih putaran + wilayah bersama layar F4 (pilihan diingat per peramban; aman bila penyimpanan tidak tersedia).
import { useEffect, useMemo, useState } from "react";
import { useDaftar } from "../api/hooks";
import type { Wilayah } from "../api/tipe";
import { useTahunDasar } from "../konteks/TahunDasar";
import type { Putaran } from "../pages/DataDasar";
import { Isian, Lencana, Pilihan } from "./ui";

function baca(kunci: string): string | null {
  try {
    return localStorage.getItem(kunci);
  } catch {
    return null;
  }
}

function tulis(kunci: string, nilai: string): void {
  try {
    localStorage.setItem(kunci, nilai);
  } catch {
    /* penyimpanan peramban tidak tersedia: pilihan berlaku selama halaman terbuka */
  }
}

export function usePilihanPutaran() {
  const { aktif: td } = useTahunDasar();
  const q = useDaftar<Putaran[]>(["putaran", td?.id], td ? `/api/putaran?tahun_dasar_id=${td.id}` : null);
  const putaran = useMemo(() => q.data ?? [], [q.data]);
  const kunciPut = `sinergi_putaran_${td?.id ?? 0}`;
  const [putId, setPut] = useState<number | null>(() => Number(baca(kunciPut)) || null);
  const [wil, setWilState] = useState<string>(() => baca("sinergi_wilayah") ?? "6500");
  const wilayah = (useDaftar<Wilayah[]>(["/api/wilayah", ""], "/api/wilayah").data ?? []).filter((w) => w.aktif);
  useEffect(() => {
    if (putaran.length && !putaran.some((p) => p.id === putId)) {
      const simpan = Number(baca(kunciPut));
      setPut(putaran.some((p) => p.id === simpan) ? simpan : putaran[0].id);
    }
  }, [putaran, putId, kunciPut]);
  const put = putaran.find((p) => p.id === putId) ?? null;
  return {
    td,
    putaran,
    put,
    wil,
    wilayah,
    memuat: q.isLoading,
    setPutId: (id: number) => {
      setPut(id);
      tulis(kunciPut, String(id));
    },
    setWil: (w: string) => {
      setWilState(w);
      tulis("sinergi_wilayah", w);
    },
  };
}

export type PilihanPutaran = ReturnType<typeof usePilihanPutaran>;

export function PemilihPutaran({ p, tanpaWilayah = false }: { p: PilihanPutaran; tanpaWilayah?: boolean }) {
  return (
    <div className="mb-3 flex flex-wrap items-end gap-3">
      <div className="w-72">
        <Isian label="Putaran">
          <Pilihan value={p.put?.id ?? ""} onChange={(e) => p.setPutId(Number(e.target.value))} aria-label="Putaran">
            {p.putaran.length === 0 && <option value="">Belum ada putaran {p.td?.kode ?? ""}</option>}
            {p.putaran.map((x) => (
              <option key={x.id} value={x.id}>
                {x.nama} · {x.label_awal}–{x.label_akhir} {x.status === "terkunci" ? "(terkunci)" : ""}
              </option>
            ))}
          </Pilihan>
        </Isian>
      </div>
      {!tanpaWilayah && (
        <div className="w-60">
          <Isian label="Wilayah">
            <Pilihan value={p.wil} onChange={(e) => p.setWil(e.target.value)} aria-label="Wilayah">
              {p.wilayah.map((w) => <option key={w.kode} value={w.kode}>{w.kode} {w.nama}</option>)}
            </Pilihan>
          </Isian>
        </div>
      )}
      {p.put?.status === "terkunci" && <Lencana warna="abu">Terkunci (baca saja)</Lencana>}
      {p.put?.lewat_cutoff && p.put.status !== "terkunci" && <Lencana warna="kuning">Lewat cut-off: perubahan wajib beralasan</Lencana>}
    </div>
  );
}
