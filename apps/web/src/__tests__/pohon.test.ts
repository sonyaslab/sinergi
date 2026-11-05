import { describe, expect, it } from "vitest";
import { barisTerlihat, calonInduk, geser, pindahKe, saudara, type Simpul } from "../lib/pohon";

// Potongan pohon TD2025: A > A.1 > (A.1.a, A.1.b), A.2 ; B (kategori) > B.1 ; kelompok TUV ; PDRB
const s = (id: number, induk: number | null, urutan: number, level: number, jenis: string, aktif = true): Simpul & { kode: string } =>
  ({ id, induk_id: induk, urutan, level, jenis, aktif, kode: String(id) });
const POHON = [
  s(1, null, 1, 1, "kategori"), s(2, 1, 2, 2, "sub"), s(3, 2, 3, 3, "daun"), s(4, 2, 4, 3, "daun", false), s(5, 1, 5, 2, "daun"),
  s(6, null, 6, 1, "kategori"), s(7, 6, 7, 2, "daun"), s(8, null, 8, 1, "kelompok"), s(9, null, 9, 0, "pdrb"),
];

describe("pohon lapus", () => {
  it("saudara urut", () => {
    expect(saudara(POHON, 1).map((x) => x.id)).toEqual([2, 5]);
    expect(saudara(POHON, null).map((x) => x.id)).toEqual([1, 6, 8, 9]);
  });
  it("geser naik/turun dan batas ujung", () => {
    expect(geser([1, 6, 8, 9], 6, -1)).toEqual([6, 1, 8, 9]);
    expect(geser([1, 6, 8, 9], 1, -1)).toBeNull();
    expect(geser([1, 6, 8, 9], 9, 1)).toBeNull();
  });
  it("seret-lepas: turun = sesudah target, naik = sebelum target", () => {
    expect(pindahKe([1, 6, 8, 9], 1, 8)).toEqual([6, 8, 1, 9]);
    expect(pindahKe([1, 6, 8, 9], 9, 6)).toEqual([1, 9, 6, 8]);
    expect(pindahKe([1, 6], 1, 1)).toBeNull();
  });
  it("lipat kategori menyembunyikan seluruh turunannya", () => {
    expect(barisTerlihat(POHON, { terlipat: new Set([1]) }).map((x) => x.id)).toEqual([1, 6, 7, 8, 9]);
    expect(barisTerlihat(POHON, { terlipat: new Set([2]) }).map((x) => x.id)).toEqual([1, 2, 5, 6, 7, 8, 9]);
  });
  it("kelompok dan nonaktif dapat disembunyikan", () => {
    expect(barisTerlihat(POHON, { tampilKelompok: false, hanyaAktif: true }).map((x) => x.id)).toEqual([1, 2, 3, 5, 6, 7, 9]);
  });
  it("calon induk: kategori/sub aktif, tanpa diri sendiri dan turunannya", () => {
    expect(calonInduk(POHON).map((x) => x.id)).toEqual([1, 2, 6]);
    expect(calonInduk(POHON, 1).map((x) => x.id)).toEqual([6]);
  });
});
