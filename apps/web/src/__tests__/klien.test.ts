import { describe, expect, it } from "vitest";
import { api, bacaCookie, GalatApi } from "../api/klien";
import { tiruFetch } from "./bantu";

describe("klien API", () => {
  it("membaca cookie", () => {
    expect(bacaCookie("sinergi_csrf", "a=1; sinergi_csrf=abc.def; b=2")).toBe("abc.def");
    expect(bacaCookie("tidak", "a=1")).toBeNull();
  });

  it("POST membawa X-CSRF-Token dan X-Alasan", async () => {
    document.cookie = "sinergi_csrf=tok.sig; path=/";
    const f = tiruFetch({ "POST /api/x": () => ({ isi: { ok: true } }) });
    await api("/api/x", { metode: "POST", isi: { a: 1 }, alasan: "koreksi data BPS" });
    const h = f.mock.calls[0][1]!.headers as Record<string, string>;
    expect(h["X-CSRF-Token"]).toBe("tok.sig");
    expect(decodeURIComponent(h["X-Alasan"])).toBe("koreksi data BPS");
  });

  it("token kedaluwarsa -> refresh sekali lalu ulang", async () => {
    document.cookie = "sinergi_csrf=tok.sig; path=/";
    let n = 0;
    const f = tiruFetch({
      "GET /api/data": () => (n++ === 0 ? { status: 401, isi: { kode: "TOKEN_KEDALUWARSA", pesan: "x" } } : { isi: [1] }),
      "POST /api/auth/refresh": () => ({ isi: { ok: true } }),
    });
    await expect(api("/api/data")).resolves.toEqual([1]);
    expect(f).toHaveBeenCalledTimes(3);
  });

  it("galat server -> GalatApi berpesan Indonesia", async () => {
    tiruFetch({ "GET /api/kunci": () => ({ status: 423, isi: { kode: "PUTARAN_TERKUNCI", pesan: "Putaran sudah dikunci." } }) });
    const e = (await api("/api/kunci").catch((x: unknown) => x)) as GalatApi;
    expect(e).toBeInstanceOf(GalatApi);
    expect(e.status).toBe(423);
    expect(e.message).toBe("Putaran sudah dikunci.");
  });
});
