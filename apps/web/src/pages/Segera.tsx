import { useLocation } from "react-router-dom";
import { MENU } from "../menu";

export function Segera() {
  const { pathname } = useLocation();
  const m = MENU.find((x) => x.jalur === pathname);
  return (
    <div className="rounded-lg border border-dashed border-slate-300 bg-white p-8 text-center">
      <h1 className="text-lg font-semibold">{m?.label ?? "Halaman"}</h1>
      <p className="text-sm text-slate-500">Layar ini dibangun pada fase {m?.fase ?? "berikutnya"}.</p>
    </div>
  );
}
