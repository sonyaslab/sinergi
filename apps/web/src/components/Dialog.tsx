import { useEffect, type ReactNode } from "react";

/** Dialog modal sederhana (Esc menutup). */
export function Dialog({ judul, tutup, children, lebar = "max-w-lg" }: { judul: string; tutup: () => void; children: ReactNode; lebar?: string }) {
  useEffect(() => {
    const f = (e: KeyboardEvent) => e.key === "Escape" && tutup();
    window.addEventListener("keydown", f);
    return () => window.removeEventListener("keydown", f);
  }, [tutup]);
  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-slate-900/40 p-6" role="presentation" onMouseDown={(e) => e.target === e.currentTarget && tutup()}>
      <div role="dialog" aria-modal="true" aria-label={judul} className={`w-full ${lebar} rounded-lg bg-white p-4 shadow-xl`}>
        <div className="mb-3 flex items-center justify-between">
          <h2 className="font-semibold">{judul}</h2>
          <button type="button" onClick={tutup} className="text-sm text-slate-500 hover:text-slate-800" aria-label="Tutup">✕</button>
        </div>
        {children}
      </div>
    </div>
  );
}
