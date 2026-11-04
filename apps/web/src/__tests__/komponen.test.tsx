import { describe, expect, it } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { PemilihTahunDasar } from "../components/PemilihTahunDasar";
import { PenyediaTahunDasar } from "../konteks/TahunDasar";
import { Login } from "../pages/Login";
import { Bungkus, tiruFetch } from "./bantu";

const TD = [
  { id: 1, kode: "TD2010", tahun_dasar: 2010, status: "produksi", klasifikasi: "KBLI2020", tahun_awal_seri: 2010, tahun_baseline_eks: 2024, keterangan: null },
  { id: 2, kode: "TD2025", tahun_dasar: 2025, status: "paralel", klasifikasi: "KBLI2025", tahun_awal_seri: 2019, tahun_baseline_eks: 2025, keterangan: null },
];

describe("pemilih tahun dasar di header", () => {
  it("bawaan = urutan pertama dari master, pilihan disimpan", async () => {
    tiruFetch({ "GET /api/tahun-dasar": () => ({ isi: TD }) });
    render(<Bungkus><PenyediaTahunDasar><PemilihTahunDasar /></PenyediaTahunDasar></Bungkus>);
    const sel = (await screen.findByLabelText("Pilih tahun dasar")) as HTMLSelectElement;
    await waitFor(() => expect(sel.value).toBe("TD2010"));
    await userEvent.selectOptions(sel, "TD2025");
    expect(sel.value).toBe("TD2025");
    expect(localStorage.getItem("sinergi_td")).toBe("TD2025");
  });
});

describe("halaman login", () => {
  it("menampilkan branding dan pesan galat", async () => {
    document.cookie = "sinergi_csrf=t.s; path=/";
    tiruFetch({ "POST /api/auth/login": () => ({ status: 401, isi: { kode: "LOGIN_GAGAL", pesan: "Nama pengguna atau sandi salah." } }) });
    render(<Bungkus><Login /></Bungkus>);
    expect(screen.getByText("SINERGI")).toBeInTheDocument();
    expect(screen.getByText("Sistem Neraca Ekonomi Regional Terintegrasi")).toBeInTheDocument();
    expect(screen.getByText("BPS Provinsi Kalimantan Utara")).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText("Nama pengguna"), "op.a");
    await userEvent.type(screen.getByLabelText("Sandi"), "salah");
    await userEvent.click(screen.getByRole("button", { name: "Masuk" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Nama pengguna atau sandi salah.");
  });

  it("pendaftaran TOTP menampilkan QR lalu meminta kode", async () => {
    document.cookie = "sinergi_csrf=t.s; path=/";
    tiruFetch({
      "POST /api/auth/login": () => ({ isi: { tahap: "daftar_totp", qr_svg: "data:image/svg+xml;base64,AA==", rahasia: "ABCDEF" } }),
    });
    render(<Bungkus><Login /></Bungkus>);
    await userEvent.type(screen.getByLabelText("Nama pengguna"), "op.a");
    await userEvent.type(screen.getByLabelText("Sandi"), "Sandi-Panjang-1");
    await userEvent.click(screen.getByRole("button", { name: "Masuk" }));
    expect(await screen.findByAltText("Kode QR pendaftaran autentikator")).toBeInTheDocument();
    expect(screen.getByText("ABCDEF")).toBeInTheDocument();
    expect(screen.getByLabelText("Kode verifikasi")).toBeInTheDocument();
  });
});
