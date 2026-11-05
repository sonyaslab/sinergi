import { useState, type FormEvent } from "react";
import { api, GalatApi } from "../../api/klien";
import { useDaftar } from "../../api/hooks";
import type { Lapus } from "../../api/tipe";
import { Dialog } from "../../components/Dialog";
import { Isian, Lencana, Masukan, Panel, Pesan, Pilihan, Tombol } from "../../components/ui";
import { labelPeriode, LABEL_TINGKAT, type BarisGrid, type DataGrid, type ItemGrid, type Temuan } from "../../lib/dataDasar";
import { formatAngka } from "../../lib/tempel";
import type { Putaran } from "../DataDasar";

interface Props {
  baris: BarisGrid | null;
  data: DataGrid;
  putaran: Putaran;
  wilayah: string;
  lapus: Lapus[];
  segarkan: () => void;
}

type Mode = "ubah" | "sambung" | "tautan" | "seri" | null;
const RUMUS: Record<string, [string, string]> = {
  TPK_X_KAMAR: ["REV", "KUANTUM"], JANGKAR_X_IH_100: ["REV", "HARGA"], KAPITA_X_PENDUDUK_X_3: ["DEF", "OUT_ADHB"],
  MARGIN_X_OUTPUT: ["DEF", "OUT_ADHB"], MARGIN_X_IMPOR: ["DEF", "OUT_ADHB"],
};

/** Panel item terpilih: info, temuan validasi (konfirmasi), Ubah/Nonaktifkan, Sambungkan, Tautan seri. */
export function PanelItem({ baris, data, putaran, wilayah, lapus, segarkan }: Props) {
  const [mode, setMode] = useState<Mode>(null);
  const [pesan, setPesan] = useState<{ jenis: "ok" | "galat"; teks: string } | null>(null);
  const terkunci = putaran.status === "terkunci";
  const temuanLapus = data.validasi.filter((t) => t.item_id === null);
  if (!baris) {
    return (
      <Panel judul="Temuan lapus">
        <DaftarTemuan ts={temuanLapus} putaran={putaran} wilayah={wilayah} segarkan={segarkan} />
        <p className="mt-2 text-xs text-slate-500">Klik sel grid untuk melihat rincian item.</p>
      </Panel>
    );
  }
  const it = baris.item;
  const ts = data.validasi.filter((t) => t.item_id === it.id);
  return (
    <Panel judul={`${it.metode} ${it.nomor} · ${it.nama}`}>
      <dl className="mb-2 grid grid-cols-[110px_1fr] gap-x-2 text-xs">
        <dt className="text-slate-500">Lapus</dt><dd>{it.kode_lapus}</dd>
        <dt className="text-slate-500">Status</dt><dd>{it.status}{it.jenis_indeks ? ` · indeks ${it.jenis_indeks}` : ""}</dd>
        <dt className="text-slate-500">Berlaku</dt>
        <dd>{it.mulai !== null ? labelPeriode(it.mulai) : "awal seri"} – {it.selesai !== null ? labelPeriode(it.selesai) : "sekarang"}</dd>
        {it.item_asal_id && (<><dt className="text-slate-500">Sambungan dari</dt><dd>item #{it.item_asal_id}</dd></>)}
        <dt className="text-slate-500">Seri terpilih</dt><dd>{baris.seri.kode}{baris.seri.tautan ? ` · ${baris.seri.tautan.teks}` : ""}</dd>
      </dl>
      {it.boleh_tulis && !terkunci && (
        <div className="mb-2 flex flex-wrap gap-1">
          <Tombol kecil onClick={() => setMode("ubah")}>Ubah / Nonaktifkan</Tombol>
          <Tombol kecil onClick={() => setMode("sambung")}>Sambungkan</Tombol>
          <Tombol kecil onClick={() => setMode("tautan")}>Tautan seri</Tombol>
          <Tombol kecil onClick={() => setMode("seri")}>Baris seri</Tombol>
        </div>
      )}
      {pesan && <div className="mb-2"><Pesan jenis={pesan.jenis}>{pesan.teks}</Pesan></div>}
      <h3 className="mb-1 text-xs font-semibold text-slate-600">Temuan validasi item</h3>
      <DaftarTemuan ts={ts} putaran={putaran} wilayah={wilayah} segarkan={segarkan} />
      {mode === "ubah" && <DialogUbah it={it} putaran={putaran} tutup={() => setMode(null)} selesai={(t) => { setMode(null); setPesan({ jenis: "ok", teks: t }); segarkan(); }} />}
      {mode === "sambung" && <DialogSambung it={it} data={data} putaran={putaran} tutup={() => setMode(null)} selesai={(t) => { setMode(null); setPesan({ jenis: "ok", teks: t }); segarkan(); }} />}
      {mode === "tautan" && <DialogTautan b={baris} putaran={putaran} wilayah={wilayah} lapus={lapus} tutup={() => setMode(null)} selesai={(t) => { setMode(null); setPesan({ jenis: "ok", teks: t }); segarkan(); }} />}
      {mode === "seri" && <DialogSeri it={it} putaran={putaran} tutup={() => setMode(null)} selesai={(t) => { setMode(null); setPesan({ jenis: "ok", teks: t }); segarkan(); }} />}
    </Panel>
  );
}

function warna(t: Temuan["tingkat"]): "merah" | "kuning" | "biru" | "abu" {
  return t.startsWith("blokir") ? "merah" : t === "peringatan" ? "kuning" : "biru";
}

export function DaftarTemuan({ ts, putaran, wilayah, segarkan }: { ts: Temuan[]; putaran: Putaran; wilayah: string; segarkan: () => void }) {
  const [galat, setGalat] = useState<string | null>(null);
  if (!ts.length) return <p className="text-xs text-slate-500">Tidak ada temuan.</p>;
  async function konfirmasi(t: Temuan) {
    const alasan = window.prompt("Alasan konfirmasi (min. 10 karakter):");
    if (!alasan) return;
    try {
      await api("/api/validasi/konfirmasi", { metode: "POST", isi: { putaran_id: putaran.id, wilayah, lapus_id: t.lapus_id, kode: t.kode, kunci: t.kunci, alasan } });
      segarkan();
    } catch (e) {
      setGalat(e instanceof GalatApi ? e.message : "Gagal mengonfirmasi.");
    }
  }
  return (
    <ul className="max-h-64 space-y-1 overflow-auto text-xs">
      {galat && <li><Pesan jenis="galat">{galat}</Pesan></li>}
      {ts.map((t, i) => (
        <li key={`${t.kode}-${t.kunci}-${i}`} className="rounded border border-slate-100 p-1">
          <Lencana warna={t.dikonfirmasi ? "hijau" : warna(t.tingkat)}>{t.kode} · {t.dikonfirmasi ? "dikonfirmasi" : LABEL_TINGKAT[t.tingkat]}</Lencana>{" "}
          {t.pesan}
          {t.alasan_konfirmasi && <div className="text-slate-500">Alasan: {t.alasan_konfirmasi}</div>}
          {t.kode === "V05" && !t.dikonfirmasi && <Tombol kecil varian="teks" onClick={() => konfirmasi(t)}>Konfirmasi</Tombol>}
        </li>
      ))}
    </ul>
  );
}

function periodeDari(p: Putaran): number[] {
  const out: number[] = [];
  for (let u = p.awal; u <= p.akhir; u++) out.push(u);
  return out;
}

function DialogUbah({ it, putaran, tutup, selesai }: { it: ItemGrid; putaran: Putaran; tutup: () => void; selesai: (t: string) => void }) {
  const [nama, setNama] = useState(it.nama);
  const [status, setStatus] = useState(it.status);
  const [mulai, setMulai] = useState(it.mulai === null ? "" : String(it.mulai));
  const [sampai, setSampai] = useState(it.selesai === null ? "" : String(it.selesai));
  const [jenis, setJenis] = useState(it.jenis_indeks ?? "IP");
  const [alasan, setAlasan] = useState("");
  const [galat, setGalat] = useState<string | null>(null);
  const per = periodeDari(putaran);
  async function kirim(e: FormEvent) {
    e.preventDefault();
    const isi: Record<string, unknown> = { putaran_id: putaran.id, alasan };
    if (nama.trim() !== it.nama) isi.nama = nama.trim();
    if (status !== it.status) isi.status = status;
    if ((mulai ? Number(mulai) : null) !== it.mulai) isi.mulai = mulai ? Number(mulai) : null;
    if ((sampai ? Number(sampai) : null) !== it.selesai) isi.selesai = sampai ? Number(sampai) : null;
    if (it.metode === "EKS" && jenis !== it.jenis_indeks) isi.jenis_indeks = jenis;
    try {
      const r = await api<{ pesan: string }>(`/api/data-dasar/item/${it.id}`, { metode: "PATCH", isi });
      selesai(r.pesan);
    } catch (err) {
      setGalat(err instanceof GalatApi ? err.message : "Gagal menyimpan.");
    }
  }
  return (
    <Dialog judul={`Ubah item ${it.metode} ${it.nomor}`} tutup={tutup}>
      <form onSubmit={kirim} className="grid gap-2">
        <Isian label="Nama"><Masukan value={nama} onChange={(e) => setNama(e.target.value)} required /></Isian>
        <div className="grid grid-cols-2 gap-2">
          <Isian label="Status" petunjuk="Nonaktif tidak menghapus riwayat; nilai tetap dihitung sesuai masa berlaku.">
            <Pilihan value={status} onChange={(e) => setStatus(e.target.value as "aktif" | "nonaktif")} aria-label="Status">
              <option value="aktif">Aktif</option>
              <option value="nonaktif">Nonaktif</option>
            </Pilihan>
          </Isian>
          {it.metode === "EKS" && (
            <Isian label="Jenis indeks">
              <Pilihan value={jenis} onChange={(e) => setJenis(e.target.value as "IP" | "IB")} aria-label="Jenis indeks">
                <option value="IP">IP</option><option value="IB">IB</option>
              </Pilihan>
            </Isian>
          )}
          <Isian label="Berlaku mulai">
            <Pilihan value={mulai} onChange={(e) => setMulai(e.target.value)} aria-label="Berlaku mulai">
              <option value="">awal seri</option>
              {per.map((u) => <option key={u} value={u}>{labelPeriode(u)}</option>)}
            </Pilihan>
          </Isian>
          <Isian label="Berlaku sampai">
            <Pilihan value={sampai} onChange={(e) => setSampai(e.target.value)} aria-label="Berlaku sampai">
              <option value="">masih berlaku</option>
              {per.map((u) => <option key={u} value={u}>{labelPeriode(u)}</option>)}
            </Pilihan>
          </Isian>
        </div>
        <Isian label="Alasan" petunjuk="Wajib, min. 10 karakter."><Masukan value={alasan} onChange={(e) => setAlasan(e.target.value)} required minLength={10} /></Isian>
        {galat && <Pesan jenis="galat">{galat}</Pesan>}
        <div className="flex justify-end gap-2">
          <Tombol onClick={tutup}>Batal</Tombol>
          <Tombol varian="utama" type="submit" disabled={alasan.trim().length < 10}>Simpan</Tombol>
        </div>
      </form>
    </Dialog>
  );
}

interface Usulan { kode: string; nilai: number; overlap: string[]; dasar: string }
interface HasilSambung { pesan: string; usulan: Usulan[]; catatan: string[]; overlap: string[] }

function DialogSambung({ it, data, putaran, tutup, selesai }: { it: ItemGrid; data: DataGrid; putaran: Putaran; tutup: () => void; selesai: (t: string) => void }) {
  const calon = data.item.filter((x) => x.id !== it.id);
  const [penerus, setPenerus] = useState(calon[0]?.id ?? 0);
  const [alasan, setAlasan] = useState("");
  const [hasil, setHasil] = useState<HasilSambung | null>(null);
  const [galat, setGalat] = useState<string | null>(null);
  const [disimpan, setDisimpan] = useState<string[]>([]);
  async function sambung(e: FormEvent) {
    e.preventDefault();
    try {
      setHasil(await api<HasilSambung>(`/api/data-dasar/item/${it.id}/sambung`, {
        metode: "POST", isi: { putaran_id: putaran.id, penerus_id: penerus, alasan } }));
    } catch (err) {
      setGalat(err instanceof GalatApi ? err.message : "Gagal menyambung.");
    }
  }
  async function simpanUsulan(u: Usulan) {
    try {
      await api("/api/data-dasar/parameter", { metode: "PUT", isi: { putaran_id: putaran.id, item_id: it.id, kode: u.kode, nilai: u.nilai,
        alasan: `Usulan dari overlap dengan item penerus #${penerus} (${u.dasar})`.slice(0, 500) } });
      setDisimpan((x) => [...x, u.kode]);
    } catch (err) {
      setGalat(err instanceof GalatApi ? err.message : "Gagal menyimpan jangkar.");
    }
  }
  return (
    <Dialog judul={`Sambungkan ${it.nama} ke item penerus`} tutup={tutup} lebar="max-w-xl">
      {!hasil ? (
        <form onSubmit={sambung} className="grid gap-2">
          <Isian label="Item penerus" petunjuk="Overlap minimal satu tahun dianjurkan (docs/04 §3).">
            <Pilihan value={penerus} onChange={(e) => setPenerus(Number(e.target.value))} aria-label="Item penerus">
              {calon.map((x) => <option key={x.id} value={x.id}>{x.kode_lapus} {x.metode} {x.nomor} — {x.nama}</option>)}
            </Pilihan>
          </Isian>
          <Isian label="Alasan"><Masukan value={alasan} onChange={(e) => setAlasan(e.target.value)} required minLength={10} /></Isian>
          {galat && <Pesan jenis="galat">{galat}</Pesan>}
          <div className="flex justify-end gap-2">
            <Tombol onClick={tutup}>Batal</Tombol>
            <Tombol varian="utama" type="submit" disabled={!penerus || alasan.trim().length < 10}>Sambungkan</Tombol>
          </div>
        </form>
      ) : (
        <div className="grid gap-2 text-sm">
          <Pesan jenis="info">{hasil.pesan}</Pesan>
          {hasil.catatan.map((c) => <p key={c} className="text-xs text-amber-700">{c}</p>)}
          <p className="text-xs text-slate-500">Overlap: {hasil.overlap.length ? hasil.overlap.join(", ") : "tidak ada"}</p>
          {hasil.usulan.length === 0 && <p>Tidak ada usulan jangkar otomatis; isi jangkar secara manual di kolom Jangkar.</p>}
          {hasil.usulan.map((u) => (
            <div key={u.kode} className="flex items-center justify-between rounded border border-slate-200 p-2">
              <div><b>{u.kode}</b> = {formatAngka(u.nilai)} <div className="text-xs text-slate-500">{u.dasar}</div></div>
              {disimpan.includes(u.kode) ? <Lencana warna="hijau">tersimpan</Lencana> : <Tombol kecil onClick={() => simpanUsulan(u)}>Simpan sebagai jangkar</Tombol>}
            </div>
          ))}
          {galat && <Pesan jenis="galat">{galat}</Pesan>}
          <div className="flex justify-end"><Tombol varian="utama" onClick={() => selesai("Item disambungkan.")}>Selesai</Tombol></div>
        </div>
      )}
    </Dialog>
  );
}

interface SeriRef { id: number; kode: string; nama: string }

function DialogTautan({ b, putaran, wilayah, lapus, tutup, selesai }: { b: BarisGrid; putaran: Putaran; wilayah: string; lapus: Lapus[]; tutup: () => void; selesai: (t: string) => void }) {
  const t = b.seri.tautan;
  const [sumber, setSumber] = useState<string>(t?.sumber ?? "");
  const [seriId, setSeriId] = useState<number | "">(t?.seri_id ?? "");
  const [rumus, setRumus] = useState(t?.rumus ?? "");
  const [lapusIds, setLapusIds] = useState<number[]>(t?.lapus_sumber_ids ?? []);
  const [besaran, setBesaran] = useState(t?.besaran ?? "OUT_CP");
  const [faktor, setFaktor] = useState(String(t?.faktor ?? 1));
  const [galat, setGalat] = useState<string | null>(null);
  const seriRef = useDaftar<{ seri: SeriRef[] }>(["seri-ref-daftar"], `/api/seri-referensi?wilayah=${wilayah}`).data?.seri ?? [];
  const rumusBoleh = Object.entries(RUMUS).filter(([, [m, s]]) => m === b.item.metode && s === b.seri.kode).map(([k]) => k);
  const sumberLapus = lapus.filter((l) => l.aktif && ["daun", "sub", "kategori", "kelompok"].includes(l.jenis));
  const butuhLapus = sumber === "HASIL_LAPUS" || rumus === "MARGIN_X_OUTPUT";
  async function kirim(e: FormEvent) {
    e.preventDefault();
    try {
      const r = await api<{ pesan: string }>(`/api/data-dasar/item/${b.item.id}/tautan`, { metode: "PUT", isi: {
        putaran_id: putaran.id, jenis_seri: b.seri.kode, sumber: sumber || null, rumus: rumus || null,
        seri_id: seriId === "" ? null : seriId, lapus_sumber_ids: butuhLapus ? lapusIds : null,
        besaran: sumber === "HASIL_LAPUS" ? besaran : null, faktor: Number(faktor.replace(",", ".")) || 1 } });
      selesai(r.pesan);
    } catch (err) {
      setGalat(err instanceof GalatApi ? err.message : "Gagal menyimpan tautan.");
    }
  }
  return (
    <Dialog judul={`Tautan seri ${b.seri.kode} — ${b.item.nama}`} tutup={tutup}>
      <form onSubmit={kirim} className="grid gap-2">
        <Isian label="Sumber" petunjuk="Seri tertaut dihitung sistem dan menggantikan isian manual.">
          <Pilihan value={sumber} onChange={(e) => setSumber(e.target.value)} aria-label="Sumber tautan">
            <option value="">Tidak tertaut (isian manual)</option>
            <option value="SERI_REFERENSI">Seri referensi bersama</option>
            <option value="HASIL_LAPUS">Hasil lapus lain (BENC)</option>
            {rumusBoleh.length > 0 && <option value="RUMUS">Rumus baku</option>}
          </Pilihan>
        </Isian>
        {sumber === "SERI_REFERENSI" && (
          <Isian label="Seri referensi">
            <Pilihan value={seriId} onChange={(e) => setSeriId(Number(e.target.value))} aria-label="Seri referensi" required>
              <option value="">—</option>
              {seriRef.map((s) => <option key={s.id} value={s.id}>{s.kode} — {s.nama}</option>)}
            </Pilihan>
          </Isian>
        )}
        {sumber === "RUMUS" && (
          <Isian label="Rumus">
            <Pilihan value={rumus} onChange={(e) => setRumus(e.target.value)} aria-label="Rumus" required>
              <option value="">—</option>
              {rumusBoleh.map((r) => <option key={r} value={r}>{r}</option>)}
            </Pilihan>
          </Isian>
        )}
        {sumber === "HASIL_LAPUS" && (
          <Isian label="Besaran">
            <Pilihan value={besaran} onChange={(e) => setBesaran(e.target.value)} aria-label="Besaran">
              {["OUT_CP", "OUT_K", "GVA_CP", "GVA_K", "IMPLISIT_OUT"].map((x) => <option key={x}>{x}</option>)}
            </Pilihan>
          </Isian>
        )}
        {(butuhLapus && (sumber === "HASIL_LAPUS" || sumber === "RUMUS")) && (
          <Isian label="Lapus sumber" petunjuk="Ctrl/Cmd+klik untuk memilih beberapa.">
            <select multiple className="h-32 w-full rounded border border-slate-300 text-sm" aria-label="Lapus sumber"
              value={lapusIds.map(String)} onChange={(e) => setLapusIds([...e.target.selectedOptions].map((o) => Number(o.value)))}>
              {sumberLapus.map((l) => <option key={l.id} value={l.id}>{l.kode} — {l.nama}</option>)}
            </select>
          </Isian>
        )}
        {sumber && <Isian label="Faktor" petunjuk="Pengali hasil tautan (bawaan 1)."><Masukan value={faktor} onChange={(e) => setFaktor(e.target.value)} inputMode="decimal" /></Isian>}
        {galat && <Pesan jenis="galat">{galat}</Pesan>}
        <div className="flex justify-end gap-2">
          <Tombol onClick={tutup}>Batal</Tombol>
          <Tombol varian="utama" type="submit">Simpan</Tombol>
        </div>
      </form>
    </Dialog>
  );
}

const SERI_METODE: Record<string, string[]> = {
  REV: ["KUANTUM", "HARGA", "IH", "RKA", "TPK", "KAMAR"],
  EKS: ["INDEKS", "IH", "BASE_ADHB", "BASE_ADHK", "RKA"],
  DEF: ["OUT_ADHB", "NTB_ADHB", "IH", "RKA", "NILAI_KAPITA", "PENDUDUK", "VOLUME", "V_IMPOR", "R_MARGIN", "KURS"],
  PDK: ["NILAI"],
};

function DialogSeri({ it, putaran, tutup, selesai }: { it: ItemGrid; putaran: Putaran; tutup: () => void; selesai: (t: string) => void }) {
  const [pilih, setPilih] = useState<string[]>(it.seri.map((s) => s.kode));
  const [galat, setGalat] = useState<string | null>(null);
  const semua = SERI_METODE[it.metode] ?? [];
  async function kirim() {
    try {
      const urut = [...it.seri.map((s) => s.kode).filter((k) => pilih.includes(k)), ...semua.filter((k) => pilih.includes(k) && !it.seri.some((s) => s.kode === k))];
      const r = await api<{ pesan: string }>(`/api/data-dasar/item/${it.id}/seri`, { metode: "PUT", isi: { putaran_id: putaran.id, seri: urut } });
      selesai(r.pesan);
    } catch (err) {
      setGalat(err instanceof GalatApi ? err.message : "Gagal menyimpan.");
    }
  }
  return (
    <Dialog judul={`Baris seri ${it.metode} ${it.nomor}`} tutup={tutup}>
      <p className="mb-2 text-xs text-slate-500">Tambah seri komponen (mis. TPK dan KAMAR untuk rumus hotel). Menyembunyikan baris tidak menghapus nilai.</p>
      <div className="mb-3 grid grid-cols-2 gap-1 text-sm">
        {semua.map((k) => (
          <label key={k} className="inline-flex items-center gap-1.5">
            <input type="checkbox" checked={pilih.includes(k)} onChange={(e) => setPilih((x) => (e.target.checked ? [...x, k] : x.filter((y) => y !== k)))} />
            {k}
          </label>
        ))}
      </div>
      {galat && <Pesan jenis="galat">{galat}</Pesan>}
      <div className="flex justify-end gap-2">
        <Tombol onClick={tutup}>Batal</Tombol>
        <Tombol varian="utama" onClick={kirim} disabled={!pilih.length}>Simpan</Tombol>
      </div>
    </Dialog>
  );
}
