// Fungsi murni layar F4 (putaran, status lapus, LK Hitung, kompilasi): status, aksi yang tersedia, laju, implisit.

export type StatusLapus = "belum" | "draf" | "diajukan" | "disetujui" | "dikembalikan" | "nihil" | "dikecualikan";
export type Warna = "abu" | "hijau" | "merah" | "kuning" | "biru";

export const LABEL_STATUS: Record<StatusLapus, string> = {
  belum: "Belum",
  draf: "Draf",
  diajukan: "Diajukan",
  disetujui: "Disetujui",
  dikembalikan: "Dikembalikan",
  nihil: "NIHIL",
  dikecualikan: "Dikecualikan",
};

export const WARNA_STATUS: Record<StatusLapus, Warna> = {
  belum: "abu",
  draf: "kuning",
  diajukan: "biru",
  disetujui: "hijau",
  dikembalikan: "merah",
  nihil: "abu",
  dikecualikan: "abu",
};

/** Kelas sel heatmap Beranda (warna latar per status). */
export const SEL_STATUS: Record<StatusLapus, string> = {
  belum: "bg-slate-100 text-slate-500",
  draf: "bg-amber-200 text-amber-900",
  diajukan: "bg-sky-300 text-sky-900",
  disetujui: "bg-green-400 text-green-950",
  dikembalikan: "bg-red-300 text-red-900",
  nihil: "bg-slate-300 text-slate-700",
  dikecualikan: "bg-slate-300 text-slate-700",
};

export type AksiStatus = "ajukan" | "setujui" | "kembalikan" | "nihil" | "kecualikan" | "batal";

export interface BarisStatus {
  id: number;
  kode: string;
  nama: string;
  jenis: string;
  status: StatusLapus;
  jumlah_item: number;
  boleh_tulis: boolean;
}

const TERBUKA_UNTUK_OPERATOR: StatusLapus[] = ["belum", "draf", "dikembalikan"];

/** Tombol aksi status yang tersedia untuk pengguna (server tetap memeriksa izin dan validasi). */
export function aksiTersedia(b: BarisStatus, izin: ReadonlySet<string>, terkunci: boolean): AksiStatus[] {
  if (terkunci) return [];
  const out: AksiStatus[] = [];
  const operator = izin.has("lk.ajukan") && b.boleh_tulis;
  const awal = TERBUKA_UNTUK_OPERATOR.includes(b.status);
  if (operator && awal && b.jumlah_item > 0) out.push("ajukan");
  if (izin.has("lk.setujui") && b.status === "diajukan") out.push("setujui");
  if (izin.has("lk.setujui") && (b.status === "diajukan" || b.status === "disetujui")) out.push("kembalikan");
  if ((operator || izin.has("lk.setujui")) && b.jenis === "daun" && b.jumlah_item === 0 && awal) out.push("nihil");
  if (izin.has("putaran.kelola") && (b.jenis === "top" || b.jenis === "sop") && b.jumlah_item === 0 && awal)
    out.push("kecualikan");
  if ((b.status === "nihil" && (operator || izin.has("lk.setujui"))) || (b.status === "dikecualikan" && izin.has("putaran.kelola")))
    out.push("batal");
  return out;
}

export const LABEL_AKSI: Record<AksiStatus, string> = {
  ajukan: "Ajukan",
  setujui: "Setujui",
  kembalikan: "Kembalikan",
  nihil: "Tandai NIHIL",
  kecualikan: "Kecualikan (V14)",
  batal: "Batalkan status",
};

/** Aksi yang wajib catatan (min. 10 karakter). */
export const AKSI_CATATAN: ReadonlySet<AksiStatus> = new Set(["kembalikan", "nihil", "kecualikan"]);

// ---- angka
export type Seri = Record<string, number[]>; // urut -> [ ... ] (indeks menurut konteks)

/** Laju (persen) X(t) terhadap X(t − lag); null bila pembanding tidak ada atau 0. */
export function laju(seri: Seri, u: number, i: number, lag = 4): number | null {
  const a = seri[String(u)]?.[i];
  const b = seri[String(u - lag)]?.[i];
  if (a === undefined || b === undefined || b === 0) return null;
  return (a / b) * 100 - 100;
}

/** Indeks implisit = ADHB ÷ ADHK × 100; null bila ADHK 0/kosong. */
export function implisit(cp: number | undefined, k: number | undefined): number | null {
  if (cp === undefined || k === undefined || k === 0) return null;
  return (cp / k) * 100;
}

const FMT2 = new Intl.NumberFormat("id-ID", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const FMT_NILAI = new Intl.NumberFormat("id-ID", { maximumFractionDigits: 2 });

export function formatNilai(x: number | null | undefined): string {
  return x === null || x === undefined ? "" : FMT_NILAI.format(x);
}

export function formatPersen(x: number | null | undefined): string {
  return x === null || x === undefined ? "" : FMT2.format(x);
}

/** urut periode (tahun × 4 + triwulan − 1). */
export function urut(tahun: number, triwulan: number): number {
  return tahun * 4 + triwulan - 1;
}

export const LABEL_MODE: Record<string, string> = {
  nilai: "Nilai penyesuaian",
  target_ntb: "Target NTB",
  target_output: "Target output",
  target_laju: "Target laju y-on-y (%)",
  target_implisit: "Target implisit",
};

export const LABEL_STATUS_ADJ: Record<string, { teks: string; warna: Warna }> = {
  draf: { teks: "Draf", warna: "kuning" },
  diajukan: { teks: "Diajukan", warna: "biru" },
  disetujui: { teks: "Disetujui", warna: "hijau" },
  ditolak: { teks: "Ditolak", warna: "merah" },
};
