import { useState, type FormEvent } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { api, GalatApi } from "../api/klien";

const kelasInput =
  "w-full rounded border border-slate-300 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-merek-500";

export function GantiSandi({ wajib = false }: { wajib?: boolean }) {
  const qc = useQueryClient();
  const [lama, setLama] = useState("");
  const [baru, setBaru] = useState("");
  const [ulang, setUlang] = useState("");
  const [pesan, setPesan] = useState<{ ok: boolean; teks: string } | null>(null);

  async function kirim(e: FormEvent) {
    e.preventDefault();
    if (baru !== ulang) return setPesan({ ok: false, teks: "Ulangi sandi baru tidak sama." });
    try {
      await api("/api/auth/ganti-sandi", { metode: "POST", isi: { sandi_lama: lama, sandi_baru: baru } });
      setPesan({ ok: true, teks: "Sandi berhasil diganti." });
      setLama("");
      setBaru("");
      setUlang("");
      await qc.invalidateQueries({ queryKey: ["saya"] });
    } catch (err) {
      setPesan({ ok: false, teks: err instanceof GalatApi ? err.message : "Gagal mengganti sandi." });
    }
  }

  return (
    <div className="mx-auto mt-10 max-w-sm rounded-lg border border-slate-200 bg-white p-6">
      <h1 className="mb-1 text-lg font-semibold">Ganti sandi</h1>
      {wajib && <p className="mb-3 text-sm text-slate-600">Ini login pertama Anda. Ganti sandi sementara sebelum melanjutkan.</p>}
      {pesan && (
        <div role="alert" className={`mb-3 rounded px-3 py-2 text-sm ${pesan.ok ? "bg-green-50 text-green-700" : "bg-red-50 text-red-700"}`}>
          {pesan.teks}
        </div>
      )}
      <form onSubmit={kirim} className="space-y-3 text-sm">
        <label className="block">Sandi lama<input className={kelasInput} type="password" autoComplete="current-password" required value={lama} onChange={(e) => setLama(e.target.value)} /></label>
        <label className="block">Sandi baru (min. 12 karakter)<input className={kelasInput} type="password" autoComplete="new-password" minLength={12} required value={baru} onChange={(e) => setBaru(e.target.value)} /></label>
        <label className="block">Ulangi sandi baru<input className={kelasInput} type="password" autoComplete="new-password" required value={ulang} onChange={(e) => setUlang(e.target.value)} /></label>
        <button className="w-full rounded bg-merek-600 py-2 font-semibold text-white hover:bg-merek-700">Simpan</button>
      </form>
    </div>
  );
}
