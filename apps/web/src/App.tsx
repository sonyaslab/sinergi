import { Route, Routes } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api, GalatApi, type Profil } from "./api/klien";
import { Layout } from "./components/Layout";
import { PenyediaTahunDasar } from "./konteks/TahunDasar";
import { menuUntuk } from "./menu";
import { Beranda } from "./pages/Beranda";
import { GantiSandi } from "./pages/GantiSandi";
import { Login } from "./pages/Login";
import { JejakAudit } from "./pages/JejakAudit";
import { MasterData } from "./pages/MasterData";
import { PenggunaAkses } from "./pages/PenggunaAkses";
import { Segera } from "./pages/Segera";

// Layar yang sudah dibangun; menu lain menampilkan "dibangun pada fase Fx".
const HALAMAN: Record<string, () => JSX.Element> = {
  "/master": () => <MasterData />,
  "/pengguna": () => <PenggunaAkses />,
  "/audit": () => <JejakAudit />,
};

async function ambilProfil(): Promise<Profil | null> {
  try {
    return await api<Profil>("/api/auth/saya");
  } catch (e) {
    if (e instanceof GalatApi && e.status === 401) return null;
    throw e;
  }
}

export function App() {
  const q = useQuery({ queryKey: ["saya"], queryFn: ambilProfil, retry: false, staleTime: 60_000 });
  if (q.isLoading) return <div className="p-8 text-slate-500">Memuat…</div>;
  if (q.isError)
    return (
      <div role="alert" className="p-8 text-red-700">
        {q.error instanceof GalatApi ? q.error.message : "Tidak dapat memuat aplikasi."}
      </div>
    );
  const profil = q.data;
  if (!profil) return <Login />;
  if (profil.wajib_ganti_sandi) return <GantiSandi wajib />;
  return (
    <PenyediaTahunDasar>
      <Routes>
        <Route element={<Layout profil={profil} />}>
          <Route index element={<Beranda profil={profil} />} />
          {menuUntuk(profil.izin)
            .filter((m) => m.jalur !== "/")
            .map((m) => (
              <Route key={m.jalur} path={m.jalur} element={HALAMAN[m.jalur]?.() ?? <Segera />} />
            ))}
          <Route path="akun/sandi" element={<GantiSandi />} />
          <Route path="*" element={<p className="text-slate-500">Halaman tidak ditemukan atau Anda tidak memiliki akses.</p>} />
        </Route>
      </Routes>
    </PenyediaTahunDasar>
  );
}
