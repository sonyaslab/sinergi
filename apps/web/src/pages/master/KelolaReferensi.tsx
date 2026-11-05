import { useState, type FormEvent } from "react";
import { api } from "../../api/klien";
import { useAksi, useDaftar } from "../../api/hooks";
import type { HasilHapus } from "../../api/tipe";
import { Centang, Isian, Lencana, Masukan, Panel, Pesan, Pilihan, Tombol, kelasTabel, kelasTd, kelasTh } from "../../components/ui";

// Editor referensi generik (satuan, sumber data, wilayah, katalog): tabel + formulir dari konfigurasi kolom.
export interface Kolom {
  kunci: string;
  label: string;
  tipe?: "teks" | "angka" | "pilihan" | "daftar";
  pilihan?: { nilai: string; label: string }[];
  wajib?: boolean;
  tetap?: boolean; // hanya diisi saat tambah (kunci utama)
  petunjuk?: string;
  pola?: string;
}

type Baris = Record<string, unknown> & { aktif?: boolean };

interface Props {
  judul: string;
  jalur: string; // mis. /api/satuan
  kunci: string; // kolom kunci utama (kode/id)
  kolom: Kolom[];
  cari?: boolean;
}

function teks(v: unknown): string {
  if (Array.isArray(v)) return v.join(", ");
  return v === null || v === undefined ? "" : String(v);
}

function Formulir({ props, lama, selesai }: { props: Props; lama: Baris | null; selesai: (pesan?: string) => void }) {
  const awal = Object.fromEntries(props.kolom.map((k) => [k.kunci, teks(lama?.[k.kunci])]));
  const [isi, setIsi] = useState<Record<string, string>>(awal);
  const [aktif, setAktif] = useState(lama?.aktif ?? true);
  const aksi = useAksi([[props.jalur]]);

  async function kirim(e: FormEvent) {
    e.preventDefault();
    const data: Record<string, unknown> = {};
    for (const k of props.kolom) {
      if (lama && k.tetap) continue;
      const v = isi[k.kunci]?.trim() ?? "";
      data[k.kunci] = k.tipe === "angka" ? (v === "" ? null : Number(v)) : k.tipe === "daftar" ? v.split(",").map((x) => x.trim()).filter(Boolean) : v === "" ? null : v;
    }
    if (lama && "aktif" in lama) data.aktif = aktif;
    const jalur = lama ? `${props.jalur}/${encodeURIComponent(String(lama[props.kunci]))}` : props.jalur;
    const r = await aksi.jalankan(() => api(jalur, { metode: lama ? "PATCH" : "POST", isi: data }));
    if (r) selesai(lama ? "Tersimpan." : "Ditambahkan.");
  }

  return (
    <Panel judul={lama ? `Ubah ${teks(lama[props.kolom[0].kunci])}` : `Tambah ${props.judul.toLowerCase()}`} tutup={() => selesai()}>
      <form onSubmit={kirim} className="space-y-2">
        {aksi.pesan && <Pesan jenis={aksi.pesan.jenis}>{aksi.pesan.teks}</Pesan>}
        {props.kolom.map((k) => (
          <Isian key={k.kunci} label={k.label} petunjuk={k.petunjuk}>
            {k.tipe === "pilihan" ? (
              <Pilihan value={isi[k.kunci]} required={k.wajib} disabled={!!lama && k.tetap} onChange={(e) => setIsi({ ...isi, [k.kunci]: e.target.value })}>
                {!k.wajib && <option value="">(kosong)</option>}
                {k.pilihan?.map((p) => <option key={p.nilai} value={p.nilai}>{p.label}</option>)}
              </Pilihan>
            ) : (
              <Masukan value={isi[k.kunci]} required={k.wajib} disabled={!!lama && k.tetap} pattern={k.pola}
                type={k.tipe === "angka" ? "number" : "text"} onChange={(e) => setIsi({ ...isi, [k.kunci]: e.target.value })} />
            )}
          </Isian>
        ))}
        {lama && "aktif" in lama && <Centang label="Aktif" checked={aktif} onChange={(e) => setAktif(e.target.checked)} />}
        <div><Tombol varian="utama" type="submit" disabled={aksi.sibuk}>Simpan</Tombol></div>
      </form>
    </Panel>
  );
}

export function KelolaReferensi(props: Props) {
  const [q, setQ] = useState("");
  const jalurDaftar = props.cari && q.trim() ? `${props.jalur}?q=${encodeURIComponent(q.trim())}` : props.jalur;
  const daftar = useDaftar<Baris[]>([props.jalur, props.cari ? q.trim() : ""], jalurDaftar);
  const aksi = useAksi([[props.jalur]]);
  const [mode, setMode] = useState<{ lama: Baris | null } | null>(null);

  async function hapus(b: Baris) {
    const nama = teks(b[props.kolom[0].kunci]);
    if (!window.confirm(`Hapus ${nama}?\nBila sudah dipakai data, akan dinonaktifkan.`)) return;
    await aksi.jalankan(() => api<HasilHapus>(`${props.jalur}/${encodeURIComponent(String(b[props.kunci]))}`, { metode: "DELETE" }), (r) => r.pesan);
  }

  return (
    <div className="grid gap-4 xl:grid-cols-[minmax(0,2fr)_minmax(300px,1fr)]">
      <div className="min-w-0 space-y-2">
        <div className="flex items-center gap-2">
          <Tombol varian="utama" onClick={() => setMode({ lama: null })}>+ {props.judul}</Tombol>
          {props.cari && <div className="w-64"><Masukan placeholder="Cari nama atau sinonim…" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Cari" /></div>}
        </div>
        {aksi.pesan && <Pesan jenis={aksi.pesan.jenis}>{aksi.pesan.teks}</Pesan>}
        <div className="overflow-auto rounded border border-slate-200 bg-white">
          <table className={kelasTabel} aria-label={props.judul}>
            <thead>
              <tr>
                {props.kolom.map((k) => <th key={k.kunci} className={kelasTh}>{k.label}</th>)}
                <th className={kelasTh}>Status</th>
                <th className={kelasTh}>Aksi</th>
              </tr>
            </thead>
            <tbody>
              {(daftar.data ?? []).map((b) => (
                <tr key={String(b[props.kunci])} className={b.aktif === false ? "text-slate-400" : ""}>
                  {props.kolom.map((k) => (
                    <td key={k.kunci} className={kelasTd}>
                      {k.tipe === "pilihan" ? k.pilihan?.find((p) => p.nilai === b[k.kunci])?.label ?? teks(b[k.kunci]) : teks(b[k.kunci])}
                    </td>
                  ))}
                  <td className={kelasTd}>{b.aktif === false ? <Lencana>nonaktif</Lencana> : <Lencana warna="hijau">aktif</Lencana>}</td>
                  <td className={`${kelasTd} whitespace-nowrap`}>
                    <Tombol kecil varian="teks" onClick={() => setMode({ lama: b })}>Ubah</Tombol>
                    <Tombol kecil varian="teks" className="text-red-700" onClick={() => hapus(b)}>Hapus</Tombol>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
      <div>
        {mode && (
          <Formulir key={mode.lama ? String(mode.lama[props.kunci]) : "baru"} props={props} lama={mode.lama}
            selesai={(p) => { setMode(null); if (p) aksi.setPesan({ jenis: "ok", teks: p }); }} />
        )}
      </div>
    </div>
  );
}
