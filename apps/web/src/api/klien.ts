// Klien API: cookie HttpOnly (sinergi_akses/refresh), CSRF double-submit (sinergi_csrf + X-CSRF-Token),
// alasan perubahan lewat header X-Alasan, refresh token otomatis satu kali (single-flight).

export class GalatApi extends Error {
  constructor(
    public status: number,
    public kode: string,
    pesan: string,
    public rincian?: unknown,
  ) {
    super(pesan);
    this.name = "GalatApi";
  }
}

export const COOKIE_CSRF = "sinergi_csrf";
const METODE_AMAN = new Set(["GET", "HEAD", "OPTIONS"]);
// Endpoint yang tidak memicu refresh otomatis saat 401.
const TANPA_REFRESH = ["/api/auth/login", "/api/auth/totp", "/api/auth/refresh", "/api/auth/logout", "/api/auth/csrf"];

export function bacaCookie(nama: string, sumber: string = document.cookie): string | null {
  for (const bagian of sumber.split(";")) {
    const [k, ...v] = bagian.trim().split("=");
    if (k === nama) return decodeURIComponent(v.join("="));
  }
  return null;
}

async function pastikanCsrf(): Promise<string> {
  const ada = bacaCookie(COOKIE_CSRF);
  if (ada) return ada;
  const r = await fetch("/api/auth/csrf", { credentials: "include" });
  const isi = (await r.json()) as { csrf: string };
  return bacaCookie(COOKIE_CSRF) ?? isi.csrf;
}

let refreshBerjalan: Promise<boolean> | null = null;

function refreshSesi(): Promise<boolean> {
  if (!refreshBerjalan) {
    refreshBerjalan = (async () => {
      try {
        const csrf = await pastikanCsrf();
        const r = await fetch("/api/auth/refresh", {
          method: "POST",
          credentials: "include",
          headers: { "X-CSRF-Token": csrf },
        });
        return r.ok;
      } catch {
        return false;
      } finally {
        setTimeout(() => (refreshBerjalan = null), 0);
      }
    })();
  }
  return refreshBerjalan;
}

export interface OpsiApi {
  metode?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  isi?: unknown;
  alasan?: string;
}

export async function api<T>(jalur: string, opsi: OpsiApi = {}, ulang = true): Promise<T> {
  const metode = opsi.metode ?? "GET";
  const headers: Record<string, string> = { Accept: "application/json" };
  if (opsi.isi !== undefined) headers["Content-Type"] = "application/json";
  if (!METODE_AMAN.has(metode)) headers["X-CSRF-Token"] = await pastikanCsrf();
  if (opsi.alasan) headers["X-Alasan"] = encodeURIComponent(opsi.alasan);

  let r: Response;
  try {
    r = await fetch(jalur, {
      method: metode,
      credentials: "include",
      headers,
      body: opsi.isi === undefined ? undefined : JSON.stringify(opsi.isi),
    });
  } catch {
    throw new GalatApi(0, "JARINGAN", "Tidak dapat terhubung ke server. Periksa jaringan/VPN.");
  }
  const isi = r.status === 204 ? null : await r.json().catch(() => null);
  if (r.ok) return isi as T;

  const kode = (isi && typeof isi === "object" && "kode" in isi ? String(isi.kode) : "") || "HTTP";
  if (r.status === 401 && kode === "TOKEN_KEDALUWARSA" && ulang && !TANPA_REFRESH.includes(jalur)) {
    if (await refreshSesi()) return api<T>(jalur, opsi, false);
  }
  const pesan =
    (isi && typeof isi === "object" && "pesan" in isi ? String(isi.pesan) : "") ||
    "Terjadi kesalahan. Silakan coba lagi.";
  throw new GalatApi(r.status, kode, pesan, isi && typeof isi === "object" && "rincian" in isi ? isi.rincian : undefined);
}

// ---- tipe respons
export interface Penugasan {
  tahun_dasar: string;
  wilayah_kode: string;
  lapus: string;
  peran_tugas: string;
}
export interface Profil {
  id: number;
  username: string;
  nama: string;
  wajib_ganti_sandi: boolean;
  peran: string[];
  izin: string[];
  penugasan: Penugasan[];
}
export interface TahunDasar {
  id: number;
  kode: string;
  tahun_dasar: number;
  status: "rencana" | "paralel" | "produksi" | "arsip";
  klasifikasi: string;
  tahun_awal_seri: number;
  tahun_baseline_eks: number;
  keterangan: string | null;
}
export interface HasilMasuk {
  tahap: "totp" | "daftar_totp";
  qr_svg: string | null;
  rahasia: string | null;
}

// ---- berkas: unggah badan mentah (xlsx/csv) dan unduh lampiran (templat, CSV)
export async function unggahBerkas<T>(jalur: string, berkas: Blob): Promise<T> {
  let r: Response;
  try {
    r = await fetch(jalur, {
      method: "POST",
      credentials: "include",
      headers: { Accept: "application/json", "Content-Type": "application/octet-stream", "X-CSRF-Token": await pastikanCsrf() },
      body: berkas,
    });
  } catch {
    throw new GalatApi(0, "JARINGAN", "Tidak dapat terhubung ke server. Periksa jaringan/VPN.");
  }
  const isi = await r.json().catch(() => null);
  if (r.ok) return isi as T;
  if (r.status === 401 && (await refreshSesi())) return unggahBerkas<T>(jalur, berkas);
  throw new GalatApi(r.status, isi?.kode ?? "HTTP", isi?.pesan ?? "Unggah gagal. Silakan coba lagi.", isi?.rincian);
}

export function namaDariHeader(cd: string | null, bawaan: string): string {
  const m = /filename="?([^";]+)"?/i.exec(cd ?? "");
  return m ? m[1] : bawaan;
}

export async function unduhBerkas(jalur: string, bawaan: string): Promise<void> {
  const r = await fetch(jalur, { credentials: "include" });
  if (!r.ok) {
    const isi = await r.json().catch(() => null);
    throw new GalatApi(r.status, isi?.kode ?? "HTTP", isi?.pesan ?? "Unduhan gagal.");
  }
  const blob = await r.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = namaDariHeader(r.headers.get("Content-Disposition"), bawaan);
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
