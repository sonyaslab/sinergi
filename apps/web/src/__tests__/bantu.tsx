import type { ReactNode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { vi } from "vitest";

export type Rute = Record<string, (init?: RequestInit) => { status?: number; isi: unknown }>;

/** Ganti global fetch dengan tabel rute "METODE /jalur" -> respons JSON. */
export function tiruFetch(rute: Rute) {
  const f = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const kunci = `${init?.method ?? "GET"} ${String(input)}`;
    const h = rute[kunci];
    if (!h) throw new Error(`rute tiruan tidak ada: ${kunci}`);
    const { status = 200, isi } = h(init);
    return new Response(JSON.stringify(isi), { status, headers: { "Content-Type": "application/json" } });
  });
  vi.stubGlobal("fetch", f);
  return f;
}

export function Bungkus({ children }: { children: ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <QueryClientProvider client={qc}>
      <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>{children}</MemoryRouter>
    </QueryClientProvider>
  );
}
