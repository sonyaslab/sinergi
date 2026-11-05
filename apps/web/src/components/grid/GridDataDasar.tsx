// Grid Data Dasar (AG Grid Community): baris = item x seri, kolom = triwulan per tahun (tahun lama dapat dilipat).
// Sel kuning dapat diedit; baris hijau (rumus) dan biru (tertaut) dihitung sistem. Tempel dari Excel: Ctrl+V pada
// sel fokus (papan klip TSV). Ikon validasi per sel dan per baris; kontribusi item ke output lapus.
import { useCallback, useMemo, useRef, type ClipboardEvent } from "react";
import { AgGridReact } from "ag-grid-react";
import type {
  CellClassParams,
  ColDef,
  ColGroupDef,
  GridApi,
  GridReadyEvent,
  ICellRendererParams,
  ITooltipParams,
  RowClassParams,
  ValueGetterParams,
  ValueSetterParams,
} from "ag-grid-community";
import "ag-grid-community/styles/ag-grid.css";
import "ag-grid-community/styles/ag-theme-quartz.css";
import {
  bolehUbahSel,
  grupTahun,
  KOLOM_PERIODE,
  terberat,
  type BarisGrid,
  type IndeksTemuan,
  type Periode,
  type Temuan,
} from "../../lib/dataDasar";
import { formatAngka, petakanTempel, uraiAngka, uraiTempel, type IsiSel } from "../../lib/tempel";

export type Tertunda = Map<string, IsiSel>; // "<item>:<seri>:<urut>" -> isi baru

export interface PropsGrid {
  baris: BarisGrid[];
  periode: Periode[];
  terkunci: boolean;
  temuan: IndeksTemuan;
  tertunda: Tertunda;
  periodeKontribusi: number;
  ubah: (b: BarisGrid, urut: number, isi: IsiSel) => void;
  ubahJangkar: (b: BarisGrid, nilai: number | null) => void;
  pilih: (b: BarisGrid | null) => void;
  galat: (pesan: string) => void;
  info: (pesan: string) => void;
}

export const TEKS_GRID = { noRowsToShow: "Belum ada data", loadingOoo: "Memuat…" };

const kunciSel = (b: BarisGrid, u: number) => `${b.item.id}:${b.seri.kode}:${u}`;

function teksTemuan(ts: Temuan[] | undefined): string | undefined {
  if (!ts?.length) return undefined;
  return ts.map((t) => `${t.kode}${t.dikonfirmasi ? " (dikonfirmasi)" : ""}: ${t.pesan}`).join("\n");
}

function RenderSeri(p: ICellRendererParams<BarisGrid> & { temuan: IndeksTemuan }) {
  const b = p.data;
  if (!b) return null;
  const ts = [...(p.temuan.baris.get(`${b.item.id}|${b.seri.kode}`) ?? []),
    ...[...p.temuan.sel.entries()].filter(([k]) => k.startsWith(`${b.item.id}|${b.seri.kode}|`)).flatMap(([, v]) => v),
    ...(b.pertama ? p.temuan.item.get(b.item.id) ?? [] : [])];
  const t = terberat(ts);
  return (
    <span title={teksTemuan(ts)}>
      {b.seri.kode}
      {t && <span className={`titik-v titik-${t}`} aria-label={`temuan ${t}`} />}
    </span>
  );
}

export function GridDataDasar(p: PropsGrid) {
  const apiRef = useRef<GridApi<BarisGrid> | null>(null);
  const per = useMemo(() => new Map(p.periode.map((x) => [x.urut, x])), [p.periode]);
  const ref = useRef(p);
  ref.current = p;

  const nilaiSel = useCallback((b: BarisGrid, u: number): number | null | "tt" => {
    const t = ref.current.tertunda.get(kunciSel(b, u));
    if (t) return t.jenis === "angka" ? t.nilai : t.jenis === "tidak_tersedia" ? "tt" : null;
    if (b.jenis === "isian" && b.seri.tidak_tersedia.includes(u)) return "tt";
    return b.nilai[String(u)] ?? null;
  }, []);

  const kolom = useMemo<(ColDef<BarisGrid> | ColGroupDef<BarisGrid>)[]>(() => {
    const kunci = (c: ColDef<BarisGrid>): ColDef<BarisGrid> => ({ pinned: "left", cellClass: "kol-kunci", suppressMovable: true, ...c });
    const depan: ColDef<BarisGrid>[] = [
      kunci({ headerName: "Lapus", width: 64, valueGetter: (x) => (x.data?.pertama ? x.data.item.kode_lapus : "") }),
      kunci({ headerName: "Metode/No", width: 76, valueGetter: (x) => (x.data?.pertama ? `${x.data.item.metode} ${x.data.item.nomor}` : "") }),
      kunci({
        headerName: "Komoditas / Rincian", width: 190, tooltipValueGetter: (x) => x.data?.item.nama,
        valueGetter: (x) => (x.data?.pertama ? x.data.item.nama + (x.data.item.status === "nonaktif" ? " (nonaktif)" : "") : ""),
        cellClass: (x: CellClassParams<BarisGrid>) => ["kol-kunci", x.data?.pertama ? "font-semibold" : "kol-ulang"],
      }),
      kunci({ headerName: "Seri", width: 104, cellRenderer: RenderSeri, cellRendererParams: { temuan: p.temuan } }),
      { headerName: "Satuan", width: 86, valueGetter: (x) => x.data?.seri.satuan ?? "", tooltipValueGetter: (x) => x.data?.seri.satuan, cellClass: "kol-kunci" },
      {
        headerName: "Jangkar", width: 92, type: "rightAligned", headerTooltip: "Jangkar tahun dasar (RKA_TD, H_TD, IH_TD, R_MARGIN_TD)",
        valueGetter: (x) => x.data?.seri.jangkar?.nilai ?? null,
        valueFormatter: (x) => formatAngka(x.value as number | null),
        editable: (x) => Boolean(x.data?.seri.jangkar && x.data.item.boleh_tulis && !ref.current.terkunci),
        valueSetter: (x: ValueSetterParams<BarisGrid>) => {
          const isi = uraiAngka(String(x.newValue ?? ""));
          if (isi.jenis === "galat" || isi.jenis === "tidak_tersedia" || !x.data) {
            ref.current.galat("Jangkar harus angka atau kosong.");
            return false;
          }
          ref.current.ubahJangkar(x.data, isi.jenis === "angka" ? isi.nilai : null);
          return false;
        },
        cellClass: (x) => (!x.data?.seri.jangkar ? "" : x.data.item.boleh_tulis && !ref.current.terkunci ? "sel-isian" : "sel-kunci"),
        tooltipValueGetter: (x: ITooltipParams<BarisGrid>) =>
          x.data?.seri.jangkar ? `${x.data.seri.jangkar.kode}${x.data.seri.jangkar.alasan ? ` — ${x.data.seri.jangkar.alasan}` : ""}` : undefined,
      },
      {
        headerName: "Kontr. %", width: 72, type: "rightAligned", headerTooltip: "Kontribusi item ke output lapus (ADHB) pada triwulan terpilih",
        valueGetter: (x) => (x.data?.pertama ? x.data.item.kontribusi[String(ref.current.periodeKontribusi)]?.[0] ?? null : null),
        valueFormatter: (x) => (x.value === null || x.value === undefined ? "" : `${formatAngka(x.value as number)}`),
        tooltipValueGetter: (x) => {
          const k = x.data?.pertama ? x.data.item.kontribusi[String(ref.current.periodeKontribusi)] : undefined;
          return k ? `ADHB ${formatAngka(k[0])}% · ADHK ${formatAngka(k[1])}%` : undefined;
        },
      },
    ];
    const grup: ColGroupDef<BarisGrid>[] = grupTahun(p.periode).map((g) => ({
      headerName: String(g.tahun),
      groupId: `y${g.tahun}`,
      openByDefault: g.terbuka,
      marryChildren: true,
      children: [
        ...g.periode.map((pe): ColDef<BarisGrid> => ({
          colId: `${KOLOM_PERIODE}${pe.urut}`,
          headerName: `T${(pe.urut % 4) + 1}`,
          headerTooltip: pe.label,
          width: 92,
          type: "rightAligned",
          columnGroupShow: "open",
          suppressMovable: true,
          valueGetter: (x: ValueGetterParams<BarisGrid>) => (x.data ? nilaiSel(x.data, pe.urut) : null),
          valueFormatter: (x) => (x.value === "tt" ? "–" : formatAngka(x.value as number | null)),
          editable: (x) => Boolean(x.data && bolehUbahSel(x.data, pe.urut, per, ref.current.terkunci)),
          valueSetter: (x: ValueSetterParams<BarisGrid>) => {
            if (!x.data) return false;
            const isi = uraiAngka(String(x.newValue ?? ""));
            if (isi.jenis === "galat") {
              ref.current.galat(`"${isi.teks}" bukan angka. Gunakan angka, kosongkan, atau "-" bila tidak tersedia.`);
              return false;
            }
            ref.current.ubah(x.data, pe.urut, isi);
            return true;
          },
          cellClass: (x: CellClassParams<BarisGrid>) => {
            const b = x.data;
            if (!b) return [];
            const k: string[] = [];
            const boleh = bolehUbahSel(b, pe.urut, per, ref.current.terkunci);
            k.push(b.jenis === "rumus" ? "sel-rumus" : b.jenis === "taut" ? "sel-taut" : boleh ? "sel-isian" : "sel-kunci");
            if (ref.current.tertunda.has(kunciSel(b, pe.urut))) k.push("sel-ubah");
            if (x.value === "tt") k.push("sel-tt");
            const { mulai, selesai } = b.item;
            if ((mulai !== null && pe.urut < mulai) || (selesai !== null && pe.urut > selesai)) k.push("sel-luar-masa");
            const t = terberat(ref.current.temuan.sel.get(`${b.item.id}|${b.seri.kode}|${pe.urut}`));
            if (t) k.push(`sel-v-${t}`);
            return k;
          },
          tooltipValueGetter: (x: ITooltipParams<BarisGrid>) => {
            const b = x.data;
            if (!b) return undefined;
            const ts = teksTemuan(ref.current.temuan.sel.get(`${b.item.id}|${b.seri.kode}|${pe.urut}`));
            const luar = (b.item.mulai !== null && pe.urut < b.item.mulai) || (b.item.selesai !== null && pe.urut > b.item.selesai)
              ? "Di luar masa berlaku item: nilai tidak dipakai hitung." : undefined;
            return [ts, luar, b.jenis !== "isian" ? b.seri.tautan?.teks : undefined].filter(Boolean).join("\n") || undefined;
          },
        })),
        {
          colId: `r${g.tahun}`,
          headerName: "Terisi",
          headerTooltip: "Jumlah triwulan terisi (tahun terlipat)",
          width: 64,
          columnGroupShow: "closed",
          valueGetter: (x) => (x.data ? `${g.periode.filter((pe) => typeof nilaiSel(x.data as BarisGrid, pe.urut) === "number").length}/${g.periode.length}` : ""),
          cellClass: "sel-kunci",
        },
      ],
    }));
    const belakang: ColDef<BarisGrid>[] = [
      { headerName: "Tautan / Rumus", width: 220, valueGetter: (x) => x.data?.seri.tautan?.teks ?? "", tooltipValueGetter: (x) => x.data?.seri.tautan?.teks },
      { headerName: "Catatan", width: 200, valueGetter: (x) => x.data?.seri.catatan ?? "", tooltipValueGetter: (x) => x.data?.seri.catatan ?? undefined },
    ];
    return [...depan, ...grup, ...belakang];
  }, [p.periode, p.temuan, per, nilaiSel]);

  const onPaste = useCallback((e: ClipboardEvent<HTMLDivElement>) => {
    const api = apiRef.current;
    const fokus = api?.getFocusedCell();
    if (!api || !fokus || api.getEditingCells().length > 0) return;
    const teks = e.clipboardData.getData("text/plain");
    if (!teks) return;
    e.preventDefault();
    const baris: BarisGrid[] = [];
    api.forEachNodeAfterFilterAndSort((n) => n.data && baris.push(n.data));
    const kol = api.getAllDisplayedColumns().map((c) => c.getColId());
    const j0 = kol.indexOf(fokus.column.getColId());
    const h = petakanTempel(teks.length > 200000 ? [] : uraiTempel(teks), fokus.rowIndex, j0, {
      baris,
      kolom: kol,
      bolehUbah: (b, k) => k.startsWith(KOLOM_PERIODE) && bolehUbahSel(b, Number(k.slice(KOLOM_PERIODE.length)), per, ref.current.terkunci),
    });
    for (const u of h.ubah) ref.current.ubah(u.baris, Number(u.kolom.slice(KOLOM_PERIODE.length)), u.isi);
    api.refreshCells({ force: true });
    if (h.galat.length || h.dilewati) {
      (h.galat.length ? ref.current.galat : ref.current.info)(
        [h.galat.length ? `${h.galat.length} sel bukan angka diabaikan.` : "", h.dilewati ? `${h.dilewati} sel terkunci/rumus/tautan dilewati.` : "",
         h.ubah.length ? `${h.ubah.length} sel ditempel (belum disimpan).` : ""]
          .filter(Boolean).join(" "),
      );
    }
  }, [per]);

  return (
    <div className="ag-theme-quartz grid-dd h-[62vh] w-full" onPaste={onPaste}>
      <AgGridReact<BarisGrid>
        rowData={p.baris}
        columnDefs={kolom}
        getRowId={(x) => x.data.id}
        onGridReady={(e: GridReadyEvent<BarisGrid>) => (apiRef.current = e.api)}
        rowClassRules={{ "baris-ganjil": (x: RowClassParams<BarisGrid>) => Boolean(x.data?.ganjil), "baris-genap": (x) => !x.data?.ganjil }}
        onCellFocused={(e) => {
          const n = e.rowIndex !== null && e.rowIndex !== undefined ? apiRef.current?.getDisplayedRowAtIndex(e.rowIndex) : null;
          ref.current.pilih(n?.data ?? null);
        }}
        singleClickEdit={false}
        stopEditingWhenCellsLoseFocus
        enterNavigatesVerticallyAfterEdit
        tooltipShowDelay={300}
        suppressColumnVirtualisation={false}
        animateRows={false}
        localeText={TEKS_GRID}
      />
    </div>
  );
}
