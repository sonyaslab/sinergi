import { useMemo, useState, type FormEvent } from "react";
import { api } from "../../api/klien";
import { useAksi, useDaftar } from "../../api/hooks";
import type { HasilHapus, JenisLapus, Lapus } from "../../api/tipe";
import { useTahunDasar } from "../../konteks/TahunDasar";
import { barisTerlihat, calonInduk, geser, JENIS_INDUK, JENIS_TOTAL, pindahKe, punyaAnak, saudara } from "../../lib/pohon";
import { Centang, Isian, Lencana, Masukan, Panel, Pesan, Pilihan, Tombol, kelasTabel, kelasTd, kelasTh } from "../../components/ui";

export const LABEL_JENIS: Record<JenisLapus, string> = {
  kategori: "Kategori",
  sub: "Subkategori",
  daun: "Lapus (daun)",
  kelompok: "Kelompok publikasi",
  ntb: "NTB",
  top: "Pajak atas produk",
  sop: "Subsidi atas produk",
  topsop: "TOP − SOP",
  pdrb: "PDRB",
  pdrb_nonmigas: "PDRB tanpa migas",
};

type Mode = { jenis: "tambah"; induk: number | null } | { jenis: "ubah"; lapus: Lapus } | { jenis: "anggota"; lapus: Lapus } | null;

export function tebal(x: Pick<Lapus, "level" | "jenis">): boolean {
  return (x.level <= 1 && x.jenis !== "kelompok") || JENIS_TOTAL.has(x.jenis);
}

export function PratinjauTabelPokok({ daftar, tampilKelompok }: { daftar: Lapus[]; tampilKelompok: boolean }) {
  const baris = barisTerlihat(daftar, { tampilKelompok, hanyaAktif: true });
  return (
    <Panel judul="Pratinjau baris tabel pokok">
      <p className="mb-2 text-xs text-slate-500">Format tetap: urutan ini dipakai tabel pokok dan ekspor.</p>
      <ol aria-label="Pratinjau baris tabel pokok" className="max-h-[60vh] overflow-auto text-sm">
        {baris.map((x) => (
          <li key={x.id} className={`truncate py-0.5 ${tebal(x) ? "font-semibold" : ""} ${x.jenis === "kelompok" ? "italic text-merek-700" : ""}`}
            style={{ paddingLeft: `${Math.max(0, x.level - 1) * 14}px` }}>
            <span className="font-mono text-xs text-slate-500">{x.kode}</span> {x.nama}
          </li>
        ))}
      </ol>
    </Panel>
  );
}

function FormLapus({ mode, daftar, tdId, selesai }: { mode: Exclude<Mode, null | { jenis: "anggota" }>; daftar: Lapus[]; tdId: number; selesai: (teks?: string) => void }) {
  const lama = mode.jenis === "ubah" ? mode.lapus : null;
  const [kode, setKode] = useState(lama?.kode ?? "");
  const [nama, setNama] = useState(lama?.nama ?? "");
  const [jenis, setJenis] = useState<JenisLapus>(lama?.jenis ?? (mode.jenis === "tambah" && mode.induk ? "daun" : "kategori"));
  const [induk, setInduk] = useState<number | null>(lama ? lama.induk_id : mode.jenis === "tambah" ? mode.induk : null);
  const [sesudah, setSesudah] = useState<number | "">("");
  const [lkBps, setLkBps] = useState(lama?.kode_lk_bps ?? "");
  const [migas, setMigas] = useState(lama?.is_migas ?? false);
  const [aktif, setAktif] = useState(lama?.aktif ?? true);
  const aksi = useAksi([["lapus", tdId]]);
  const tanpaInduk = jenis === "kategori" || jenis === "kelompok" || JENIS_TOTAL.has(jenis);

  async function kirim(e: FormEvent) {
    e.preventDefault();
    const indukKirim = tanpaInduk ? null : induk;
    const r = lama
      ? await aksi.jalankan(() => api<Lapus>(`/api/lapus/${lama.id}`, { metode: "PATCH", isi: { kode, nama, jenis, induk_id: indukKirim, kode_lk_bps: lkBps || null, is_migas: migas, aktif } }))
      : await aksi.jalankan(() => api<Lapus>(`/api/tahun-dasar/${tdId}/lapus`, { metode: "POST", isi: { kode, nama, jenis, induk_id: indukKirim, sesudah_id: sesudah === "" ? null : sesudah, kode_lk_bps: lkBps || null, is_migas: migas } }));
    if (r) selesai(lama ? `${r.kode} tersimpan.` : `${r.kode} ditambahkan; tabel pokok mengikuti.`);
  }

  return (
    <Panel judul={lama ? `Ubah ${lama.kode}` : "Tambah lapus"} tutup={() => selesai()}>
      <form onSubmit={kirim} className="space-y-2">
        {aksi.pesan && <Pesan jenis={aksi.pesan.jenis}>{aksi.pesan.teks}</Pesan>}
        <div className="grid grid-cols-3 gap-2">
          <Isian label="Kode"><Masukan required value={kode} onChange={(e) => setKode(e.target.value)} placeholder="mis. C.2.23" /></Isian>
          <div className="col-span-2">
            <Isian label="Jenis">
              <Pilihan value={jenis} onChange={(e) => setJenis(e.target.value as JenisLapus)}>
                {(Object.keys(LABEL_JENIS) as JenisLapus[]).map((j) => <option key={j} value={j}>{LABEL_JENIS[j]}</option>)}
              </Pilihan>
            </Isian>
          </div>
        </div>
        <Isian label="Nama"><Masukan required value={nama} onChange={(e) => setNama(e.target.value)} /></Isian>
        {!tanpaInduk && (
          <Isian label="Induk">
            <Pilihan value={induk ?? ""} onChange={(e) => { setInduk(e.target.value ? Number(e.target.value) : null); setSesudah(""); }}>
              <option value="">(tanpa induk — baris utama)</option>
              {calonInduk(daftar, lama?.id).map((x) => <option key={x.id} value={x.id}>{x.kode} {x.nama}</option>)}
            </Pilihan>
          </Isian>
        )}
        {!lama && (
          <Isian label="Letakkan sesudah" petunjuk="Posisi di antara saudara; baris tabel pokok mengikuti.">
            <Pilihan value={sesudah} onChange={(e) => setSesudah(e.target.value ? Number(e.target.value) : "")}>
              <option value="">(paling akhir)</option>
              {saudara(daftar, tanpaInduk ? null : induk).map((x) => <option key={x.id} value={x.id}>{x.kode} {x.nama}</option>)}
            </Pilihan>
          </Isian>
        )}
        <div className="grid grid-cols-2 gap-2">
          <Isian label="Kode LK 02 BPS" petunjuk="Isi bila berbeda (mis. TUV.1)"><Masukan value={lkBps} onChange={(e) => setLkBps(e.target.value)} /></Isian>
          <div className="flex flex-col justify-center gap-1 pt-4">
            <Centang label="Migas" checked={migas} onChange={(e) => setMigas(e.target.checked)} />
            {lama && <Centang label="Aktif" checked={aktif} onChange={(e) => setAktif(e.target.checked)} />}
          </div>
        </div>
        <Tombol varian="utama" type="submit" disabled={aksi.sibuk}>Simpan</Tombol>
      </form>
    </Panel>
  );
}

function FormAnggota({ kelompok, daftar, tdId, selesai }: { kelompok: Lapus; daftar: Lapus[]; tdId: number; selesai: () => void }) {
  const [pilih, setPilih] = useState<Set<number>>(new Set(kelompok.anggota));
  const aksi = useAksi([["lapus", tdId]]);
  const calon = daftar.filter((x) => x.aktif && x.jenis !== "kelompok" && !JENIS_TOTAL.has(x.jenis));
  const ubah = (id: number, v: boolean) => setPilih((s) => { const n = new Set(s); if (v) n.add(id); else n.delete(id); return n; });
  return (
    <Panel judul={`Anggota kelompok ${kelompok.kode}`} tutup={selesai}>
      {aksi.pesan && <Pesan jenis={aksi.pesan.jenis}>{aksi.pesan.teks}</Pesan>}
      <p className="mb-2 text-xs text-slate-500">Kelompok = jumlah anggota; tidak punya item dan tidak menambah total.</p>
      <div className="mb-3 max-h-80 overflow-auto rounded border border-slate-200 p-2">
        {calon.map((x) => (
          <div key={x.id} style={{ paddingLeft: `${Math.max(0, x.level - 1) * 14}px` }}>
            <Centang label={`${x.kode} ${x.nama}`} checked={pilih.has(x.id)} onChange={(e) => ubah(x.id, e.target.checked)} />
          </div>
        ))}
      </div>
      <Tombol varian="utama" disabled={aksi.sibuk}
        onClick={() => aksi.jalankan(() => api(`/api/lapus/${kelompok.id}/anggota`, { metode: "PUT", isi: { anggota_ids: [...pilih] } }), "Anggota disimpan.")}>
        Simpan anggota
      </Tombol>
    </Panel>
  );
}

export function PohonLapus() {
  const { aktif: td } = useTahunDasar();
  const q = useDaftar<Lapus[]>(["lapus", td?.id], td ? `/api/tahun-dasar/${td.id}/lapus` : null);
  const aksi = useAksi([["lapus", td?.id]]);
  const [mode, setMode] = useState<Mode>(null);
  const [terlipat, setTerlipat] = useState<Set<number>>(new Set());
  const [tampilKelompok, setTampilKelompok] = useState(true);
  const [tampilNonaktif, setTampilNonaktif] = useState(true);
  const [diseret, setDiseret] = useState<Lapus | null>(null);
  const tutupForm = (teks?: string) => {
    setMode(null);
    if (teks) aksi.setPesan({ jenis: "ok", teks });
  };
  const daftar = useMemo(() => q.data ?? [], [q.data]);
  const baris = barisTerlihat(daftar, { terlipat, tampilKelompok, hanyaAktif: !tampilNonaktif });

  if (!td) return <p className="text-slate-500">Pilih tahun dasar di header.</p>;
  if (q.isLoading) return <p className="text-slate-500">Memuat pohon lapus…</p>;

  const atur = (induk: number | null, ids: number[] | null) =>
    ids && aksi.jalankan(() => api(`/api/tahun-dasar/${td.id}/lapus/urutan`, { metode: "PUT", isi: { induk_id: induk, anak: ids } }), "Urutan disimpan; tabel pokok mengikuti.");
  const idsSaudara = (x: Lapus) => saudara(daftar, x.induk_id).map((s) => s.id);
  const lipat = (id: number) => setTerlipat((s) => { const n = new Set(s); if (n.has(id)) n.delete(id); else n.add(id); return n; });

  async function hapus(x: Lapus) {
    if (!window.confirm(`Hapus ${x.kode} ${x.nama}?\nBila sudah dipakai data, lapus dinonaktifkan (riwayat tetap utuh).`)) return;
    await aksi.jalankan(() => api<HasilHapus>(`/api/lapus/${x.id}`, { metode: "DELETE" }), (r) => r.pesan);
  }

  return (
    <div className="grid gap-4 xl:grid-cols-[minmax(0,2fr)_minmax(320px,1fr)]">
      <div className="min-w-0 space-y-2">
        <div className="flex flex-wrap items-center gap-2">
          <Tombol varian="utama" onClick={() => setMode({ jenis: "tambah", induk: null })}>+ Lapus</Tombol>
          <Tombol onClick={() => setTerlipat(new Set(daftar.filter((x) => x.induk_id === null && punyaAnak(daftar, x.id)).map((x) => x.id)))}>Lipat semua</Tombol>
          <Tombol onClick={() => setTerlipat(new Set())}>Buka semua</Tombol>
          <Centang label="Kelompok publikasi" checked={tampilKelompok} onChange={(e) => setTampilKelompok(e.target.checked)} />
          <Centang label="Tampilkan nonaktif" checked={tampilNonaktif} onChange={(e) => setTampilNonaktif(e.target.checked)} />
          <span className="text-xs text-slate-500">Seret ⠿ atau ▲▼ untuk mengubah urutan antar-saudara.</span>
        </div>
        {aksi.pesan && <Pesan jenis={aksi.pesan.jenis}>{aksi.pesan.teks}</Pesan>}
        <div className="overflow-auto rounded border border-slate-200 bg-white">
          <table className={kelasTabel} aria-label="Pohon lapus">
            <thead>
              <tr>
                <th className={kelasTh} aria-label="Seret" />
                <th className={kelasTh}>Kode</th>
                <th className={kelasTh}>Nama</th>
                <th className={kelasTh}>Jenis</th>
                <th className={kelasTh}>LK 02</th>
                <th className={kelasTh}>Item</th>
                <th className={kelasTh}>Aksi</th>
              </tr>
            </thead>
            <tbody>
              {baris.map((x) => {
                const ids = idsSaudara(x);
                const bisaLepas = diseret !== null && diseret.id !== x.id && diseret.induk_id === x.induk_id;
                const anak = punyaAnak(daftar, x.id);
                return (
                  <tr key={x.id} data-kode={x.kode}
                    className={`${x.aktif ? "" : "text-slate-400"} ${bisaLepas ? "outline-dashed outline-1 outline-merek-500" : ""} hover:bg-slate-50`}
                    onDragOver={(e) => { if (bisaLepas) e.preventDefault(); }}
                    onDrop={(e) => { e.preventDefault(); if (diseret && bisaLepas) atur(x.induk_id, pindahKe(ids, diseret.id, x.id)); setDiseret(null); }}>
                    <td className={`${kelasTd} w-6 cursor-grab select-none text-slate-400`} draggable
                      onDragStart={(e) => { e.dataTransfer.effectAllowed = "move"; e.dataTransfer.setData("text/plain", String(x.id)); setDiseret(x); }}
                      onDragEnd={() => setDiseret(null)} title="Seret untuk mengubah urutan">⠿</td>
                    <td className={`${kelasTd} whitespace-nowrap font-mono text-xs`} style={{ paddingLeft: `${8 + Math.max(0, x.level - 1) * 16}px` }}>
                      {anak ? (
                        <button type="button" className="mr-1 w-4 text-slate-500" aria-label={terlipat.has(x.id) ? `Buka ${x.kode}` : `Lipat ${x.kode}`} onClick={() => lipat(x.id)}>
                          {terlipat.has(x.id) ? "▸" : "▾"}
                        </button>
                      ) : <span className="mr-1 inline-block w-4" />}
                      {x.kode}
                    </td>
                    <td className={`${kelasTd} ${tebal(x) ? "font-semibold" : ""} ${x.jenis === "kelompok" ? "italic" : ""}`}>
                      {x.nama} {x.is_migas && <Lencana warna="kuning">migas</Lencana>} {!x.aktif && <Lencana>nonaktif</Lencana>}
                    </td>
                    <td className={`${kelasTd} whitespace-nowrap text-xs`}>{LABEL_JENIS[x.jenis]}</td>
                    <td className={`${kelasTd} text-xs`}>{x.kode_lk_bps ?? ""}</td>
                    <td className={`${kelasTd} text-right text-xs`}>{x.jumlah_item || ""}</td>
                    <td className={`${kelasTd} whitespace-nowrap`}>
                      <Tombol kecil varian="teks" aria-label={`Naikkan ${x.kode}`} disabled={ids[0] === x.id} onClick={() => atur(x.induk_id, geser(ids, x.id, -1))}>▲</Tombol>
                      <Tombol kecil varian="teks" aria-label={`Turunkan ${x.kode}`} disabled={ids[ids.length - 1] === x.id} onClick={() => atur(x.induk_id, geser(ids, x.id, 1))}>▼</Tombol>
                      <Tombol kecil varian="teks" onClick={() => setMode({ jenis: "ubah", lapus: x })}>Ubah</Tombol>
                      {JENIS_INDUK.has(x.jenis) && <Tombol kecil varian="teks" onClick={() => setMode({ jenis: "tambah", induk: x.id })}>+ Sub</Tombol>}
                      {x.jenis === "kelompok" && <Tombol kecil varian="teks" onClick={() => setMode({ jenis: "anggota", lapus: x })}>Anggota</Tombol>}
                      <Tombol kecil varian="teks" className="text-red-700" onClick={() => hapus(x)}>Hapus</Tombol>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
      <div className="space-y-4">
        {mode && mode.jenis !== "anggota" && <FormLapus key={JSON.stringify(mode.jenis === "ubah" ? mode.lapus.id : mode)} mode={mode} daftar={daftar} tdId={td.id} selesai={tutupForm} />}
        {mode && mode.jenis === "anggota" && <FormAnggota key={mode.lapus.id} kelompok={mode.lapus} daftar={daftar} tdId={td.id} selesai={() => setMode(null)} />}
        <PratinjauTabelPokok daftar={daftar} tampilKelompok={tampilKelompok} />
      </div>
    </div>
  );
}
