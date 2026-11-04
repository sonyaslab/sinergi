import { useState, type FormEvent } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { api, GalatApi, type HasilMasuk, type Profil } from "../api/klien";
import { INSTITUSI, KEPANJANGAN, Logo, NAMA_PRODUK } from "../components/Logo";

type Tahap = { jenis: "sandi" } | { jenis: "totp"; daftar: HasilMasuk | null };

const kelasInput =
  "w-full rounded border border-slate-300 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-merek-500";

export function Login() {
  const qc = useQueryClient();
  const [tahap, setTahap] = useState<Tahap>({ jenis: "sandi" });
  const [username, setUsername] = useState("");
  const [sandi, setSandi] = useState("");
  const [kode, setKode] = useState("");
  const [galat, setGalat] = useState<string | null>(null);
  const [sibuk, setSibuk] = useState(false);

  async function kirimSandi(e: FormEvent) {
    e.preventDefault();
    setGalat(null);
    setSibuk(true);
    try {
      const h = await api<HasilMasuk>("/api/auth/login", { metode: "POST", isi: { username, sandi } });
      setSandi("");
      setTahap({ jenis: "totp", daftar: h.tahap === "daftar_totp" ? h : null });
    } catch (err) {
      setGalat(err instanceof GalatApi ? err.message : "Gagal masuk.");
    } finally {
      setSibuk(false);
    }
  }

  async function kirimKode(e: FormEvent) {
    e.preventDefault();
    setGalat(null);
    setSibuk(true);
    try {
      const profil = await api<Profil>("/api/auth/totp", { metode: "POST", isi: { kode: kode.replace(/\s/g, "") } });
      qc.setQueryData(["saya"], profil);
    } catch (err) {
      setKode("");
      if (err instanceof GalatApi && err.kode === "PRA_KEDALUWARSA") setTahap({ jenis: "sandi" });
      setGalat(err instanceof GalatApi ? err.message : "Gagal verifikasi.");
    } finally {
      setSibuk(false);
    }
  }

  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-gradient-to-b from-merek-50 to-white p-4">
      <div className="w-full max-w-sm rounded-lg border border-slate-200 bg-white p-6 shadow-sm">
        <div className="mb-5 flex flex-col items-center text-center">
          <Logo ukuran={56} />
          <h1 className="mt-3 text-3xl font-bold tracking-wider text-merek-700">{NAMA_PRODUK}</h1>
          <p className="text-sm text-slate-600">{KEPANJANGAN}</p>
          <p className="text-xs text-slate-500">{INSTITUSI}</p>
        </div>

        {galat && (
          <div role="alert" className="mb-3 rounded border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
            {galat}
          </div>
        )}

        {tahap.jenis === "sandi" ? (
          <form onSubmit={kirimSandi} className="space-y-3">
            <label className="block text-sm">
              Nama pengguna
              <input className={kelasInput} autoComplete="username" autoFocus required value={username}
                onChange={(e) => setUsername(e.target.value)} />
            </label>
            <label className="block text-sm">
              Sandi
              <input className={kelasInput} type="password" autoComplete="current-password" required value={sandi}
                onChange={(e) => setSandi(e.target.value)} />
            </label>
            <button disabled={sibuk} className="w-full rounded bg-merek-600 py-2 font-semibold text-white hover:bg-merek-700 disabled:opacity-60">
              {sibuk ? "Memeriksa…" : "Masuk"}
            </button>
          </form>
        ) : (
          <form onSubmit={kirimKode} className="space-y-3">
            {tahap.daftar ? (
              <div className="space-y-2 text-sm">
                <p className="font-semibold">Aktifkan verifikasi dua langkah</p>
                <p className="text-slate-600">Pindai kode QR dengan aplikasi autentikator (Google/Microsoft Authenticator), lalu isi kode 6 digit.</p>
                {tahap.daftar.qr_svg && (
                  <img src={tahap.daftar.qr_svg} alt="Kode QR pendaftaran autentikator" className="mx-auto h-44 w-44" />
                )}
                <p className="break-all rounded bg-slate-100 px-2 py-1 text-center font-mono text-xs" title="Kode untuk diketik manual">
                  {tahap.daftar.rahasia}
                </p>
              </div>
            ) : (
              <p className="text-sm text-slate-600">Masukkan kode 6 digit dari aplikasi autentikator.</p>
            )}
            <label className="block text-sm">
              Kode verifikasi
              <input className={`${kelasInput} text-center font-mono text-lg tracking-[0.4em]`} inputMode="numeric"
                autoComplete="one-time-code" pattern="[0-9 ]{6,7}" maxLength={7} autoFocus required value={kode}
                onChange={(e) => setKode(e.target.value)} />
            </label>
            <button disabled={sibuk} className="w-full rounded bg-merek-600 py-2 font-semibold text-white hover:bg-merek-700 disabled:opacity-60">
              {sibuk ? "Memeriksa…" : "Verifikasi"}
            </button>
            <button type="button" className="w-full text-sm text-slate-500 hover:underline" onClick={() => setTahap({ jenis: "sandi" })}>
              Kembali
            </button>
          </form>
        )}
      </div>
      <p className="mt-4 text-xs text-slate-400">Hanya untuk pengguna berwenang. Aktivitas dicatat.</p>
    </div>
  );
}
