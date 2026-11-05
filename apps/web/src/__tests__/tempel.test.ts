import { describe, expect, it } from "vitest";
import { petakanTempel, uraiAngka, uraiTempel } from "../lib/tempel";
import { aktifDi, grupTahun, indeksTemuan, susunBaris, terberat, type ItemGrid, type Temuan } from "../lib/dataDasar";

describe("uraiAngka (format Excel Indonesia/Inggris)", () => {
  it.each([
    ["0,25", 0.25],
    ["0.25", 0.25],
    ["1.234.567", 1234567],
    ["1,234,567", 1234567],
    ["1.234,5", 1234.5],
    ["1,234.5", 1234.5],
    [" 12 ", 12],
    ["-3,5", -3.5],
    ["1 234,5", 1234.5],
    ["1e3", 1000],
  ])("%s -> %s", (t, n) => {
    expect(uraiAngka(t)).toEqual({ jenis: "angka", nilai: n });
  });
  it("kosong, tidak tersedia, dan teks", () => {
    expect(uraiAngka("")).toEqual({ jenis: "kosong" });
    expect(uraiAngka("-")).toEqual({ jenis: "tidak_tersedia" });
    expect(uraiAngka("TT")).toEqual({ jenis: "tidak_tersedia" });
    expect(uraiAngka("dua")).toEqual({ jenis: "galat", teks: "dua" });
    expect(uraiAngka("25%")).toEqual({ jenis: "galat", teks: "25%" });
  });
});

describe("tempel dari Excel", () => {
  it("TSV -> matriks, buang baris kosong terakhir", () => {
    expect(uraiTempel("1\t2\r\n3\t4\r\n")).toEqual([["1", "2"], ["3", "4"]]);
  });
  it("memetakan mulai sel fokus, melewati sel terkunci dan di luar grid", () => {
    const baris = ["a", "b", "c"];
    const kolom = ["p1", "p2", "p3"];
    const h = petakanTempel([["1", "2"], ["x", "-"], ["5", "6"], ["7", "8"]], 1, 1, {
      baris, kolom, bolehUbah: (b, k) => !(b === "b" && k === "p2"),
    });
    expect(h.ubah.map((u) => [u.baris, u.kolom, u.isi.jenis])).toEqual([
      ["b", "p3", "angka"],
      ["c", "p3", "tidak_tersedia"],
    ]);
    expect(h.dilewati).toBe(1);
    expect(h.galat).toEqual(["x"]);
  });
});

const item = (id: number, over: Partial<ItemGrid> = {}): ItemGrid => ({
  id, lapus_id: 1, kode_lapus: "A.1.a", metode: "REV", nomor: id, nama: `Item ${id}`, status: "aktif",
  jenis_indeks: null, satuan_kode: null, sumber: null, katalog_id: null, item_asal_id: null, mulai: null, selesai: null,
  boleh_tulis: true, kontribusi: {},
  seri: [
    { kode: "KUANTUM", satuan: "ton", label: null, catatan: null, tautan: null, jangkar: null, nilai: { "8100": 5 },
      tidak_tersedia: [], nilai_turunan: {} },
    { kode: "HARGA", satuan: null, label: null, catatan: null, jangkar: { kode: "H_TD", nilai: null, alasan: null },
      tautan: { sumber: "RUMUS", rumus: "JANGKAR_X_IH_100", seri_ref: null, seri_id: null, lapus_sumber_ids: [],
        lapus_sumber: [], besaran: null, faktor: 1, teks: "RUMUS: ..." },
      nilai: { "8100": 999 }, tidak_tersedia: [], nilai_turunan: { "8100": 7 } },
  ],
  ...over,
});

describe("susunan grid", () => {
  it("baris item x seri: isian memakai nilai tersimpan, rumus memakai nilai turunan", () => {
    const b = susunBaris([item(1), item(2)]);
    expect(b.map((x) => [x.id, x.jenis, x.pertama, x.ganjil])).toEqual([
      ["1:KUANTUM", "isian", true, false], ["1:HARGA", "rumus", false, false],
      ["2:KUANTUM", "isian", true, true], ["2:HARGA", "rumus", false, true],
    ]);
    expect(b[1].nilai["8100"]).toBe(7);
  });
  it("filter aktif di triwulan dan masa berlaku", () => {
    expect(aktifDi(item(1, { mulai: 8100 }), 8099)).toBe(false);
    expect(aktifDi(item(1, { status: "nonaktif" }), 8100)).toBe(false);
    expect(susunBaris([item(1, { selesai: 8090 }), item(2)], 8100).map((x) => x.item.id)).toEqual([2, 2]);
  });
  it("tahun lama terlipat", () => {
    const per = [8076, 8077, 8100, 8104, 8105].map((u) => ({ urut: u, label: "", ubah: true }));
    expect(grupTahun(per).map((g) => [g.tahun, g.periode.length, g.terbuka])).toEqual([
      [2019, 2, false], [2025, 1, true], [2026, 2, true]]);
  });
  it("indeks temuan per sel/baris/item/lapus dan tingkat terberat", () => {
    const t = (o: Partial<Temuan>): Temuan => ({ kode: "V01", tingkat: "peringatan", lapus_id: 1, item_id: 1,
      jenis_seri: null, periode: null, pesan: "", kunci: "", dikonfirmasi: false, alasan_konfirmasi: null, ...o });
    const ix = indeksTemuan([t({ jenis_seri: "HARGA", periode: 8100 }), t({ jenis_seri: "RKA" }), t({}),
      t({ item_id: null, tingkat: "info" }), t({ tingkat: "blokir_ajukan", dikonfirmasi: true })]);
    expect(ix.sel.get("1|HARGA|8100")?.length).toBe(1);
    expect(ix.baris.get("1|RKA")?.length).toBe(1);
    expect(ix.item.get(1)?.length).toBe(2);
    expect(ix.lapus.length).toBe(1);
    expect(terberat(ix.item.get(1))).toBe("peringatan"); // blokir sudah dikonfirmasi
  });
});
