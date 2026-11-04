import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import { api, type TahunDasar } from "../api/klien";

const KUNCI = "sinergi_td";

interface NilaiKonteks {
  daftar: TahunDasar[];
  aktif: TahunDasar | null;
  pilih: (kode: string) => void;
  memuat: boolean;
}

const Konteks = createContext<NilaiKonteks>({ daftar: [], aktif: null, pilih: () => {}, memuat: true });

function bacaSimpanan(): string | null {
  try {
    return localStorage.getItem(KUNCI);
  } catch {
    return null;
  }
}

function simpan(kode: string): void {
  try {
    localStorage.setItem(KUNCI, kode);
  } catch {
    /* penyimpanan peramban tidak tersedia: pilihan tetap berlaku selama halaman terbuka */
  }
}

export function PenyediaTahunDasar({ children }: { children: ReactNode }) {
  const q = useQuery({ queryKey: ["tahun-dasar"], queryFn: () => api<TahunDasar[]>("/api/tahun-dasar") });
  const [kode, setKode] = useState<string | null>(bacaSimpanan);
  const daftar = useMemo(() => q.data ?? [], [q.data]);

  useEffect(() => {
    // Bawaan: urutan pertama dari server (status produksi), bila pilihan tersimpan tidak ada di master.
    if (daftar.length && !daftar.some((t) => t.kode === kode)) setKode(daftar[0].kode);
  }, [daftar, kode]);

  const nilai = useMemo<NilaiKonteks>(
    () => ({
      daftar,
      aktif: daftar.find((t) => t.kode === kode) ?? null,
      pilih: (k: string) => {
        setKode(k);
        simpan(k);
      },
      memuat: q.isLoading,
    }),
    [daftar, kode, q.isLoading],
  );
  return <Konteks.Provider value={nilai}>{children}</Konteks.Provider>;
}

export function useTahunDasar(): NilaiKonteks {
  return useContext(Konteks);
}
