// Dialog penyesuaian (adjustment) tiga tahap: isi nilai atau target (NTB / output / laju y-on-y / implisit) + alasan.
// Nilai dari target dihitung server (pratinjau draf + diajukan + disetujui) dengan membalik rumus docs/02 §6.
import { useEffect, useMemo, useState, type ReactNode } from "react";
import { api, GalatApi } from "../api/klien";
import { useDaftar } from "../api/hooks";
import { formatNilai, LABEL_MODE } from "../lib/putaran";
import { labelPeriode } from "../lib/dataDasar";
import { uraiAngka } from "../lib/tempel";
import { Dialog } from "./Dialog";
import { Isian, Masukan, Pesan, Pilihan, Tombol, kelasInput } from "./ui";

export type Tahap = "METODE" | "REKON" | "SIMULASI";
export interface JenisAdj {
  kode: string;
  tahap: Tahap;
  nama: string;
  ubah_angka: boolean;
  wajib_alasan: boolean;
  mode: Record<"CP" | "K", string[]>;
}
interface Rincian {
  nilai: number;
  target_ntb: number | null;
  target_output: number | null;
  ntb_sebelum: number | null;
  output_sebelum: number | null;
  label_periode: string;
}

export interface Props {
  putaran: { id: number; awal: number; akhir: number };
  wilayah: string;
  lapus: { id: number; kode: string; nama?: string }[];
  tahapBoleh: Tahap[];
  awal?: Partial<{ lapus_id: number; tahap: Tahap; metode: string; jenis: string; harga: "CP" | "K"; periode: number }>;
  metodeBoleh?: string[];
  info?: ReactNode;
  tutup: () => void;
  selesai: (pesan: string) => void;
}

const METODE = ["REV", "EKS", "DEF"];

export function DialogPenyesuaian({ putaran, wilayah, lapus, tahapBoleh, awal = {}, metodeBoleh = METODE, info, tutup, selesai }: Props) {
  const qJenis = useDaftar<JenisAdj[]>(["penyesuaian-jenis"], "/api/penyesuaian/jenis").data;
  const daftarJenis = useMemo(() => qJenis ?? [], [qJenis]);
  const [lapusId, setLapusId] = useState<number>(awal.lapus_id ?? lapus[0]?.id ?? 0);
  const [tahap, setTahap] = useState<Tahap>(awal.tahap ?? tahapBoleh[0]);
  const [metode, setMetode] = useState<string>(awal.metode ?? metodeBoleh[0] ?? "REV");
  const jenisTahap = useMemo(() => daftarJenis.filter((j) => j.tahap === tahap), [daftarJenis, tahap]);
  const [jenis, setJenis] = useState<string>(awal.jenis ?? "");
  const [harga, setHarga] = useState<"CP" | "K">(awal.harga ?? "K");
  const [periode, setPeriode] = useState<number>(awal.periode ?? putaran.akhir);
  const [mode, setMode] = useState("nilai");
  const [teks, setTeks] = useState("");
  const [alasan, setAlasan] = useState("");
  const [rincian, setRincian] = useState<Rincian | null>(null);
  const [galat, setGalat] = useState<string | null>(null);
  const [sibuk, setSibuk] = useState(false);

  useEffect(() => {
    if (jenisTahap.length && !jenisTahap.some((j) => j.kode === jenis)) setJenis(jenisTahap[0].kode);
  }, [jenisTahap, jenis]);
  const j = daftarJenis.find((x) => x.kode === jenis);
  const modeBoleh = useMemo(() => j?.mode[harga] ?? ["nilai"], [j, harga]);
  useEffect(() => {
    if (!modeBoleh.includes(mode)) setMode("nilai");
  }, [modeBoleh, mode]);
  useEffect(() => setRincian(null), [lapusId, tahap, metode, jenis, harga, periode, mode, teks]);

  const periodeOpsi = useMemo(() => {
    const out: number[] = [];
    for (let u = putaran.akhir; u >= putaran.awal; u--) out.push(u);
    return out;
  }, [putaran.awal, putaran.akhir]);

  function badan() {
    const a = uraiAngka(teks);
    if (a.jenis !== "angka") throw new Error(mode === "nilai" ? "Isi nilai penyesuaian dengan angka." : "Isi target dengan angka.");
    return {
      putaran_id: putaran.id, wilayah, lapus_id: lapusId, tahap, metode: tahap === "METODE" ? metode : null, jenis,
      harga, periode, mode, target: a.nilai, alasan: alasan.trim() || null,
    };
  }

  async function jalankan(simpan: boolean) {
    setGalat(null);
    setSibuk(true);
    try {
      const isi = badan();
      if (simpan) {
        const r = await api<{ pesan: string; nilai: number }>("/api/penyesuaian", { metode: "POST", isi });
        selesai(`${r.pesan} Nilai: ${formatNilai(r.nilai)}.`);
      } else {
        setRincian(await api<Rincian>("/api/penyesuaian/hitung", { metode: "POST", isi }));
      }
    } catch (e) {
      setGalat(e instanceof GalatApi || e instanceof Error ? e.message : "Gagal memproses penyesuaian.");
    } finally {
      setSibuk(false);
    }
  }

  const perluAlasan = j?.wajib_alasan ?? true;
  return (
    <Dialog judul={tahap === "SIMULASI" ? "Simulasi (penyesuaian akhir NTB)" : "Penyesuaian (adjustment)"} tutup={tutup} lebar="max-w-xl">
      {info && <div className="mb-3">{info}</div>}
      <div className="grid grid-cols-2 gap-3">
        <Isian label="Lapus">
          <Pilihan value={lapusId} onChange={(e) => setLapusId(Number(e.target.value))} aria-label="Lapus penyesuaian">
            {lapus.map((l) => <option key={l.id} value={l.id}>{l.kode}{l.nama ? ` — ${l.nama}` : ""}</option>)}
          </Pilihan>
        </Isian>
        <Isian label="Tahap">
          <Pilihan value={tahap} onChange={(e) => setTahap(e.target.value as Tahap)} aria-label="Tahap" disabled={tahapBoleh.length < 2}>
            {tahapBoleh.map((t) => <option key={t} value={t}>{t === "METODE" ? "Metode (ADJ1/ADJ2/SC)" : t === "REKON" ? "Rekonsiliasi (ADJ3/ADJ4/CT)" : "Simulasi"}</option>)}
          </Pilihan>
        </Isian>
        {tahap === "METODE" && (
          <Isian label="Metode">
            <Pilihan value={metode} onChange={(e) => setMetode(e.target.value)} aria-label="Metode">
              {metodeBoleh.map((m) => <option key={m} value={m}>{m}</option>)}
            </Pilihan>
          </Isian>
        )}
        <Isian label="Jenis">
          <Pilihan value={jenis} onChange={(e) => setJenis(e.target.value)} aria-label="Jenis penyesuaian">
            {jenisTahap.map((x) => <option key={x.kode} value={x.kode}>{x.kode} — {x.nama}</option>)}
          </Pilihan>
        </Isian>
        <Isian label="Harga">
          <Pilihan value={harga} onChange={(e) => setHarga(e.target.value as "CP" | "K")} aria-label="Harga">
            <option value="CP">ADHB (berlaku)</option>
            <option value="K">ADHK (konstan)</option>
          </Pilihan>
        </Isian>
        <Isian label="Triwulan">
          <Pilihan value={periode} onChange={(e) => setPeriode(Number(e.target.value))} aria-label="Triwulan">
            {periodeOpsi.map((u) => <option key={u} value={u}>{labelPeriode(u)}</option>)}
          </Pilihan>
        </Isian>
        <Isian label="Cara isi">
          <Pilihan value={mode} onChange={(e) => setMode(e.target.value)} aria-label="Cara isi">
            {modeBoleh.map((m) => <option key={m} value={m}>{LABEL_MODE[m] ?? m}</option>)}
          </Pilihan>
        </Isian>
        <Isian label={LABEL_MODE[mode] ?? "Nilai"} petunjuk={mode === "nilai" ? "Langsung ditambahkan pada tahap ini." : "Nilai dihitung sistem dari target."}>
          <Masukan value={teks} onChange={(e) => setTeks(e.target.value)} inputMode="decimal" aria-label="Nilai atau target" />
        </Isian>
      </div>
      <div className="mt-3">
        <Isian label={`Alasan${perluAlasan ? " (wajib, min. 10 karakter)" : ""}`}>
          <textarea className={kelasInput} rows={2} value={alasan} onChange={(e) => setAlasan(e.target.value)} aria-label="Alasan penyesuaian" />
        </Isian>
      </div>
      {rincian && (
        <div className="mt-3 rounded border border-slate-200 bg-slate-50 p-2 text-sm" aria-label="Hasil hitung penyesuaian">
          <div>Nilai penyesuaian {rincian.label_periode}: <b>{formatNilai(rincian.nilai)}</b></div>
          {rincian.ntb_sebelum !== null && <div className="text-xs text-slate-600">NTB tahap ini tanpa penyesuaian ini: {formatNilai(rincian.ntb_sebelum)}{rincian.target_ntb !== null ? ` → target ${formatNilai(rincian.target_ntb)}` : ""}</div>}
          {rincian.target_output !== null && <div className="text-xs text-slate-600">Output tanpa penyesuaian ini: {formatNilai(rincian.output_sebelum)} → target {formatNilai(rincian.target_output)}</div>}
          <div className="text-xs text-slate-500">Dihitung dari pratinjau (draf + diajukan + disetujui).</div>
        </div>
      )}
      {galat && <div className="mt-3"><Pesan jenis="galat">{galat}</Pesan></div>}
      <div className="mt-4 flex justify-end gap-2">
        <Tombol onClick={tutup}>Batal</Tombol>
        <Tombol disabled={sibuk || !teks} onClick={() => jalankan(false)}>Hitung</Tombol>
        <Tombol varian="utama" disabled={sibuk || !teks || (perluAlasan && alasan.trim().length < 10)} onClick={() => jalankan(true)}>Simpan sebagai draf</Tombol>
      </div>
    </Dialog>
  );
}
