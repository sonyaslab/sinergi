import { useState } from "react";
import { useQuery, useQueryClient, type QueryKey } from "@tanstack/react-query";
import { api, GalatApi } from "./klien";

/** Ambil daftar (GET) dengan cache TanStack Query. `jalur` null = belum siap. */
export function useDaftar<T>(kunci: QueryKey, jalur: string | null) {
  return useQuery({ queryKey: kunci, queryFn: () => api<T>(jalur as string), enabled: jalur !== null });
}

export interface PesanAksi {
  jenis: "ok" | "galat";
  teks: string;
}

/** Jalankan aksi tulis, segarkan kueri terkait, dan simpan pesan sukses/galat berbahasa Indonesia. */
export function useAksi(segarkan: QueryKey[]) {
  const qc = useQueryClient();
  const [pesan, setPesan] = useState<PesanAksi | null>(null);
  const [sibuk, setSibuk] = useState(false);

  async function jalankan<T>(fn: () => Promise<T>, ok?: string | ((r: T) => string)): Promise<T | undefined> {
    setPesan(null);
    setSibuk(true);
    try {
      const r = await fn();
      await Promise.all(segarkan.map((k) => qc.invalidateQueries({ queryKey: k })));
      if (ok) setPesan({ jenis: "ok", teks: typeof ok === "function" ? ok(r) : ok });
      return r;
    } catch (e) {
      setPesan({ jenis: "galat", teks: e instanceof GalatApi ? e.message : "Aksi gagal. Coba lagi." });
      return undefined;
    } finally {
      setSibuk(false);
    }
  }
  return { jalankan, pesan, setPesan, sibuk };
}

/** Izin pengguna saat ini (dari profil /api/auth/saya di cache). */
export function useIzin(): ReadonlySet<string> {
  const qc = useQueryClient();
  const izin = qc.getQueryData<{ izin?: string[] }>(["saya"])?.izin;
  return new Set(izin ?? []);
}
