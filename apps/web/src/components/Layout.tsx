import { NavLink, Outlet } from "react-router-dom";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api, type Profil } from "../api/klien";
import { menuUntuk } from "../menu";
import { INSTITUSI, KEPANJANGAN, Logo, NAMA_PRODUK } from "./Logo";
import { PemilihTahunDasar } from "./PemilihTahunDasar";

export function Sidebar({ izin }: { izin: string[] }) {
  return (
    <nav aria-label="Menu utama" className="flex flex-col gap-0.5 p-2">
      {menuUntuk(izin).map((m) => (
        <NavLink
          key={m.jalur}
          to={m.jalur}
          end={m.jalur === "/"}
          className={({ isActive }) =>
            `rounded px-3 py-2 text-sm ${isActive ? "bg-merek-600 font-semibold text-white" : "text-slate-700 hover:bg-merek-50"}`
          }
        >
          {m.label}
        </NavLink>
      ))}
    </nav>
  );
}

export function Layout({ profil }: { profil: Profil }) {
  const qc = useQueryClient();
  const keluar = useMutation({
    mutationFn: () => api("/api/auth/logout", { metode: "POST" }),
    onSettled: () => {
      qc.setQueryData(["saya"], null);
      qc.removeQueries({ predicate: (q) => q.queryKey[0] !== "saya" });
    },
  });
  return (
    <div className="flex h-screen flex-col bg-slate-50 text-slate-900">
      <header className="flex items-center justify-between border-b border-slate-200 bg-white px-4 py-2">
        <div className="flex items-center gap-3">
          <Logo />
          <div className="leading-tight">
            <div className="text-lg font-bold tracking-wide text-merek-700">{NAMA_PRODUK}</div>
            <div className="hidden text-xs text-slate-500 md:block">{INSTITUSI}</div>
          </div>
        </div>
        <PemilihTahunDasar />
        <div className="flex items-center gap-3 text-sm">
          <span title={profil.peran.join(", ")}>
            {profil.nama} <span className="text-slate-500">({profil.peran.join(", ")})</span>
          </span>
          <button
            type="button"
            onClick={() => keluar.mutate()}
            className="rounded border border-slate-300 px-3 py-1 hover:bg-slate-100"
          >
            Keluar
          </button>
        </div>
      </header>
      <div className="flex min-h-0 flex-1">
        <aside className="w-56 shrink-0 overflow-y-auto border-r border-slate-200 bg-white">
          <Sidebar izin={profil.izin} />
        </aside>
        <main className="min-w-0 flex-1 overflow-auto p-6">
          <Outlet />
        </main>
      </div>
      <footer className="border-t border-slate-200 bg-white px-4 py-1 text-xs text-slate-500">
        {NAMA_PRODUK} — {KEPANJANGAN} · {INSTITUSI}
      </footer>
    </div>
  );
}
