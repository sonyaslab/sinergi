import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ImporEkspor, type Pratinjau } from "../pages/data-dasar/ImporEkspor";
import type { Putaran } from "../pages/DataDasar";
import { tiruFetch } from "./bantu";

const PUT: Putaran = { id: 7, tahun_dasar_id: 2, tahun_dasar: "TD2025", nama: "Put 0", jenis: "BACKCAST", status: "terbuka",
  tahun: 2026, triwulan: 2, awal: 8076, akhir: 8105, label_awal: "Q1-2019", label_akhir: "Q2-2026" };

function pratinjau(o: Partial<Pratinjau> = {}): Pratinjau {
  return { impor_id: 11, jenis: "templat_xlsx", nama_berkas: "t.xlsx", dapat_diterapkan: true,
    ringkasan: { item_baru: 2, sel_baru: 5, galat: 0 }, item_baru: [], sel: [], sel_terpotong: false, tautan: [],
    seri_referensi_baru: [], penyesuaian: [], pesan: [], jumlah_pesan: 0, ...o };
}

function pasang(profilIzin: string[]) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  qc.setQueryData(["saya"], { izin: profilIzin });
  render(<QueryClientProvider client={qc}><ImporEkspor putaran={PUT} wilayah="6500" /></QueryClientProvider>);
}

describe("Impor templat: pratinjau -> terapkan", () => {
  it("menampilkan ringkasan, mengirim berkas mentah, lalu menerapkan dengan berkas yang sama", async () => {
    document.cookie = "sinergi_csrf=abc";
    const f = tiruFetch({
      "POST /api/impor/templat?putaran_id=7&nama=t.xlsx&kosongkan=false&setujui_penyesuaian=false": () => ({ isi: pratinjau() }),
      "POST /api/impor/11/terapkan": () => ({ isi: { pesan: "Impor diterapkan." } }),
    });
    pasang(["data_dasar.impor"]);
    const berkas = new File([new Uint8Array([80, 75, 1])], "t.xlsx");
    await userEvent.upload(screen.getByLabelText("Berkas impor"), berkas);
    expect(screen.queryByLabelText(/Kosongkan sel/)).not.toBeInTheDocument(); // khusus admin
    await userEvent.click(screen.getByRole("button", { name: "Pratinjau" }));
    expect(await screen.findByText("Item baru: 2")).toBeInTheDocument();
    expect(screen.getByText("Sel baru: 5")).toBeInTheDocument();
    const [, init] = f.mock.calls[0];
    expect((init as RequestInit).body).toBe(berkas);
    expect((init as RequestInit).headers).toMatchObject({ "X-CSRF-Token": "abc", "Content-Type": "application/octet-stream" });
    await userEvent.click(screen.getByRole("button", { name: "Terapkan ke putaran" }));
    expect(await screen.findByText("Impor diterapkan.")).toBeInTheDocument();
    expect((f.mock.calls[1][1] as RequestInit).body).toBe(berkas);
  });

  it("galat format memblokir penerapan dan pesan ditampilkan per sheet/baris", async () => {
    document.cookie = "sinergi_csrf=abc";
    tiruFetch({
      "POST /api/impor/templat?putaran_id=7&nama=t.xlsx&kosongkan=false&setujui_penyesuaian=false": () => ({ isi: pratinjau({
        dapat_diterapkan: false, ringkasan: { galat: 1 },
        pesan: [{ tingkat: "galat", teks: "Isi bukan angka (kosongkan bila tidak tersedia).", sheet: "A", baris: 9, kolom: "K" }] }) }),
    });
    pasang(["data_dasar.impor", "data.tulis_semua", "penyesuaian.putus"]);
    expect(screen.getByLabelText(/Kosongkan sel/)).toBeInTheDocument();
    await userEvent.upload(screen.getByLabelText("Berkas impor"), new File(["x"], "t.xlsx"));
    await userEvent.click(screen.getByRole("button", { name: "Pratinjau" }));
    await waitFor(() => expect(screen.getByText(/A · baris 9 · K: Isi bukan angka/)).toBeInTheDocument());
    expect(screen.getByRole("button", { name: "Terapkan ke putaran" })).toBeDisabled();
  });
});
