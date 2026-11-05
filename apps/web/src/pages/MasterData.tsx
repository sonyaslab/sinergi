import { useState } from "react";
import { useDaftar } from "../api/hooks";
import type { Satuan, Wilayah } from "../api/tipe";
import { Tab } from "../components/ui";
import { KelolaReferensi } from "./master/KelolaReferensi";
import { KonkordansiTab } from "./master/KonkordansiTab";
import { PohonLapus } from "./master/PohonLapus";
import { TahunDasarTab } from "./master/TahunDasarTab";

type Kunci = "pohon" | "td" | "konkordansi" | "katalog" | "satuan" | "sumber" | "wilayah";
const TAB: { kunci: Kunci; label: string }[] = [
  { kunci: "pohon", label: "Pohon lapus" },
  { kunci: "td", label: "Tahun dasar" },
  { kunci: "konkordansi", label: "Konkordansi" },
  { kunci: "katalog", label: "Katalog komoditas" },
  { kunci: "satuan", label: "Satuan" },
  { kunci: "sumber", label: "Sumber data" },
  { kunci: "wilayah", label: "Wilayah" },
];

export function MasterData() {
  const [tab, setTab] = useState<Kunci>("pohon");
  const satuan = useDaftar<Satuan[]>(["/api/satuan", ""], "/api/satuan").data ?? [];
  const wilayah = useDaftar<Wilayah[]>(["/api/wilayah", ""], "/api/wilayah").data ?? [];
  return (
    <div>
      <h1 className="mb-2 text-xl font-semibold">Master data</h1>
      <Tab daftar={TAB} aktif={tab} ubah={setTab} />
      {tab === "pohon" && <PohonLapus />}
      {tab === "td" && <TahunDasarTab />}
      {tab === "konkordansi" && <KonkordansiTab />}
      {tab === "katalog" && (
        <KelolaReferensi judul="Komoditas" jalur="/api/katalog" kunci="id" cari kolom={[
          { kunci: "nama_baku", label: "Nama baku", wajib: true },
          { kunci: "sinonim", label: "Sinonim", tipe: "daftar", petunjuk: "Pisahkan dengan koma, mis. Gurame, Kalui" },
          { kunci: "satuan_kode", label: "Satuan", tipe: "pilihan", pilihan: satuan.filter((s) => s.aktif).map((s) => ({ nilai: s.kode, label: s.nama })) },
          { kunci: "kbli", label: "KBLI" },
          { kunci: "catatan", label: "Catatan" },
        ]} />
      )}
      {tab === "satuan" && (
        <KelolaReferensi judul="Satuan" jalur="/api/satuan" kunci="kode" kolom={[
          { kunci: "kode", label: "Kode", wajib: true, tetap: true },
          { kunci: "nama", label: "Nama", wajib: true },
        ]} />
      )}
      {tab === "sumber" && (
        <KelolaReferensi judul="Sumber data" jalur="/api/sumber-data" kunci="id" kolom={[
          { kunci: "nama", label: "Nama", wajib: true },
          { kunci: "instansi", label: "Instansi" },
          { kunci: "keterangan", label: "Keterangan" },
        ]} />
      )}
      {tab === "wilayah" && (
        <KelolaReferensi judul="Wilayah" jalur="/api/wilayah" kunci="kode" kolom={[
          { kunci: "kode", label: "Kode", wajib: true, tetap: true, pola: "[0-9]{4}", petunjuk: "4 digit, mis. 6504" },
          { kunci: "nama", label: "Nama", wajib: true },
          { kunci: "level", label: "Tingkat", tipe: "pilihan", wajib: true, pilihan: [{ nilai: "provinsi", label: "Provinsi" }, { nilai: "kabupaten", label: "Kabupaten" }, { nilai: "kota", label: "Kota" }] },
          { kunci: "induk", label: "Induk", tipe: "pilihan", pilihan: wilayah.map((w) => ({ nilai: w.kode, label: `${w.kode} ${w.nama}` })) },
          { kunci: "urutan", label: "Urutan", tipe: "angka" },
        ]} />
      )}
    </div>
  );
}
