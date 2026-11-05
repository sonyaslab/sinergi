// Fungsi murni pohon lapus (tanpa I/O): saudara, geser urutan, lipat per kategori, filter tampilan.
// Daftar lapus dari API sudah urut `urutan` = urutan baris tabel pokok (DFS).

export interface Simpul {
  id: number;
  induk_id: number | null;
  urutan: number;
  level: number;
  jenis: string;
  aktif: boolean;
}

export const JENIS_TOTAL = new Set(["ntb", "top", "sop", "topsop", "pdrb", "pdrb_nonmigas"]);
export const JENIS_INDUK = new Set(["kategori", "sub"]);

export function saudara<T extends Simpul>(daftar: T[], induk: number | null): T[] {
  return daftar.filter((x) => x.induk_id === induk).sort((a, b) => a.urutan - b.urutan);
}

export function punyaAnak(daftar: Simpul[], id: number): boolean {
  return daftar.some((x) => x.induk_id === id);
}

/** Geser `id` satu langkah di antara saudaranya. null bila sudah di ujung. */
export function geser(ids: number[], id: number, arah: -1 | 1): number[] | null {
  const i = ids.indexOf(id);
  const j = i + arah;
  if (i < 0 || j < 0 || j >= ids.length) return null;
  const hasil = [...ids];
  [hasil[i], hasil[j]] = [hasil[j], hasil[i]];
  return hasil;
}

/** Pindahkan `id` ke posisi `target` (seret-lepas): naik = sebelum target, turun = sesudah target. */
export function pindahKe(ids: number[], id: number, target: number): number[] | null {
  const dari = ids.indexOf(id);
  const ke = ids.indexOf(target);
  if (dari < 0 || ke < 0 || dari === ke) return null;
  const hasil = ids.filter((x) => x !== id);
  hasil.splice(ke, 0, id);
  return hasil;
}

/** Baris yang terlihat: turunan simpul terlipat disembunyikan; kelompok/nonaktif dapat disembunyikan. */
export function barisTerlihat<T extends Simpul>(
  daftar: T[],
  opsi: { terlipat?: Set<number>; tampilKelompok?: boolean; hanyaAktif?: boolean } = {},
): T[] {
  const { terlipat = new Set<number>(), tampilKelompok = true, hanyaAktif = false } = opsi;
  const hasil: T[] = [];
  let sembunyiDiBawah: number | null = null; // level simpul terlipat yang sedang aktif
  for (const x of [...daftar].sort((a, b) => a.urutan - b.urutan)) {
    if (sembunyiDiBawah !== null) {
      if (x.level > sembunyiDiBawah && x.induk_id !== null) continue;
      sembunyiDiBawah = null;
    }
    if (!tampilKelompok && x.jenis === "kelompok") continue;
    if (hanyaAktif && !x.aktif) continue;
    hasil.push(x);
    if (terlipat.has(x.id)) sembunyiDiBawah = x.level;
  }
  return hasil;
}

/** Calon induk: kategori/subkategori aktif, kecuali simpul itu sendiri dan turunannya. */
export function calonInduk<T extends Simpul>(daftar: T[], kecuali?: number): T[] {
  const keluar = new Set<number>();
  if (kecuali !== undefined) {
    keluar.add(kecuali);
    let tambah = true;
    while (tambah) {
      tambah = false;
      for (const x of daftar) {
        if (x.induk_id !== null && keluar.has(x.induk_id) && !keluar.has(x.id)) {
          keluar.add(x.id);
          tambah = true;
        }
      }
    }
  }
  return daftar.filter((x) => JENIS_INDUK.has(x.jenis) && x.aktif && !keluar.has(x.id));
}
