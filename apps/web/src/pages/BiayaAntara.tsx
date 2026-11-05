// Layar LK Biaya Antara (F4): output dan rincian BA tahun dasar (SE2026/SUT) per kategori/subkategori/lapus/item, rasio KA
// otomatis, persetujuan, lalu Terapkan ke RKA_TD item putaran terpilih (urutan cari: item → lapus → induk).
import { useEffect, useMemo, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { api, GalatApi } from "../api/klien";
import { useDaftar, useIzin } from "../api/hooks";
import type { Lapus } from "../api/tipe";
import { Dialog } from "../components/Dialog";
import { PemilihPutaran, usePilihanPutaran } from "../components/PemilihPutaran";
import { Centang, Isian, Lencana, Masukan, Pesan, Pilihan, Tombol, kelasTabel, kelasTd, kelasTh } from "../components/ui";
import { formatNilai, formatPersen } from "../lib/putaran";
import { uraiAngka } from "../lib/tempel";

interface LapusBA { id: number; kode: string; nama: string; jenis: string; level: number; induk_id: number | null; boleh_tulis: boolean }
interface ItemBA { id: number; lapus_id: number; kode_lapus: string; metode: string; nomor: number; nama: string; status: string }
export interface BarisBA {
  id: number; lapus_id: number; item_id: number | null; output: number | null; ba_bahan: number | null; ba_energi: number | null;
  ba_jasa: number | null; ba_sewa: number | null; ba_lainnya: number | null; ba_total_langsung: number | null;
  total_ba: number | null; rasio_ka: number | null; sumber: string; status: "draf" | "disetujui"; diubah_oleh: string | null;
}
interface DataBA { lapus: LapusBA[]; item: ItemBA[]; baris: BarisBA[] }
interface RencanaRKA { id: number; kode_lapus: string; metode: string; nomor: number; nama: string; lama: number | null; baru: number | null; sumber: string | null; aksi: string }

export const KOLOM_BA: { kunci: keyof BarisBA; label: string }[] = [
  { kunci: "output", label: "Output" },
  { kunci: "ba_bahan", label: "BA bahan" },
  { kunci: "ba_energi", label: "BA energi" },
  { kunci: "ba_jasa", label: "BA jasa" },
  { kunci: "ba_sewa", label: "BA sewa" },
  { kunci: "ba_lainnya", label: "BA lainnya" },
  { kunci: "ba_total_langsung", label: "Total BA langsung" },
];

/** Rasio KA = total BA ÷ output (total = Σ rincian; bila rincian kosong, total langsung). Sama dengan kolom terhitung DB. */
export function rasioKA(x: Partial<Record<keyof BarisBA, number | null>>): number | null {
  const rinci = ["ba_bahan", "ba_energi", "ba_jasa", "ba_sewa", "ba_lainnya"].reduce((a, k) => a + ((x[k as keyof BarisBA] as number | null) ?? 0), 0);
  const total = rinci !== 0 ? rinci : x.ba_total_langsung ?? null;
  return x.output && x.output > 0 && total !== null ? total / x.output : null;
}

const LABEL_AKSI: Record<string, string> = {
  ubah: "Diubah", sama: "Sama", tanpa_sumber: "Tanpa rasio disetujui", sudah_terisi: "Sudah terisi (dilewati)", tidak_ditugaskan: "Tidak ditugaskan",
};

export function BiayaAntara() {
  const pil = usePilihanPutaran();
  const { td, put, wil } = pil;
  const qc = useQueryClient();
  const izin = useIzin();
  const qLapus = useDaftar<Lapus[]>(["lapus", td?.id], td ? `/api/tahun-dasar/${td.id}/lapus` : null).data;
  const akar = useMemo(() => (qLapus ?? []).filter((l) => l.aktif && l.induk_id === null && (l.jenis === "kategori" || l.jenis === "daun")), [qLapus]);
  const [kat, setKat] = useState<number | null>(null);
  useEffect(() => {
    if (akar.length && !akar.some((a) => a.id === kat)) setKat(akar[0].id);
  }, [akar, kat]);
  const kunci = ["struktur-biaya", td?.id, wil, kat];
  const q = useDaftar<DataBA>(kunci, td && kat ? `/api/struktur-biaya?tahun_dasar_id=${td.id}&wilayah=${wil}&lapus_id=${kat}` : null);
  const d = q.data;
  const [ubah, setUbah] = useState<{ lapus: LapusBA; item: ItemBA | null; baris: BarisBA | null } | null>(null);
  const [pilih, setPilih] = useState<Set<number>>(new Set());
  const [terapkan, setTerapkan] = useState(false);
  const [pesan, setPesan] = useState<{ jenis: "ok" | "galat" | "info"; teks: string } | null>(null);
  if (!td) return <p className="text-slate-500">Memuat tahun dasar…</p>;
  const barisDari = (lid: number, iid: number | null) => d?.baris.find((b) => b.lapus_id === lid && b.item_id === iid) ?? null;

  async function setujui(nilai: boolean) {
    setPesan(null);
    try {
      const r = await api<{ pesan: string }>("/api/struktur-biaya/setujui", { metode: "POST", isi: { id: [...pilih], setujui: nilai } });
      setPilih(new Set());
      setPesan({ jenis: "ok", teks: r.pesan });
      qc.invalidateQueries({ queryKey: ["struktur-biaya"] });
    } catch (e) {
      setPesan({ jenis: "galat", teks: e instanceof GalatApi ? e.message : "Gagal." });
    }
  }

  const sel = (b: BarisBA | null, k: keyof BarisBA) => (b ? formatNilai(b[k] as number | null) : "");
  const barisTabel = (d?.lapus ?? []).flatMap((l) => [
    { lapus: l, item: null as ItemBA | null },
    ...(d?.item ?? []).filter((i) => i.lapus_id === l.id).map((i) => ({ lapus: l, item: i })),
  ]);

  return (
    <div>
      <h1 className="mb-2 text-xl font-semibold">Biaya Antara tahun dasar</h1>
      <PemilihPutaran p={pil} />
      <div className="mb-3 flex flex-wrap items-end gap-3">
        <div className="w-72"><Isian label="Kategori">
          <Pilihan value={kat ?? ""} onChange={(e) => setKat(Number(e.target.value))} aria-label="Kategori">
            {akar.map((a) => <option key={a.id} value={a.id}>{a.kode} — {a.nama}</option>)}
          </Pilihan>
        </Isian></div>
        {izin.has("lk.setujui") && (
          <>
            <Tombol disabled={!pilih.size} onClick={() => setujui(true)}>Setujui terpilih ({pilih.size})</Tombol>
            <Tombol disabled={!pilih.size} onClick={() => setujui(false)}>Kembalikan ke draf</Tombol>
          </>
        )}
        {izin.has("biaya_antara.isi") && <Tombol varian="utama" disabled={!put || put.status === "terkunci"} onClick={() => setTerapkan(true)}>Terapkan ke RKA tahun dasar…</Tombol>}
      </div>
      <p className="mb-1 text-xs text-slate-500">Rasio KA dipakai setelah disetujui. Rasio item mengalahkan rasio lapus, rasio lapus mengalahkan induk (subkategori, kategori). TOP/SOP tanpa konsumsi antara.</p>
      {pesan && <div className="mb-2"><Pesan jenis={pesan.jenis}>{pesan.teks}</Pesan></div>}
      <div className="max-h-[64vh] overflow-auto rounded border border-slate-200 bg-white">
        <table className={kelasTabel}>
          <thead><tr>{["", "Lapus / item", ...KOLOM_BA.map((k) => k.label), "Total BA", "Rasio KA", "Sumber", "Status", ""].map((h, i) => <th key={i} className={`${kelasTh} ${i > 1 && i < 11 ? "text-right" : ""}`}>{h}</th>)}</tr></thead>
          <tbody>
            {barisTabel.map(({ lapus: l, item: it }) => {
              const b = barisDari(l.id, it?.id ?? null);
              return (
                <tr key={`${l.id}:${it?.id ?? "-"}`} className={!it && l.jenis !== "daun" ? "font-semibold" : it ? "text-slate-700" : ""}>
                  <td className={kelasTd}>
                    {b && izin.has("lk.setujui") && (
                      <input type="checkbox" className="accent-merek-600" aria-label={`Pilih ${l.kode}${it ? ` ${it.nama}` : ""}`} checked={pilih.has(b.id)}
                        onChange={(e) => { const s = new Set(pilih); if (e.target.checked) s.add(b.id); else s.delete(b.id); setPilih(s); }} />
                    )}
                  </td>
                  <td className={`${kelasTd} whitespace-nowrap`} style={{ paddingLeft: 8 + 12 * (Math.max(0, l.level - 1) + (it ? 1 : 0)) }}>
                    {it ? `${it.metode} ${it.nomor} · ${it.nama}` : <>{l.kode} <span className="font-normal text-slate-500">{l.nama}</span></>}
                  </td>
                  {KOLOM_BA.map((k) => <td key={k.kunci} className={`${kelasTd} text-right tabular-nums`}>{sel(b, k.kunci)}</td>)}
                  <td className={`${kelasTd} text-right tabular-nums`}>{sel(b, "total_ba")}</td>
                  <td className={`${kelasTd} text-right tabular-nums`}>{b?.rasio_ka !== null && b?.rasio_ka !== undefined ? formatPersen(b.rasio_ka * 100) + "%" : ""}</td>
                  <td className={kelasTd}>{b?.sumber ?? ""}</td>
                  <td className={kelasTd}>{b && <Lencana warna={b.status === "disetujui" ? "hijau" : "kuning"}>{b.status}</Lencana>}</td>
                  <td className={kelasTd}>{izin.has("biaya_antara.isi") && l.boleh_tulis && <Tombol kecil onClick={() => setUbah({ lapus: l, item: it, baris: b })}>{b ? "Ubah" : "Isi"}</Tombol>}</td>
                </tr>
              );
            })}
            {!barisTabel.length && <tr><td className={kelasTd} colSpan={14}>{q.isLoading ? "Memuat…" : "Pilih kategori."}</td></tr>}
          </tbody>
        </table>
      </div>
      {ubah && td && (
        <DialogBA td={td.id} wilayah={wil} lapus={ubah.lapus} item={ubah.item} baris={ubah.baris} tutup={() => setUbah(null)}
          selesai={(t) => { setUbah(null); setPesan({ jenis: "ok", teks: t }); qc.invalidateQueries({ queryKey: ["struktur-biaya"] }); }} />
      )}
      {terapkan && put && kat && (
        <DialogTerapkan putaran={put.id} wilayah={wil} lapus={kat} tutup={() => setTerapkan(false)}
          selesai={(t) => { setTerapkan(false); setPesan({ jenis: "ok", teks: t }); }} />
      )}
    </div>
  );
}

function DialogBA({ td, wilayah, lapus, item, baris, tutup, selesai }: { td: number; wilayah: string; lapus: LapusBA; item: ItemBA | null;
  baris: BarisBA | null; tutup: () => void; selesai: (t: string) => void }) {
  const [isi, setIsi] = useState<Record<string, string>>(() => Object.fromEntries(KOLOM_BA.map((k) => [k.kunci, baris?.[k.kunci] != null ? String(baris[k.kunci]).replace(".", ",") : ""])));
  const [sumber, setSumber] = useState(baris?.sumber ?? "SE2026");
  const [galat, setGalat] = useState<string | null>(null);
  const angka: Record<string, number | null> = {};
  let salah: string | null = null;
  for (const k of KOLOM_BA) {
    const a = uraiAngka(isi[k.kunci] ?? "");
    if (a.jenis === "angka") angka[k.kunci] = a.nilai;
    else if (a.jenis === "kosong") angka[k.kunci] = null;
    else salah = `${k.label} harus angka.`;
  }
  const rasio = rasioKA(angka);
  async function simpan() {
    try {
      const r = await api<{ pesan: string; peringatan: string | null }>("/api/struktur-biaya", { metode: "PUT", isi: {
        tahun_dasar_id: td, wilayah, lapus_id: lapus.id, item_id: item?.id ?? null, sumber, ...angka } });
      selesai(r.peringatan ? `${r.pesan} ${r.peringatan}` : r.pesan);
    } catch (e) {
      setGalat(e instanceof GalatApi ? e.message : "Gagal menyimpan.");
    }
  }
  return (
    <Dialog judul={`Biaya antara ${lapus.kode}${item ? ` · ${item.nama}` : ""}`} tutup={tutup}>
      <div className="grid grid-cols-2 gap-3">
        {KOLOM_BA.map((k) => (
          <Isian key={k.kunci} label={k.label}>
            <Masukan inputMode="decimal" value={isi[k.kunci] ?? ""} onChange={(e) => setIsi({ ...isi, [k.kunci]: e.target.value })} aria-label={k.label} />
          </Isian>
        ))}
        <Isian label="Sumber"><Masukan value={sumber} onChange={(e) => setSumber(e.target.value)} aria-label="Sumber" /></Isian>
      </div>
      <p className="mt-2 text-sm">Rasio KA: <b>{rasio !== null ? `${formatPersen(rasio * 100)}%` : "-"}</b> <span className="text-xs text-slate-500">(isi rincian, atau total langsung bila rincian tidak tersedia)</span></p>
      {(galat || salah) && <div className="mt-2"><Pesan jenis="galat">{galat ?? salah}</Pesan></div>}
      <div className="mt-4 flex justify-end gap-2"><Tombol onClick={tutup}>Batal</Tombol><Tombol varian="utama" disabled={!!salah} onClick={simpan}>Simpan (draf)</Tombol></div>
    </Dialog>
  );
}

function DialogTerapkan({ putaran, wilayah, lapus, tutup, selesai }: { putaran: number; wilayah: string; lapus: number; tutup: () => void; selesai: (t: string) => void }) {
  const [hanyaKosong, setHanyaKosong] = useState(false);
  const [rencana, setRencana] = useState<{ baris: RencanaRKA[]; ringkasan: Record<string, number> } | null>(null);
  const [galat, setGalat] = useState<string | null>(null);
  async function jalankan(terapkan: boolean) {
    setGalat(null);
    try {
      const r = await api<{ baris: RencanaRKA[]; ringkasan: Record<string, number>; pesan: string }>("/api/struktur-biaya/terapkan", {
        metode: "POST", isi: { putaran_id: putaran, wilayah, lapus_id: lapus, hanya_kosong: hanyaKosong, terapkan } });
      if (terapkan) selesai(r.pesan);
      else setRencana(r);
    } catch (e) {
      setGalat(e instanceof GalatApi ? e.message : "Gagal.");
    }
  }
  useEffect(() => { void jalankan(false); }, [hanyaKosong]); // eslint-disable-line react-hooks/exhaustive-deps
  return (
    <Dialog judul="Terapkan rasio KA ke RKA tahun dasar" tutup={tutup} lebar="max-w-3xl">
      <Centang label="Hanya item yang RKA tahun dasarnya masih kosong" checked={hanyaKosong} onChange={(e) => setHanyaKosong(e.target.checked)} />
      {rencana && (
        <>
          <p className="my-2 text-sm">{Object.entries(rencana.ringkasan).map(([k, n]) => `${LABEL_AKSI[k] ?? k}: ${n}`).join(" · ")}</p>
          <div className="max-h-80 overflow-auto rounded border border-slate-200">
            <table className={kelasTabel} aria-label="Pratinjau terapkan">
              <thead><tr>{["Item", "Lama", "Baru", "Sumber", "Keterangan"].map((h) => <th key={h} className={kelasTh}>{h}</th>)}</tr></thead>
              <tbody>{rencana.baris.map((b) => (
                <tr key={b.id} className={b.aksi === "ubah" ? "" : "text-slate-400"}>
                  <td className={kelasTd}>{b.kode_lapus} {b.metode} {b.nomor} · {b.nama}</td>
                  <td className={`${kelasTd} text-right tabular-nums`}>{formatNilai(b.lama)}</td>
                  <td className={`${kelasTd} text-right tabular-nums`}>{formatNilai(b.baru)}</td>
                  <td className={kelasTd}>{b.sumber ?? ""}</td>
                  <td className={kelasTd}>{LABEL_AKSI[b.aksi] ?? b.aksi}</td>
                </tr>
              ))}</tbody>
            </table>
          </div>
        </>
      )}
      {galat && <div className="mt-2"><Pesan jenis="galat">{galat}</Pesan></div>}
      <div className="mt-4 flex justify-end gap-2">
        <Tombol onClick={tutup}>Batal</Tombol>
        <Tombol varian="utama" disabled={!rencana?.ringkasan.ubah} onClick={() => jalankan(true)}>Terapkan ({rencana?.ringkasan.ubah ?? 0} item)</Tombol>
      </div>
    </Dialog>
  );
}
