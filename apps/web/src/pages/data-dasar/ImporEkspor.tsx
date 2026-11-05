import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { GalatApi, unduhBerkas, unggahBerkas, type Profil } from "../../api/klien";
import { Centang, Lencana, Panel, Pesan, Tombol, kelasTabel, kelasTd, kelasTh } from "../../components/ui";
import { formatAngka } from "../../lib/tempel";
import type { Putaran } from "../DataDasar";

interface PesanImpor { tingkat: "galat" | "peringatan" | "info"; teks: string; sheet?: string; baris?: number; kolom?: string; kode?: string }
export interface Pratinjau {
  impor_id: number;
  jenis: string;
  nama_berkas: string;
  dapat_diterapkan: boolean;
  ringkasan: Record<string, number>;
  item_baru: { wilayah: string; lapus: string; metode: string; no: number; nama: string }[];
  sel: { wilayah: string; lapus: string; metode: string; no: number; seri: string; periode: string; lama: number | null; baru: number | null }[];
  sel_terpotong: boolean;
  tautan: { lapus: string; metode: string; no: number; seri: string; lama: string | null; baru: string | null }[];
  seri_referensi_baru: { kode: string; nama: string; jenis: string }[];
  penyesuaian: { lapus: string; tahap: string; jenis: string; harga: string; periode: string; lama: number | null; baru: number | null; status: string }[];
  pesan: PesanImpor[];
  jumlah_pesan: number;
}

const LABEL: Record<string, string> = {
  item_baru: "Item baru", item_berubah: "Item berubah", sel_baru: "Sel baru", sel_berubah: "Sel berubah", sel_dihapus: "Sel dihapus",
  parameter: "Jangkar", tautan: "Tautan", metadata_seri: "Metadata seri", seri_referensi_baru: "Seri referensi baru",
  sel_seri_referensi: "Sel seri referensi", penyesuaian: "Penyesuaian", dilewati: "Baris dilewati", galat: "Galat", peringatan: "Peringatan",
};

/** Impor templat/CSV (pratinjau selisih -> terapkan) dan ekspor templat, CSV panjang, seri referensi. */
export function ImporEkspor({ putaran, wilayah }: { putaran: Putaran; wilayah: string }) {
  const qc = useQueryClient();
  const profil = qc.getQueryData<Profil>(["saya"]);
  const izin = new Set(profil?.izin ?? []);
  const [berkas, setBerkas] = useState<File | null>(null);
  const [kosongkan, setKosongkan] = useState(false);
  const [setujui, setSetujui] = useState(false);
  const [prat, setPrat] = useState<Pratinjau | null>(null);
  const [pesan, setPesan] = useState<{ jenis: "ok" | "galat" | "info"; teks: string } | null>(null);
  const [sibuk, setSibuk] = useState(false);
  const terkunci = putaran.status === "terkunci";

  async function pratinjau() {
    if (!berkas) return;
    setSibuk(true);
    setPesan(null);
    setPrat(null);
    try {
      const q = new URLSearchParams({ putaran_id: String(putaran.id), nama: berkas.name, kosongkan: String(kosongkan), setujui_penyesuaian: String(setujui) });
      setPrat(await unggahBerkas<Pratinjau>(`/api/impor/templat?${q}`, berkas));
    } catch (e) {
      setPesan({ jenis: "galat", teks: e instanceof GalatApi ? e.message : "Pratinjau gagal." });
    } finally {
      setSibuk(false);
    }
  }

  async function terapkan() {
    if (!berkas || !prat) return;
    setSibuk(true);
    try {
      const r = await unggahBerkas<{ pesan: string }>(`/api/impor/${prat.impor_id}/terapkan`, berkas);
      setPesan({ jenis: "ok", teks: r.pesan });
      setPrat(null);
      setBerkas(null);
      qc.invalidateQueries({ queryKey: ["grid", putaran.id] });
    } catch (e) {
      setPesan({ jenis: "galat", teks: e instanceof GalatApi ? e.message : "Penerapan gagal." });
    } finally {
      setSibuk(false);
    }
  }

  async function unduh(jalur: string, nama: string) {
    try {
      await unduhBerkas(jalur, nama);
    } catch (e) {
      setPesan({ jenis: "galat", teks: e instanceof GalatApi ? e.message : "Unduhan gagal." });
    }
  }

  return (
    <div className="grid gap-4 lg:grid-cols-[1fr_340px]">
      <Panel judul="Impor templat / CSV">
        <p className="mb-2 text-xs text-slate-500">
          Templat .xlsx (format docs/05) atau CSV panjang. Sistem selalu menampilkan pratinjau selisih dulu; sel kosong di berkas tidak
          menghapus nilai. Berkas tidak disimpan di server.
        </p>
        <div className="mb-2 flex flex-wrap items-center gap-3">
          <input type="file" accept=".xlsx,.csv" aria-label="Berkas impor" onChange={(e) => { setBerkas(e.target.files?.[0] ?? null); setPrat(null); }} className="text-sm" />
          {izin.has("data.tulis_semua") && <Centang label="Kosongkan sel yang kosong di berkas (admin)" checked={kosongkan} onChange={(e) => setKosongkan(e.target.checked)} />}
          {izin.has("penyesuaian.putus") && <Centang label="Setujui penyesuaian dari berkas" checked={setujui} onChange={(e) => setSetujui(e.target.checked)} />}
          <Tombol varian="utama" disabled={!berkas || sibuk || terkunci} onClick={pratinjau}>Pratinjau</Tombol>
        </div>
        {pesan && <div className="mb-2"><Pesan jenis={pesan.jenis}>{pesan.teks}</Pesan></div>}
        {prat && <TampilPratinjau p={prat} />}
        {prat && (
          <div className="mt-3 flex items-center gap-2">
            <Tombol varian="utama" disabled={!prat.dapat_diterapkan || sibuk} onClick={terapkan}>Terapkan ke putaran</Tombol>
            {!prat.dapat_diterapkan && <span className="text-sm text-red-700">Perbaiki galat format lalu unggah ulang.</span>}
          </div>
        )}
      </Panel>
      <Panel judul="Ekspor">
        <div className="grid gap-2">
          <Tombol onClick={() => unduh(`/api/ekspor/templat?putaran_id=${putaran.id}&wilayah=${wilayah}`, "templat.xlsx")}>Templat terisi ({wilayah})</Tombol>
          <Tombol onClick={() => unduh(`/api/ekspor/templat?putaran_id=${putaran.id}`, "templat.xlsx")}>Templat terisi (semua wilayah)</Tombol>
          <Tombol onClick={() => unduh(`/api/ekspor/templat?putaran_id=${putaran.id}&kosong=true`, "templat_kosong.xlsx")}>Templat kosong (daftar item)</Tombol>
          <Tombol onClick={() => unduh(`/api/ekspor/csv?putaran_id=${putaran.id}&wilayah=${wilayah}`, "data_dasar.csv")}>CSV panjang ({wilayah})</Tombol>
          <Tombol onClick={() => unduh(`/api/ekspor/seri-referensi?putaran_id=${putaran.id}`, "seri_referensi.csv")}>Seri referensi (CSV)</Tombol>
          <p className="text-xs text-slate-500">Berkas ekspor bertanda air dan tercatat di jejak audit. Simpan di folder terbatas.</p>
        </div>
      </Panel>
    </div>
  );
}

function TampilPratinjau({ p }: { p: Pratinjau }) {
  const r = p.ringkasan;
  const galat = p.pesan.filter((x) => x.tingkat === "galat");
  const lain = p.pesan.filter((x) => x.tingkat !== "galat");
  return (
    <div className="grid gap-3 text-sm">
      <div className="flex flex-wrap gap-1">
        {Object.entries(LABEL).filter(([k]) => r[k]).map(([k, l]) => (
          <Lencana key={k} warna={k === "galat" ? "merah" : k === "peringatan" || k === "dilewati" ? "kuning" : "biru"}>{l}: {r[k]}</Lencana>
        ))}
        {!Object.keys(LABEL).some((k) => r[k]) && <Lencana warna="hijau">Tidak ada perubahan</Lencana>}
      </div>
      {galat.length > 0 && <DaftarPesan judul="Galat format (baris ditolak)" pesan={galat} />}
      {lain.length > 0 && <DaftarPesan judul="Peringatan dan info" pesan={lain} />}
      {p.item_baru.length > 0 && (
        <details>
          <summary className="cursor-pointer font-medium">Item baru ({r.item_baru})</summary>
          <ul className="mt-1 max-h-40 overflow-auto text-xs">{p.item_baru.map((x, i) => <li key={i}>{x.wilayah} {x.lapus} {x.metode} {x.no} — {x.nama}</li>)}</ul>
        </details>
      )}
      {p.sel.length > 0 && (
        <details open={p.sel.length <= 50}>
          <summary className="cursor-pointer font-medium">Sel berubah (lama → baru){p.sel_terpotong ? " — sebagian" : ""}</summary>
          <div className="mt-1 max-h-72 overflow-auto">
            <table className={kelasTabel}>
              <thead><tr>{["Wil", "Lapus", "Item", "Seri", "Periode", "Lama", "Baru"].map((h) => <th key={h} className={kelasTh}>{h}</th>)}</tr></thead>
              <tbody>
                {p.sel.slice(0, 500).map((s, i) => (
                  <tr key={i}>
                    <td className={kelasTd}>{s.wilayah}</td><td className={kelasTd}>{s.lapus}</td><td className={kelasTd}>{s.metode} {s.no}</td>
                    <td className={kelasTd}>{s.seri}</td><td className={kelasTd}>{s.periode}</td>
                    <td className={`${kelasTd} text-right text-slate-500`}>{s.lama === null ? "kosong" : formatAngka(s.lama)}</td>
                    <td className={`${kelasTd} text-right font-medium`}>{s.baru === null ? "dihapus" : formatAngka(s.baru)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </details>
      )}
      {p.tautan.length > 0 && (
        <details>
          <summary className="cursor-pointer font-medium">Tautan/rumus ({r.tautan})</summary>
          <ul className="mt-1 max-h-40 overflow-auto text-xs">{p.tautan.map((t, i) => <li key={i}>{t.lapus} {t.metode} {t.no} {t.seri}: {t.lama ?? "manual"} → {t.baru ?? "manual"}</li>)}</ul>
        </details>
      )}
      {p.seri_referensi_baru.length > 0 && (
        <details>
          <summary className="cursor-pointer font-medium">Seri referensi baru ({p.seri_referensi_baru.length})</summary>
          <ul className="mt-1 text-xs">{p.seri_referensi_baru.map((s) => <li key={s.kode}>{s.kode} — {s.nama}</li>)}</ul>
        </details>
      )}
      {p.penyesuaian.length > 0 && (
        <details>
          <summary className="cursor-pointer font-medium">Penyesuaian ({r.penyesuaian})</summary>
          <ul className="mt-1 max-h-40 overflow-auto text-xs">{p.penyesuaian.map((a, i) => <li key={i}>{a.lapus} {a.tahap} {a.jenis} {a.harga} {a.periode}: {a.lama === null ? "—" : formatAngka(a.lama)} → {a.baru === null ? "dihapus" : formatAngka(a.baru)} ({a.status ?? "dihapus"})</li>)}</ul>
        </details>
      )}
    </div>
  );
}

function DaftarPesan({ judul, pesan }: { judul: string; pesan: PesanImpor[] }) {
  return (
    <details open>
      <summary className="cursor-pointer font-medium">{judul} ({pesan.length})</summary>
      <ul className="mt-1 max-h-48 overflow-auto text-xs">
        {pesan.slice(0, 300).map((m, i) => (
          <li key={i} className={m.tingkat === "galat" ? "text-red-700" : m.tingkat === "peringatan" ? "text-amber-700" : "text-slate-600"}>
            {[m.sheet, m.baris ? `baris ${m.baris}` : null, m.kolom].filter(Boolean).join(" · ")}{m.sheet ? ": " : ""}{m.teks}{m.kode ? ` [${m.kode}]` : ""}
          </li>
        ))}
      </ul>
    </details>
  );
}
