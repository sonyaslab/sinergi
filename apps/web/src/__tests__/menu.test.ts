import { describe, expect, it } from "vitest";
import { MENU, menuUntuk } from "../menu";

const label = (izin: string[]) => menuUntuk(izin).map((m) => m.label);

describe("menu samping sesuai izin", () => {
  it("operator: data dasar, tanpa master/pengguna/audit", () => {
    const l = label(["data_dasar.isi", "data_dasar.impor", "item.tambah", "biaya_antara.isi", "penyesuaian.usul",
      "lk.ajukan", "tabel_pokok.lihat", "dashboard.lihat"]);
    expect(l).toContain("Data Dasar");
    expect(l).toContain("Biaya Antara");
    expect(l).not.toContain("Master Data");
    expect(l).not.toContain("Pengguna & Hak Akses");
    expect(l).not.toContain("Kompilasi & Simulasi");
  });
  it("auditor: hanya baca", () => {
    expect(label(["tabel_pokok.lihat", "dashboard.lihat", "audit.lihat"])).toEqual([
      "Beranda", "Tabel Pokok", "Dashboard Pimpinan", "Jejak Audit",
    ]);
  });
  it("tanpa izin: hanya beranda", () => {
    expect(label([])).toEqual(["Beranda"]);
  });
  it("admin dengan semua izin melihat semua menu", () => {
    const semua = Array.from(new Set(MENU.flatMap((m) => m.izin)));
    expect(menuUntuk(semua)).toHaveLength(MENU.length);
  });
});
