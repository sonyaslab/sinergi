import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useDaftar } from "../../api/hooks";
import { Lencana, Pilihan, kelasTabel, kelasTd, kelasTh } from "../../components/ui";
import { labelPeriode, LABEL_TINGKAT, type Temuan } from "../../lib/dataDasar";
import type { Putaran } from "../DataDasar";

interface Baris extends Temuan { nama: string; kode_lapus: string; boleh_konfirmasi: boolean }

/** Ringkasan temuan V01–V17 satu wilayah (per lapus), dapat disaring menurut tingkat. */
export function DaftarValidasi({ putaran, wilayah }: { putaran: Putaran; wilayah: string }) {
  useQueryClient();
  const [tingkat, setTingkat] = useState("");
  const q = useDaftar<Baris[]>(["validasi", putaran.id, wilayah, tingkat],
    `/api/validasi?putaran_id=${putaran.id}&wilayah=${wilayah}${tingkat ? `&tingkat=${tingkat}` : ""}`);
  const ts = q.data ?? [];
  const jumlah = ts.reduce<Record<string, number>>((a, t) => ({ ...a, [t.tingkat]: (a[t.tingkat] ?? 0) + (t.dikonfirmasi ? 0 : 1) }), {});
  return (
    <div>
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <div className="w-48">
          <Pilihan value={tingkat} onChange={(e) => setTingkat(e.target.value)} aria-label="Saring tingkat">
            <option value="">Semua tingkat</option>
            {Object.entries(LABEL_TINGKAT).map(([k, l]) => <option key={k} value={k}>{l}</option>)}
          </Pilihan>
        </div>
        {Object.entries(jumlah).map(([k, n]) => n > 0 && <Lencana key={k} warna={k.startsWith("blokir") ? "merah" : k === "peringatan" ? "kuning" : "biru"}>{LABEL_TINGKAT[k as Temuan["tingkat"]]}: {n}</Lencana>)}
        <span className="text-xs text-slate-500">Diperbarui otomatis setiap hitung ulang. Ambang V08/V11 diatur admin (per lapus, kalibrasi P95).</span>
      </div>
      <div className="max-h-[65vh] overflow-auto rounded border border-slate-200 bg-white">
        <table className={kelasTabel}>
          <thead><tr>{["Kode", "Tingkat", "Lapus", "Item", "Seri", "Periode", "Pesan"].map((h) => <th key={h} className={kelasTh}>{h}</th>)}</tr></thead>
          <tbody>
            {ts.map((t, i) => (
              <tr key={i} className={t.dikonfirmasi ? "text-slate-400" : ""}>
                <td className={kelasTd} title={t.nama}>{t.kode}</td>
                <td className={kelasTd}><Lencana warna={t.dikonfirmasi ? "hijau" : t.tingkat.startsWith("blokir") ? "merah" : t.tingkat === "peringatan" ? "kuning" : "biru"}>{t.dikonfirmasi ? "dikonfirmasi" : LABEL_TINGKAT[t.tingkat]}</Lencana></td>
                <td className={kelasTd}>{t.kode_lapus}</td>
                <td className={kelasTd}>{t.item_id ?? ""}</td>
                <td className={kelasTd}>{t.jenis_seri ?? ""}</td>
                <td className={kelasTd}>{t.periode !== null ? labelPeriode(t.periode) : ""}</td>
                <td className={kelasTd}>{t.pesan}</td>
              </tr>
            ))}
            {!ts.length && <tr><td className={kelasTd} colSpan={7}>{q.isLoading ? "Memuat…" : "Tidak ada temuan."}</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  );
}
