// Tempel dari Excel ke grid Data Dasar (fungsi murni, diuji Vitest).
// Excel menyalin sel sebagai teks bertab (TSV). Angka boleh berformat Indonesia (1.234,56) atau Inggris (1,234.56).
// Aturan: satu jenis pemisah saja = pemisah desimal, kecuali muncul berkali-kali (pemisah ribuan).
// Sel kosong = hapus nilai (belum diisi); "-" atau "tt" = tidak tersedia (kosong yang disengaja, bukan nol).

export type IsiSel = { jenis: "angka"; nilai: number } | { jenis: "kosong" } | { jenis: "tidak_tersedia" } | { jenis: "galat"; teks: string };

const TANDA_TIDAK_TERSEDIA = new Set(["-", "–", "tt", "t/t", "n/a", "na"]);

export function uraiAngka(teks: string): IsiSel {
  const t = teks.replace(/[\s\u00a0]/g, "");
  if (t === "") return { jenis: "kosong" };
  if (TANDA_TIDAK_TERSEDIA.has(t.toLowerCase())) return { jenis: "tidak_tersedia" };
  if (!/^[-+]?[0-9.,]+([eE][-+]?[0-9]+)?$/.test(t) || !/[0-9]/.test(t)) return { jenis: "galat", teks: teks.trim() };
  let s = t;
  const titik = (s.match(/\./g) ?? []).length;
  const koma = (s.match(/,/g) ?? []).length;
  if (titik > 0 && koma > 0) {
    // pemisah terakhir = desimal
    if (s.lastIndexOf(",") > s.lastIndexOf(".")) s = s.replace(/\./g, "").replace(",", ".");
    else s = s.replace(/,/g, "");
  } else if (koma > 1) s = s.replace(/,/g, "");
  else if (titik > 1) s = s.replace(/\./g, "");
  else if (koma === 1) s = s.replace(",", ".");
  const n = Number(s);
  return Number.isFinite(n) ? { jenis: "angka", nilai: n } : { jenis: "galat", teks: teks.trim() };
}

/** Teks papan klip (TSV) -> matriks sel. Baris kosong terakhir (akhir salinan Excel) dibuang. */
export function uraiTempel(teks: string): string[][] {
  const baris = teks.replace(/\r\n?/g, "\n").split("\n");
  if (baris.length > 1 && baris[baris.length - 1] === "") baris.pop();
  return baris.map((b) => b.split("\t"));
}

export interface TujuanTempel<B> {
  baris: B[]; // baris tampil (urut layar)
  kolom: string[]; // id kolom tampil (urut layar)
  bolehUbah: (baris: B, kolom: string) => boolean;
}

export interface HasilTempel<B> {
  ubah: { baris: B; kolom: string; isi: IsiSel }[];
  dilewati: number; // sel tujuan yang tidak dapat diubah (rumus/tautan/di luar cakupan)
  galat: string[];
}

/** Petakan matriks tempel mulai sel fokus (baris i, kolom j) ke sel grid. Sel di luar grid diabaikan. */
export function petakanTempel<B>(m: string[][], i0: number, j0: number, t: TujuanTempel<B>): HasilTempel<B> {
  const out: HasilTempel<B> = { ubah: [], dilewati: 0, galat: [] };
  m.forEach((isi, di) => {
    const b = t.baris[i0 + di];
    if (b === undefined) return;
    isi.forEach((teks, dj) => {
      const k = t.kolom[j0 + dj];
      if (k === undefined) return;
      if (!t.bolehUbah(b, k)) {
        out.dilewati += 1;
        return;
      }
      const sel = uraiAngka(teks);
      if (sel.jenis === "galat") out.galat.push(sel.teks);
      else out.ubah.push({ baris: b, kolom: k, isi: sel });
    });
  });
  return out;
}

const FMT = new Intl.NumberFormat("id-ID", { maximumFractionDigits: 6 });
export function formatAngka(x: number | null | undefined): string {
  return x === null || x === undefined ? "" : FMT.format(x);
}
