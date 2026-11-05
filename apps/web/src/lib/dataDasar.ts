// Susunan grid Data Dasar (fungsi murni): baris = item x seri, kolom = triwulan dikelompokkan per tahun.

export interface Periode { urut: number; label: string; ubah: boolean }
export interface TautanSeri {
  sumber: "SERI_REFERENSI" | "HASIL_LAPUS" | "RUMUS";
  rumus: string | null;
  seri_ref: string | null;
  seri_id: number | null;
  lapus_sumber_ids: number[];
  lapus_sumber: string[];
  besaran: string | null;
  faktor: number;
  teks: string;
}
export interface SeriGrid {
  kode: string;
  satuan: string | null;
  label: string | null;
  catatan: string | null;
  tautan: TautanSeri | null;
  jangkar: { kode: string; nilai: number | null; alasan: string | null } | null;
  nilai: Record<string, number>;
  tidak_tersedia: number[];
  nilai_turunan: Record<string, number>;
}
export interface ItemGrid {
  id: number;
  lapus_id: number;
  kode_lapus: string;
  metode: "REV" | "EKS" | "DEF" | "PDK";
  nomor: number;
  nama: string;
  status: "aktif" | "nonaktif";
  jenis_indeks: "IP" | "IB" | null;
  satuan_kode: string | null;
  sumber: string | null;
  katalog_id: number | null;
  item_asal_id: number | null;
  mulai: number | null;
  selesai: number | null;
  boleh_tulis: boolean;
  kontribusi: Record<string, [number, number]>;
  seri: SeriGrid[];
}
export interface Temuan {
  kode: string;
  tingkat: "info" | "peringatan" | "blokir_ajukan" | "blokir_kunci";
  lapus_id: number;
  item_id: number | null;
  jenis_seri: string | null;
  periode: number | null;
  pesan: string;
  kunci: string;
  dikonfirmasi: boolean;
  alasan_konfirmasi: string | null;
}
export interface DataGrid {
  putaran: { id: number; status: string; awal: number; akhir: number; td_kode: string; nama: string };
  periode: Periode[];
  lapus: { id: number; kode: string; nama: string; jenis: string; boleh_tulis: boolean }[];
  item: ItemGrid[];
  validasi: Temuan[];
  antrean: { berjalan: number; terakhir: { status: string; pesan: string | null } | null };
}

export type JenisBaris = "isian" | "rumus" | "taut";
export interface BarisGrid {
  id: string; // "<item>:<seri>"
  item: ItemGrid;
  seri: SeriGrid;
  pertama: boolean; // baris pertama item (tampilkan nama, nomor, kontribusi)
  ganjil: boolean; // selang-seling warna per item
  jenis: JenisBaris;
  nilai: Record<string, number | null>; // urut -> nilai tampil (isian: tersimpan; tautan/rumus: turunan)
}

export const KOLOM_PERIODE = "p_";

export function jenisBaris(s: SeriGrid): JenisBaris {
  if (!s.tautan) return "isian";
  return s.tautan.sumber === "RUMUS" && !s.tautan.rumus?.startsWith("MARGIN") ? "rumus" : "taut";
}

export function susunBaris(item: ItemGrid[], hanyaAktifDi: number | null = null): BarisGrid[] {
  const out: BarisGrid[] = [];
  let ke = 0;
  for (const it of item) {
    if (hanyaAktifDi !== null && !aktifDi(it, hanyaAktifDi)) continue;
    it.seri.forEach((s, j) => {
      const jenis = jenisBaris(s);
      const sumber = jenis === "isian" ? s.nilai : s.nilai_turunan;
      out.push({ id: `${it.id}:${s.kode}`, item: it, seri: s, pertama: j === 0, ganjil: ke % 2 === 1, jenis,
        nilai: Object.fromEntries(Object.entries(sumber).map(([u, x]) => [u, x])) });
    });
    ke += 1;
  }
  return out;
}

/** Item berlaku dan aktif pada triwulan `u` (filter "aktif di triwulan ini"). */
export function aktifDi(it: Pick<ItemGrid, "status" | "mulai" | "selesai">, u: number): boolean {
  return it.status === "aktif" && (it.mulai === null || u >= it.mulai) && (it.selesai === null || u <= it.selesai);
}

export interface GrupTahun { tahun: number; periode: Periode[]; terbuka: boolean }

/** Kelompok kolom per tahun; tahun lama (sebelum dua tahun terakhir) terlipat secara bawaan. */
export function grupTahun(periode: Periode[]): GrupTahun[] {
  const per = new Map<number, Periode[]>();
  for (const p of periode) {
    const y = Math.floor(p.urut / 4);
    per.set(y, [...(per.get(y) ?? []), p]);
  }
  const tahun = [...per.keys()].sort((a, b) => a - b);
  const akhir = tahun[tahun.length - 1] ?? 0;
  return tahun.map((y) => ({ tahun: y, periode: per.get(y) ?? [], terbuka: y >= akhir - 1 }));
}

export function bolehUbahSel(b: BarisGrid, urut: number, periode: Map<number, Periode>, terkunci: boolean): boolean {
  return !terkunci && b.item.boleh_tulis && b.jenis === "isian" && (periode.get(urut)?.ubah ?? false);
}

const PERINGKAT: Record<Temuan["tingkat"], number> = { info: 1, peringatan: 2, blokir_kunci: 3, blokir_ajukan: 4 };

export interface IndeksTemuan {
  sel: Map<string, Temuan[]>; // "<item>|<seri>|<urut>"
  baris: Map<string, Temuan[]>; // "<item>|<seri>" (tanpa periode)
  item: Map<number, Temuan[]>; // temuan tingkat item (tanpa seri)
  lapus: Temuan[]; // temuan tingkat lapus
}

export function indeksTemuan(ts: Temuan[]): IndeksTemuan {
  const ix: IndeksTemuan = { sel: new Map(), baris: new Map(), item: new Map(), lapus: [] };
  const tambah = <K,>(m: Map<K, Temuan[]>, k: K, t: Temuan) => m.set(k, [...(m.get(k) ?? []), t]);
  for (const t of ts) {
    if (t.item_id === null) ix.lapus.push(t);
    else if (t.jenis_seri && t.periode !== null) tambah(ix.sel, `${t.item_id}|${t.jenis_seri}|${t.periode}`, t);
    else if (t.jenis_seri) tambah(ix.baris, `${t.item_id}|${t.jenis_seri}`, t);
    else tambah(ix.item, t.item_id, t);
  }
  return ix;
}

/** Tingkat terberat yang belum dikonfirmasi (untuk warna ikon). */
export function terberat(ts: Temuan[] | undefined): Temuan["tingkat"] | null {
  let hasil: Temuan["tingkat"] | null = null;
  for (const t of ts ?? []) {
    if (t.dikonfirmasi) continue;
    if (hasil === null || PERINGKAT[t.tingkat] > PERINGKAT[hasil]) hasil = t.tingkat;
  }
  return hasil;
}

export const LABEL_TINGKAT: Record<Temuan["tingkat"], string> = {
  info: "Info",
  peringatan: "Peringatan",
  blokir_ajukan: "Blokir ajukan",
  blokir_kunci: "Blokir kunci",
};

export function labelPeriode(u: number): string {
  return `Q${(u % 4) + 1}-${Math.floor(u / 4)}`;
}
