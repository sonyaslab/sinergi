import { useMemo, useState, type FormEvent } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { AgGridReact } from "ag-grid-react";
import type { ColDef, ColGroupDef, ValueSetterParams } from "ag-grid-community";
import "ag-grid-community/styles/ag-grid.css";
import "ag-grid-community/styles/ag-theme-quartz.css";
import { api, GalatApi } from "../../api/klien";
import { TEKS_GRID } from "../../components/grid/GridDataDasar";
import { Dialog } from "../../components/Dialog";
import { Isian, Masukan, Pesan, Pilihan, Tombol } from "../../components/ui";
import { grupTahun, type Periode } from "../../lib/dataDasar";
import { formatAngka, uraiAngka } from "../../lib/tempel";
import type { Putaran } from "../DataDasar";

interface Seri {
  id: number;
  kode: string;
  nama: string;
  jenis: string;
  satuan: string | null;
  keterangan: string | null;
  lapus_pemilik: string | null;
  jumlah_tautan: number;
  boleh_tulis: boolean;
  nilai: Record<string, number>;
}

/** Seri referensi bersama (IHK, IHPB, upah, implisit PMTB, IBS/IMK agregat): diisi sekali, ditautkan ke banyak item. */
export function SeriReferensi({ putaran, wilayah }: { putaran: Putaran; wilayah: string }) {
  const qc = useQueryClient();
  const kunci = ["seri-ref", putaran.id, wilayah];
  const q = useQuery({ queryKey: kunci, queryFn: () => api<{ seri: Seri[]; periode: Periode[] }>(`/api/seri-referensi?putaran_id=${putaran.id}&wilayah=${wilayah}`) });
  const [ubah, setUbah] = useState<Map<string, number | null>>(new Map());
  const [pesan, setPesan] = useState<{ jenis: "ok" | "galat"; teks: string } | null>(null);
  const [baru, setBaru] = useState(false);
  const terkunci = putaran.status === "terkunci";
  const periode = useMemo(() => q.data?.periode ?? [], [q.data]);

  const kolom = useMemo<(ColDef<Seri> | ColGroupDef<Seri>)[]>(() => [
    { field: "kode", headerName: "Kode", pinned: "left", width: 170 },
    { field: "nama", headerName: "Nama", pinned: "left", width: 200, tooltipField: "nama" },
    { field: "satuan", headerName: "Satuan", width: 90 },
    { headerName: "Dipakai", width: 80, valueGetter: (x) => x.data?.jumlah_tautan ?? 0, headerTooltip: "Jumlah tautan item" },
    { field: "lapus_pemilik", headerName: "Pemilik", width: 80, headerTooltip: "Lapus pemilik (operatornya boleh mengisi)" },
    ...grupTahun(periode).map((g): ColGroupDef<Seri> => ({
      headerName: String(g.tahun), openByDefault: g.terbuka,
      children: [...g.periode.map((pe): ColDef<Seri> => ({
        colId: `p_${pe.urut}`, headerName: `T${(pe.urut % 4) + 1}`, width: 88, type: "rightAligned",
        columnGroupShow: "open",
        valueGetter: (x) => {
          const k = `${x.data?.id}:${pe.urut}`;
          return ubah.has(k) ? ubah.get(k) : x.data?.nilai[String(pe.urut)] ?? null;
        },
        valueFormatter: (x) => formatAngka(x.value as number | null),
        editable: (x) => Boolean(x.data?.boleh_tulis) && !terkunci,
        cellClass: (x) => (x.data?.boleh_tulis && !terkunci ? "sel-isian" : "sel-kunci") + (ubah.has(`${x.data?.id}:${pe.urut}`) ? " sel-ubah" : ""),
        valueSetter: (x: ValueSetterParams<Seri>) => {
          const isi = uraiAngka(String(x.newValue ?? ""));
          if (isi.jenis === "galat" || isi.jenis === "tidak_tersedia" || !x.data) {
            setPesan({ jenis: "galat", teks: "Isi angka atau kosongkan." });
            return false;
          }
          setUbah((m) => new Map(m).set(`${x.data?.id}:${pe.urut}`, isi.jenis === "angka" ? isi.nilai : null));
          return true;
        },
      })), {
        colId: `r${g.tahun}`, headerName: "Terisi", width: 64, columnGroupShow: "closed", cellClass: "sel-kunci",
        valueGetter: (x) => `${g.periode.filter((pe) => x.data?.nilai[String(pe.urut)] !== undefined).length}/${g.periode.length}`,
      }],
    })),
  ], [periode, ubah, terkunci]);

  async function simpan() {
    try {
      const perubahan = [...ubah.entries()].map(([k, nilai]) => ({ seri_id: Number(k.split(":")[0]), periode: Number(k.split(":")[1]), nilai }));
      const r = await api<{ pesan: string }>("/api/seri-referensi/nilai", { metode: "PUT", isi: { putaran_id: putaran.id, wilayah, perubahan } });
      setUbah(new Map());
      setPesan({ jenis: "ok", teks: r.pesan });
      qc.invalidateQueries({ queryKey: kunci });
    } catch (e) {
      setPesan({ jenis: "galat", teks: e instanceof GalatApi ? e.message : "Gagal menyimpan." });
    }
  }

  return (
    <div>
      <div className="mb-2 flex items-center gap-2">
        <Tombol varian="utama" disabled={!ubah.size || terkunci} onClick={simpan}>Simpan ({ubah.size})</Tombol>
        <Tombol disabled={!ubah.size} onClick={() => setUbah(new Map())}>Batalkan</Tombol>
        <Tombol onClick={() => setBaru(true)}>+ Seri referensi</Tombol>
        <span className="text-xs text-slate-500">Seri dipakai banyak item: perubahan menghitung ulang semua item tertaut di wilayah {wilayah}.</span>
      </div>
      {pesan && <div className="mb-2"><Pesan jenis={pesan.jenis}>{pesan.teks}</Pesan></div>}
      <div className="ag-theme-quartz grid-dd h-[55vh] w-full">
        <AgGridReact<Seri> rowData={q.data?.seri ?? []} columnDefs={kolom} getRowId={(x) => String(x.data.id)} tooltipShowDelay={300} stopEditingWhenCellsLoseFocus localeText={TEKS_GRID} />
      </div>
      {baru && <DialogSeriBaru tutup={() => setBaru(false)} selesai={() => { setBaru(false); qc.invalidateQueries({ queryKey: kunci }); }} />}
    </div>
  );
}

function DialogSeriBaru({ tutup, selesai }: { tutup: () => void; selesai: () => void }) {
  const [kode, setKode] = useState("REF_");
  const [nama, setNama] = useState("");
  const [jenis, setJenis] = useState("indeks_harga");
  const [satuan, setSatuan] = useState("");
  const [galat, setGalat] = useState<string | null>(null);
  async function kirim(e: FormEvent) {
    e.preventDefault();
    try {
      await api("/api/seri-referensi", { metode: "POST", isi: { kode, nama, jenis, satuan: satuan || null } });
      selesai();
    } catch (err) {
      setGalat(err instanceof GalatApi ? err.message : "Gagal membuat seri.");
    }
  }
  return (
    <Dialog judul="Seri referensi baru" tutup={tutup}>
      <form onSubmit={kirim} className="grid gap-2">
        <Isian label="Kode" petunjuk="Huruf besar/angka/garis bawah, mis. REF_IHK_SANDANG"><Masukan value={kode} onChange={(e) => setKode(e.target.value.toUpperCase())} pattern="[A-Za-z0-9_.\-]{2,40}" required /></Isian>
        <Isian label="Nama"><Masukan value={nama} onChange={(e) => setNama(e.target.value)} required minLength={2} /></Isian>
        <Isian label="Jenis">
          <Pilihan value={jenis} onChange={(e) => setJenis(e.target.value)} aria-label="Jenis seri referensi">
            <option value="indeks_harga">Indeks harga</option>
            <option value="harga">Harga</option>
            <option value="indeks_produksi">Indeks produksi</option>
            <option value="indeks_nilai">Indeks nilai</option>
            <option value="pdrb_td2010">PDRB TD2010</option>
            <option value="lainnya">Lainnya</option>
          </Pilihan>
        </Isian>
        <Isian label="Satuan"><Masukan value={satuan} onChange={(e) => setSatuan(e.target.value)} /></Isian>
        {galat && <Pesan jenis="galat">{galat}</Pesan>}
        <div className="flex justify-end gap-2"><Tombol onClick={tutup}>Batal</Tombol><Tombol varian="utama" type="submit">Buat</Tombol></div>
      </form>
    </Dialog>
  );
}
