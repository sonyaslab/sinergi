import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";
import { api } from "../api/klien";
import { DialogPenyesuaian } from "../components/DialogPenyesuaian";
import { aksiTersedia, implisit, laju, type BarisStatus } from "../lib/putaran";
import { rasioKA } from "../pages/BiayaAntara";
import { tugasSaya } from "../pages/Beranda";
import type { Putaran } from "../pages/DataDasar";
import { nilaiTampilan } from "../pages/Kompilasi";
import { lapusBerdataDi } from "../pages/LkHitung";
import { StatusLapus } from "../pages/putaran/StatusLapus";
import type { Lapus } from "../api/tipe";
import { tiruFetch } from "./bantu";

const PUT: Putaran = { id: 7, tahun_dasar_id: 2, tahun_dasar: "TD2025", nama: "Put 0", jenis: "BACKCAST", status: "terbuka",
  tahun: 2026, triwulan: 1, awal: 8096, akhir: 8104, label_awal: "Q1-2024", label_akhir: "Q1-2026" };

function pasang(isi: ReactNode, izin: string[]) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  qc.setQueryData(["saya"], { izin });
  render(<QueryClientProvider client={qc}>{isi}</QueryClientProvider>);
}

const b = (o: Partial<BarisStatus>): BarisStatus => ({ id: 1, kode: "A.1.a", nama: "Padi", jenis: "daun", status: "draf",
  jumlah_item: 2, boleh_tulis: true, ...o });

describe("aturan tombol status lapus", () => {
  const op = new Set(["lk.ajukan"]);
  const sup = new Set(["lk.setujui"]);
  const adm = new Set(["lk.ajukan", "lk.setujui", "putaran.kelola"]);
  it("operator: ajukan lapus berisi yang ditugaskan; NIHIL hanya daun kosong", () => {
    expect(aksiTersedia(b({}), op, false)).toEqual(["ajukan"]);
    expect(aksiTersedia(b({ boleh_tulis: false }), op, false)).toEqual([]);
    expect(aksiTersedia(b({ jumlah_item: 0, status: "belum" }), op, false)).toEqual(["nihil"]);
    expect(aksiTersedia(b({ jenis: "top", jumlah_item: 0, status: "belum" }), op, false)).toEqual([]);
    expect(aksiTersedia(b({ status: "diajukan" }), op, false)).toEqual([]);
    expect(aksiTersedia(b({}), op, true)).toEqual([]); // putaran terkunci
  });
  it("supervisor: setujui/kembalikan; admin: kecualikan TOP/SOP kosong dan batalkan", () => {
    expect(aksiTersedia(b({ status: "diajukan" }), sup, false)).toEqual(["setujui", "kembalikan"]);
    expect(aksiTersedia(b({ status: "disetujui" }), sup, false)).toEqual(["kembalikan"]);
    expect(aksiTersedia(b({ jenis: "sop", jumlah_item: 0, status: "belum" }), adm, false)).toContain("kecualikan");
    expect(aksiTersedia(b({ jenis: "sop", jumlah_item: 0, status: "dikecualikan" }), adm, false)).toEqual(["batal"]);
    expect(aksiTersedia(b({ jenis: "sop", jumlah_item: 0, status: "dikecualikan" }), sup, false)).toEqual([]);
  });
});

describe("angka layar F4", () => {
  const s = { "8100": [110, 220], "8104": [121, 231], "8101": [0, 0] };
  it("laju y-on-y, implisit, kosong bila pembanding tidak ada atau nol", () => {
    expect(laju(s, 8104, 0)).toBeCloseTo(10);
    expect(laju(s, 8105, 0)).toBeNull();
    expect(laju(s, 8105, 1, 4)).toBeNull();
    expect(implisit(121, 110)).toBeCloseTo(110);
    expect(implisit(5, 0)).toBeNull();
    expect(nilaiTampilan(s, 8104, "implisit")).toBeCloseTo((121 / 231) * 100);
    expect(nilaiTampilan(s, 8104, "laju_k")).toBeCloseTo(5);
    expect(nilaiTampilan(s, 8099, "ntb_k")).toBeNull();
  });
  it("rasio KA = Σ rincian (atau total langsung) ÷ output, sama dengan kolom DB", () => {
    expect(rasioKA({ output: 1000, ba_bahan: 200, ba_jasa: 100 })).toBeCloseTo(0.3);
    expect(rasioKA({ output: 1000, ba_total_langsung: 450 })).toBeCloseTo(0.45);
    expect(rasioKA({ output: 0, ba_bahan: 1 })).toBeNull();
    expect(rasioKA({ output: 100 })).toBeNull();
  });
  it("lapus berdata di bawah kategori menurut urutan pohon; tugas saya per peran", () => {
    const L = (id: number, kode: string, jenis: string, induk: number | null, urutan: number) =>
      ({ id, kode, nama: kode, jenis, induk_id: induk, urutan, aktif: true }) as Lapus;
    const pohon = [L(1, "A", "kategori", null, 1), L(3, "A.1.b", "daun", 2, 4), L(2, "A.1", "sub", 1, 2), L(4, "A.1.a", "daun", 2, 3), L(5, "TOP", "top", null, 9)];
    expect(lapusBerdataDi(pohon, 1).map((l) => l.kode)).toEqual(["A.1.a", "A.1.b"]);
    const r = { putaran: { id: 1, nama: "Put", status: "terbuka" }, wilayah: [{ kode: "6500", nama: "Kaltara" }],
      lapus: [{ id: 4, kode: "A.1.a", nama: "", jenis: "daun" }, { id: 3, kode: "A.1.b", nama: "", jenis: "daun" }],
      sel: { "6500": { "4": { status: "dikembalikan" as const, item: 2 }, "3": { status: "diajukan" as const, item: 1 } } } };
    const penugasan = [{ tahun_dasar: "TD2025", wilayah_kode: "6500", lapus: "A.1.a", peran_tugas: "operator" }];
    expect(tugasSaya(r, { izin: ["lk.ajukan"], penugasan }, "TD2025")).toEqual([
      { kode: "A.1.a", wilayah: "6500", status: "dikembalikan", aksi: "perbaiki lalu ajukan" }]);
    expect(tugasSaya(r, { izin: ["lk.setujui"], penugasan: [] }, "TD2025").map((t) => t.kode)).toEqual(["A.1.b"]);
  });
});

describe("klien: cut-off", () => {
  it("ALASAN_CUTOFF -> minta alasan lalu ulangi dengan X-Alasan; batal -> galat", async () => {
    document.cookie = "sinergi_csrf=tok; path=/";
    let n = 0;
    const f = tiruFetch({
      "PUT /api/data-dasar/nilai": () => (n++ === 0 ? { status: 422, isi: { kode: "ALASAN_CUTOFF", pesan: "Lewat cut-off." } } : { isi: { pesan: "ok" } }),
    });
    const tanya = vi.spyOn(window, "prompt").mockReturnValueOnce("pendek").mockReturnValueOnce("koreksi sesudah cut-off");
    await expect(api("/api/data-dasar/nilai", { metode: "PUT", isi: {} })).resolves.toEqual({ pesan: "ok" });
    expect(tanya).toHaveBeenCalledTimes(2); // alasan < 10 karakter ditanya ulang
    expect(decodeURIComponent((f.mock.calls[1][1]!.headers as Record<string, string>)["X-Alasan"])).toBe("koreksi sesudah cut-off");
    n = 0;
    vi.spyOn(window, "prompt").mockReturnValueOnce(null);
    await expect(api("/api/data-dasar/nilai", { metode: "PUT", isi: {} })).rejects.toThrow("Lewat cut-off.");
  });
});

describe("layar status lapus", () => {
  const status = { putaran: { id: 7, status: "terbuka" }, lapus: [
    { id: 11, kode: "A.1.a", nama: "Padi", jenis: "daun", status: "draf", catatan: null, diperbarui_pada: null, diperbarui_oleh: null,
      jumlah_item: 2, penyesuaian: { draf: 1 }, blokir_ajukan: 1, boleh_tulis: true },
    { id: 12, kode: "A.1.b", nama: "Horti", jenis: "daun", status: "diajukan", catatan: null, diperbarui_pada: null, diperbarui_oleh: null,
      jumlah_item: 3, penyesuaian: { diajukan: 2 }, blokir_ajukan: 0, boleh_tulis: false },
  ] };

  it("ajukan diblokir validasi menampilkan rincian temuan", async () => {
    document.cookie = "sinergi_csrf=tok; path=/";
    tiruFetch({
      "GET /api/status?putaran_id=7&wilayah=6500": () => ({ isi: status }),
      "POST /api/status/11/ajukan": () => ({ status: 409, isi: { kode: "VALIDASI_BLOKIR", pesan: "Pengajuan diblokir 1 temuan validasi.",
        rincian: [{ kode: "V02", pesan: "RKA tahun dasar kosong." }] } }),
    });
    pasang(<StatusLapus putaran={PUT} wilayah="6500" />, ["lk.ajukan"]);
    const baris = (await screen.findByText("A.1.a")).closest("tr")!;
    expect(within(screen.getByText("A.1.b").closest("tr")!).queryByRole("button", { name: "Setujui" })).toBeNull();
    await userEvent.click(within(baris).getByRole("button", { name: "Ajukan" }));
    expect(await screen.findByText("V02: RKA tahun dasar kosong.")).toBeInTheDocument();
  });

  it("setujui dengan penyesuaian belum diputus -> konfirmasi -> kirim ulang dengan putus_penyesuaian", async () => {
    document.cookie = "sinergi_csrf=tok; path=/";
    const badan: unknown[] = [];
    tiruFetch({
      "GET /api/status?putaran_id=7&wilayah=6500": () => ({ isi: status }),
      "POST /api/status/12/setujui": (init) => {
        const x = JSON.parse(String(init?.body));
        badan.push(x);
        return x.putus_penyesuaian ? { isi: { pesan: "Lapus A.1.b disetujui." } }
          : { status: 409, isi: { kode: "PENYESUAIAN_BELUM_DIPUTUS", pesan: "Masih ada 2 penyesuaian yang belum diputus." } };
      },
    });
    vi.spyOn(window, "confirm").mockReturnValue(true);
    pasang(<StatusLapus putaran={PUT} wilayah="6500" />, ["lk.setujui", "penyesuaian.putus"]);
    const baris = (await screen.findByText("A.1.b")).closest("tr")!;
    await userEvent.click(within(baris).getByRole("button", { name: "Setujui" }));
    expect(await screen.findByText("Lapus A.1.b disetujui.")).toBeInTheDocument();
    expect(badan).toHaveLength(2);
    expect(badan[1]).toMatchObject({ putaran_id: 7, wilayah: "6500", putus_penyesuaian: "setujui" });
  });
});

describe("dialog penyesuaian", () => {
  const jenis = [
    { kode: "ADJ4_OUTPUT", tahap: "REKON", nama: "Benchmarking output", ubah_angka: true, wajib_alasan: true, mode: { CP: ["nilai", "target_output"], K: ["nilai", "target_output"] } },
    { kode: "ADJ4_NTB", tahap: "REKON", nama: "Benchmarking NTB", ubah_angka: true, wajib_alasan: true,
      mode: { CP: ["nilai", "target_ntb", "target_laju", "target_implisit"], K: ["nilai", "target_ntb", "target_laju"] } },
  ];
  it("cara isi mengikuti jenis/harga; Hitung menampilkan nilai; Simpan butuh alasan", async () => {
    document.cookie = "sinergi_csrf=tok; path=/";
    const f = tiruFetch({
      "GET /api/penyesuaian/jenis": () => ({ isi: jenis }),
      "POST /api/penyesuaian/hitung": () => ({ isi: { nilai: 12.5, target_ntb: 500, target_output: null, ntb_sebelum: 487.5, output_sebelum: 900, label_periode: "Q1-2026" } }),
      "POST /api/penyesuaian": () => ({ isi: { pesan: "Penyesuaian tersimpan sebagai draf.", nilai: 12.5 } }),
    });
    const selesai = vi.fn();
    pasang(<DialogPenyesuaian putaran={PUT} wilayah="6500" lapus={[{ id: 11, kode: "A.1.a" }]} tahapBoleh={["REKON"]} tutup={() => {}} selesai={selesai} />, []);
    const caraIsi = screen.getByLabelText("Cara isi");
    await waitFor(() => expect(within(caraIsi).getAllByRole("option").map((o) => o.textContent)).toEqual(["Nilai penyesuaian", "Target output"]));
    await userEvent.selectOptions(screen.getByLabelText("Jenis penyesuaian"), "ADJ4_NTB");
    expect(within(caraIsi).getAllByRole("option")).toHaveLength(3); // ADHK: tanpa target implisit
    await userEvent.selectOptions(screen.getByLabelText("Harga"), "CP");
    expect(within(caraIsi).getAllByRole("option")).toHaveLength(4);
    await userEvent.selectOptions(caraIsi, "target_ntb");
    await userEvent.type(screen.getByLabelText("Nilai atau target"), "500");
    await userEvent.click(screen.getByRole("button", { name: "Hitung" }));
    expect(await screen.findByLabelText("Hasil hitung penyesuaian")).toHaveTextContent("12,5");
    const simpan = screen.getByRole("button", { name: "Simpan sebagai draf" });
    expect(simpan).toBeDisabled();
    await userEvent.type(screen.getByLabelText("Alasan penyesuaian"), "benchmark ke data rilis");
    await userEvent.click(simpan);
    await waitFor(() => expect(selesai).toHaveBeenCalled());
    const isi = JSON.parse(String(f.mock.calls.at(-1)![1]!.body));
    expect(isi).toMatchObject({ putaran_id: 7, lapus_id: 11, tahap: "REKON", metode: null, jenis: "ADJ4_NTB", harga: "CP",
      periode: 8104, mode: "target_ntb", target: 500, alasan: "benchmark ke data rilis" });
  });
});
