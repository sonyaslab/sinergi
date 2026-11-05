// Komponen UI dasar SINERGI: sederhana, ramah operator, teks sedikit.
import type { ButtonHTMLAttributes, InputHTMLAttributes, ReactNode, SelectHTMLAttributes } from "react";

type Varian = "utama" | "biasa" | "bahaya" | "teks";
const KELAS_TOMBOL: Record<Varian, string> = {
  utama: "bg-merek-600 text-white hover:bg-merek-700 border border-merek-600",
  biasa: "bg-white text-slate-700 hover:bg-slate-100 border border-slate-300",
  bahaya: "bg-white text-red-700 hover:bg-red-50 border border-red-300",
  teks: "text-merek-700 hover:underline",
};

export function Tombol({ varian = "biasa", kecil, className = "", ...p }: ButtonHTMLAttributes<HTMLButtonElement> & {
  varian?: Varian;
  kecil?: boolean;
}) {
  return (
    <button
      type="button"
      className={`rounded ${kecil ? "px-2 py-0.5 text-xs" : "px-3 py-1.5 text-sm"} font-medium disabled:cursor-not-allowed disabled:opacity-50 ${KELAS_TOMBOL[varian]} ${className}`}
      {...p}
    />
  );
}

export const kelasInput =
  "w-full rounded border border-slate-300 px-2 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-merek-500";

export function Isian({ label, petunjuk, children }: { label: string; petunjuk?: string; children: ReactNode }) {
  return (
    <label className="block text-sm">
      <span className="mb-0.5 block text-slate-700">{label}</span>
      {children}
      {petunjuk && <span className="mt-0.5 block text-xs text-slate-500">{petunjuk}</span>}
    </label>
  );
}

export function Masukan(p: InputHTMLAttributes<HTMLInputElement>) {
  return <input className={kelasInput} {...p} />;
}

export function Pilihan({ children, ...p }: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select className={kelasInput} {...p}>
      {children}
    </select>
  );
}

export function Centang({ label, ...p }: InputHTMLAttributes<HTMLInputElement> & { label: string }) {
  return (
    <label className="inline-flex items-center gap-1.5 text-sm">
      <input type="checkbox" className="h-4 w-4 accent-merek-600" {...p} />
      {label}
    </label>
  );
}

export function Pesan({ jenis, children }: { jenis: "ok" | "galat" | "info"; children: ReactNode }) {
  const k = { ok: "border-green-200 bg-green-50 text-green-800", galat: "border-red-200 bg-red-50 text-red-700", info: "border-sky-200 bg-sky-50 text-sky-800" }[jenis];
  return (
    <div role={jenis === "galat" ? "alert" : "status"} className={`rounded border px-3 py-2 text-sm ${k}`}>
      {children}
    </div>
  );
}

export function Lencana({ warna = "abu", children }: { warna?: "abu" | "hijau" | "merah" | "kuning" | "biru"; children: ReactNode }) {
  const k = {
    abu: "bg-slate-100 text-slate-700",
    hijau: "bg-green-100 text-green-800",
    merah: "bg-red-100 text-red-700",
    kuning: "bg-amber-100 text-amber-800",
    biru: "bg-merek-100 text-merek-700",
  }[warna];
  return <span className={`inline-block rounded px-1.5 py-0.5 text-xs font-medium ${k}`}>{children}</span>;
}

export function Tab<T extends string>({ daftar, aktif, ubah }: { daftar: { kunci: T; label: string }[]; aktif: T; ubah: (k: T) => void }) {
  return (
    <div role="tablist" className="mb-4 flex flex-wrap gap-1 border-b border-slate-200">
      {daftar.map((t) => (
        <button
          key={t.kunci}
          role="tab"
          type="button"
          aria-selected={aktif === t.kunci}
          onClick={() => ubah(t.kunci)}
          className={`-mb-px border-b-2 px-3 py-2 text-sm ${aktif === t.kunci ? "border-merek-600 font-semibold text-merek-700" : "border-transparent text-slate-600 hover:text-slate-900"}`}
        >
          {t.label}
        </button>
      ))}
    </div>
  );
}

export function Panel({ judul, tutup, children }: { judul: string; tutup?: () => void; children: ReactNode }) {
  return (
    <section className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="font-semibold">{judul}</h2>
        {tutup && (
          <Tombol varian="teks" onClick={tutup} aria-label="Tutup">
            Tutup
          </Tombol>
        )}
      </div>
      {children}
    </section>
  );
}

export const kelasTabel = "w-full border-collapse text-sm";
export const kelasTh = "border-b border-slate-200 bg-slate-50 px-2 py-1.5 text-left font-medium text-slate-600";
export const kelasTd = "border-b border-slate-100 px-2 py-1";
