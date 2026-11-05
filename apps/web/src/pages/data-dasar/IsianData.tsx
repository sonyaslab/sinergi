import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api, GalatApi } from "../../api/klien";
import type { Lapus } from "../../api/tipe";
import { GridDataDasar, type Tertunda } from "../../components/grid/GridDataDasar";
import { Centang, Isian, Lencana, Pesan, Pilihan, Tab, Tombol } from "../../components/ui";
import { indeksTemuan, labelPeriode, susunBaris, type BarisGrid, type DataGrid } from "../../lib/dataDasar";
import type { IsiSel } from "../../lib/tempel";
import type { Putaran } from "../DataDasar";
import { DialogKomoditas } from "./DialogKomoditas";
import { PanelItem } from "./PanelItem";

interface Props {
  putaran: Putaran;
  wilayah: string;
  lapus: Lapus[];
  akar: Lapus[];
}

export function IsianData({ putaran, wilayah, lapus, akar }: Props) {
  const qc = useQueryClient();
  const [kat, setKat] = useState<number | null>(null);
  const [sub, setSub] = useState<number | null>(null);
  const [hanyaAktif, setHanyaAktif] = useState(false);
  const [pesan, setPesan] = useState<{ jenis: "ok" | "galat" | "info"; teks: string } | null>(null);
  const [pilihan, setPilihan] = useState<BarisGrid | null>(null);
  const [tambah, setTambah] = useState(false);
  const [sibuk, setSibuk] = useState(false);
  const tertunda = useRef<Tertunda>(new Map());
  const [nTertunda, setNTertunda] = useState(0);

  useEffect(() => {
    if (akar.length && !akar.some((a) => a.id === kat)) setKat(akar[0].id);
  }, [akar, kat]);
  const anak = useMemo(() => lapus.filter((l) => l.aktif && l.induk_id === kat), [lapus, kat]);
  useEffect(() => setSub(null), [kat]);
  const target = sub ?? kat;
  const kunci = ["grid", putaran.id, wilayah, target];
  const q = useQuery({
    queryKey: kunci,
    queryFn: () => api<DataGrid>(`/api/data-dasar/grid?putaran_id=${putaran.id}&wilayah=${wilayah}&lapus_id=${target}`),
    enabled: target !== null,
  });
  const d = q.data;
  const [perKontribusi, setPerKontribusi] = useState<number>(putaran.akhir);
  useEffect(() => setPerKontribusi(putaran.akhir), [putaran.akhir]);

  // Hitung otomatis: pantau antrean sampai selesai, lalu segarkan grid (hasil, kontribusi, validasi).
  const berjalan = d?.antrean.berjalan ?? 0;
  useEffect(() => {
    if (!berjalan) return;
    const t = setInterval(async () => {
      const s = await api<DataGrid["antrean"]>(`/api/hitung/status?putaran_id=${putaran.id}&wilayah=${wilayah}`).catch(() => null);
      if (s && s.berjalan === 0) {
        clearInterval(t);
        qc.invalidateQueries({ queryKey: ["grid", putaran.id, wilayah] });
      }
    }, 2000);
    return () => clearInterval(t);
  }, [berjalan, putaran.id, wilayah, qc]);

  const baris = useMemo(() => (d ? susunBaris(d.item, hanyaAktif ? putaran.akhir : null) : []), [d, hanyaAktif, putaran.akhir]);
  const temuan = useMemo(() => indeksTemuan(d?.validasi ?? []), [d]);
  const terkunci = putaran.status === "terkunci";

  const ubah = useCallback((b: BarisGrid, u: number, isi: IsiSel) => {
    tertunda.current.set(`${b.item.id}:${b.seri.kode}:${u}`, isi);
    setNTertunda(tertunda.current.size);
  }, []);

  function batal() {
    tertunda.current = new Map();
    setNTertunda(0);
    qc.invalidateQueries({ queryKey: kunci });
  }

  async function simpan() {
    const perubahan = [...tertunda.current.entries()].map(([k, isi]) => {
      const [item, seri, u] = k.split(":");
      return { item_id: Number(item), seri, periode: Number(u), nilai: isi.jenis === "angka" ? isi.nilai : null,
        tidak_tersedia: isi.jenis === "tidak_tersedia" };
    });
    setSibuk(true);
    setPesan(null);
    try {
      const r = await api<{ pesan: string }>("/api/data-dasar/nilai", { metode: "PUT", isi: { putaran_id: putaran.id, perubahan } });
      tertunda.current = new Map();
      setNTertunda(0);
      setPesan({ jenis: "ok", teks: r.pesan });
      await qc.invalidateQueries({ queryKey: ["grid", putaran.id, wilayah] });
    } catch (e) {
      setPesan({ jenis: "galat", teks: e instanceof GalatApi ? e.message : "Gagal menyimpan." });
    } finally {
      setSibuk(false);
    }
  }

  const ubahJangkar = useCallback(async (b: BarisGrid, nilai: number | null) => {
    const kode = b.seri.jangkar?.kode;
    if (!kode) return;
    let alasan: string | null = null;
    if ((kode === "H_TD" || kode === "IH_TD") && nilai !== null) {
      alasan = window.prompt(`Alasan jangkar pengganti ${kode} (min. 10 karakter):`, b.seri.jangkar?.alasan ?? "");
      if (alasan === null) return;
    }
    try {
      await api("/api/data-dasar/parameter", { metode: "PUT", isi: { putaran_id: putaran.id, item_id: b.item.id, kode, nilai, alasan } });
      setPesan({ jenis: "ok", teks: `Jangkar ${kode} tersimpan. Hitung ulang berjalan.` });
      qc.invalidateQueries({ queryKey: ["grid", putaran.id, wilayah] });
    } catch (e) {
      setPesan({ jenis: "galat", teks: e instanceof GalatApi ? e.message : "Gagal menyimpan jangkar." });
    }
  }, [putaran.id, wilayah, qc]);

  async function hitungUlang() {
    await api("/api/hitung", { metode: "POST", isi: { putaran_id: putaran.id, wilayah } }).catch(() => null);
    qc.invalidateQueries({ queryKey: ["grid", putaran.id, wilayah] });
  }

  const tabSub = [{ kunci: "semua", label: "Semua" }, ...anak.map((a) => ({ kunci: String(a.id), label: a.kode }))];
  const lapusBerdata = (d?.lapus ?? []).filter((l) => ["daun", "top", "sop"].includes(l.jenis) && l.boleh_tulis);
  const blokir = (d?.validasi ?? []).filter((t) => t.tingkat === "blokir_ajukan" && !t.dikonfirmasi).length;

  return (
    <div>
      <div className="mb-2 flex flex-wrap items-end gap-3">
        <div className="w-72">
          <Isian label="Kategori">
            <Pilihan value={kat ?? ""} onChange={(e) => setKat(Number(e.target.value))} aria-label="Kategori">
              {akar.map((a) => <option key={a.id} value={a.id}>{a.kode} — {a.nama}</option>)}
            </Pilihan>
          </Isian>
        </div>
        <div className="w-44">
          <Isian label="Kontribusi pada">
            <Pilihan value={perKontribusi} onChange={(e) => setPerKontribusi(Number(e.target.value))} aria-label="Periode kontribusi">
              {(d?.periode ?? []).slice().reverse().map((p) => <option key={p.urut} value={p.urut}>{p.label}</option>)}
            </Pilihan>
          </Isian>
        </div>
        <Centang label={`Hanya item aktif di ${labelPeriode(putaran.akhir)}`} checked={hanyaAktif} onChange={(e) => setHanyaAktif(e.target.checked)} />
      </div>
      {anak.length > 0 && <Tab daftar={tabSub} aktif={sub === null ? "semua" : String(sub)} ubah={(k) => setSub(k === "semua" ? null : Number(k))} />}
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <Tombol varian="utama" disabled={!nTertunda || sibuk || terkunci} onClick={simpan}>Simpan perubahan{nTertunda ? ` (${nTertunda})` : ""}</Tombol>
        <Tombol disabled={!nTertunda || sibuk} onClick={batal}>Batalkan</Tombol>
        <Tombol disabled={terkunci || !lapusBerdata.length} onClick={() => setTambah(true)}>+ Komoditas</Tombol>
        <Tombol onClick={hitungUlang} disabled={terkunci}>Hitung ulang</Tombol>
        <span className="text-xs text-slate-500">
          {berjalan ? "Menghitung…" : d?.antrean.terakhir ? `Hitung terakhir: ${d.antrean.terakhir.status}` : ""}
        </span>
        {blokir > 0 && <Lencana warna="merah">{blokir} temuan blokir ajukan</Lencana>}
        {terkunci && <Lencana warna="abu">Putaran terkunci (baca saja)</Lencana>}
        <span className="ml-auto text-xs text-slate-500">Ctrl+V menempel dari Excel mulai sel aktif · "-" = tidak tersedia · kosong ≠ 0</span>
      </div>
      {pesan && <div className="mb-2"><Pesan jenis={pesan.jenis}>{pesan.teks}</Pesan></div>}
      {d?.antrean.terakhir?.status === "gagal" && <div className="mb-2"><Pesan jenis="galat">Hitung gagal: {d.antrean.terakhir.pesan}</Pesan></div>}
      {q.isLoading && <p className="text-sm text-slate-500">Memuat data…</p>}
      {q.isError && <Pesan jenis="galat">{q.error instanceof GalatApi ? q.error.message : "Gagal memuat data."}</Pesan>}
      {d && (
        <div className="grid gap-3 2xl:grid-cols-[1fr_320px]">
          <div>
            {baris.length === 0 && <p className="mb-2 text-sm text-slate-500">Belum ada komoditas pada pilihan ini. Gunakan + Komoditas atau impor templat.</p>}
            <GridDataDasar baris={baris} periode={d.periode} terkunci={terkunci} temuan={temuan} tertunda={tertunda.current}
              periodeKontribusi={perKontribusi} ubah={ubah} ubahJangkar={ubahJangkar} pilih={setPilihan}
              galat={(t) => setPesan({ jenis: "galat", teks: t })} info={(t) => setPesan({ jenis: "info", teks: t })} />
          </div>
          <PanelItem baris={pilihan} data={d} putaran={putaran} wilayah={wilayah} lapus={lapus}
            segarkan={() => qc.invalidateQueries({ queryKey: ["grid", putaran.id, wilayah] })} />
        </div>
      )}
      {tambah && d && (
        <DialogKomoditas putaran={putaran} wilayah={wilayah} lapus={lapusBerdata} tutup={() => setTambah(false)}
          selesai={(t) => {
            setTambah(false);
            setPesan({ jenis: "ok", teks: t });
            qc.invalidateQueries({ queryKey: ["grid", putaran.id, wilayah] });
          }} />
      )}
    </div>
  );
}
