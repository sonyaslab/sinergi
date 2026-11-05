import { useState } from "react";
import { Tab } from "../components/ui";
import { PenggunaTab } from "./akses/PenggunaTab";
import { PenugasanTab } from "./akses/PenugasanTab";
import { PeranIzinTab } from "./akses/PeranIzinTab";

type Kunci = "pengguna" | "peran" | "penugasan";

export function PenggunaAkses() {
  const [tab, setTab] = useState<Kunci>("pengguna");
  return (
    <div>
      <h1 className="mb-2 text-xl font-semibold">Pengguna &amp; hak akses</h1>
      <Tab<Kunci> daftar={[{ kunci: "pengguna", label: "Pengguna" }, { kunci: "peran", label: "Peran & izin" }, { kunci: "penugasan", label: "Penugasan" }]} aktif={tab} ubah={setTab} />
      {tab === "pengguna" && <PenggunaTab />}
      {tab === "peran" && <PeranIzinTab />}
      {tab === "penugasan" && <PenugasanTab />}
    </div>
  );
}
