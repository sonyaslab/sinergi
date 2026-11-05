import { useState, type FormEvent } from "react";
import { api, GalatApi } from "../../api/klien";
import { useDaftar } from "../../api/hooks";
import type { Katalog, Satuan } from "../../api/tipe";
import { Dialog } from "../../components/Dialog";
import { Isian, Masukan, Pesan, Pilihan, Tombol } from "../../components/ui";
import { labelPeriode } from "../../lib/dataDasar";
import type { Putaran } from "../DataDasar";

/** + Komoditas: nama dari katalog (autocomplete), metode, satuan, jenis indeks (EKS), berlaku mulai/sampai, alasan. */
export function DialogKomoditas({ putaran, wilayah, lapus, tutup, selesai }: {
  putaran: Putaran;
  wilayah: string;
  lapus: { id: number; kode: string; nama: string }[];
  tutup: () => void;
  selesai: (pesan: string) => void;
}) {
  const [lapusId, setLapusId] = useState(lapus[0]?.id ?? 0);
  const [metode, setMetode] = useState<"REV" | "EKS" | "DEF" | "PDK">("REV");
  const [nama, setNama] = useState("");
  const [satuan, setSatuan] = useState("");
  const [jenis, setJenis] = useState<"IP" | "IB">("IP");
  const [mulai, setMulai] = useState<string>("");
  const [selesaiP, setSelesaiP] = useState<string>("");
  const [sumber, setSumber] = useState("");
  const [alasan, setAlasan] = useState("");
  const [galat, setGalat] = useState<string | null>(null);
  const cari = nama.trim().length >= 2 ? nama.trim() : null;
  const katalog = useDaftar<Katalog[]>(["/api/katalog", cari], cari ? `/api/katalog?q=${encodeURIComponent(cari)}` : null).data ?? [];
  const daftarSatuan = (useDaftar<Satuan[]>(["/api/satuan", ""], "/api/satuan").data ?? []).filter((s) => s.aktif);
  const periode: number[] = [];
  for (let u = putaran.awal; u <= putaran.akhir; u++) periode.push(u);
  const cocok = katalog.find((k) => k.nama_baku.toLowerCase() === nama.trim().toLowerCase());

  async function kirim(e: FormEvent) {
    e.preventDefault();
    setGalat(null);
    try {
      const r = await api<{ pesan: string }>("/api/data-dasar/item", {
        metode: "POST",
        isi: {
          putaran_id: putaran.id, wilayah, lapus_id: lapusId, metode, nama: nama.trim(), katalog_id: cocok?.id ?? null,
          satuan_kode: satuan || cocok?.satuan_kode || null, jenis_indeks: metode === "EKS" ? jenis : null,
          mulai: mulai ? Number(mulai) : null, selesai: selesaiP ? Number(selesaiP) : null, sumber: sumber || null, alasan,
        },
      });
      selesai(r.pesan);
    } catch (err) {
      setGalat(err instanceof GalatApi ? err.message : "Gagal menambah komoditas.");
    }
  }

  return (
    <Dialog judul="+ Komoditas" tutup={tutup}>
      <form onSubmit={kirim} className="grid gap-2">
        <Isian label="Lapus">
          <Pilihan value={lapusId} onChange={(e) => setLapusId(Number(e.target.value))} aria-label="Lapus">
            {lapus.map((l) => <option key={l.id} value={l.id}>{l.kode} — {l.nama}</option>)}
          </Pilihan>
        </Isian>
        <Isian label="Nama komoditas/rincian" petunjuk={cocok ? "Sesuai katalog baku." : katalog.length ? "Pilih nama baku dari daftar bila ada." : undefined}>
          <Masukan list="katalog-komoditas" value={nama} onChange={(e) => setNama(e.target.value)} required maxLength={200} />
          <datalist id="katalog-komoditas">
            {katalog.map((k) => <option key={k.id} value={k.nama_baku}>{k.sinonim.join(", ")}</option>)}
          </datalist>
        </Isian>
        <div className="grid grid-cols-2 gap-2">
          <Isian label="Metode">
            <Pilihan value={metode} onChange={(e) => setMetode(e.target.value as typeof metode)} aria-label="Metode">
              <option value="REV">REV — revaluasi</option>
              <option value="EKS">EKS — ekstrapolasi</option>
              <option value="DEF">DEF — deflasi</option>
              <option value="PDK">PDK — pendukung</option>
            </Pilihan>
          </Isian>
          {metode === "EKS" ? (
            <Isian label="Jenis indeks">
              <Pilihan value={jenis} onChange={(e) => setJenis(e.target.value as "IP" | "IB")} aria-label="Jenis indeks">
                <option value="IP">IP — indeks produksi</option>
                <option value="IB">IB — indeks berlaku</option>
              </Pilihan>
            </Isian>
          ) : (
            <Isian label="Satuan">
              <Pilihan value={satuan} onChange={(e) => setSatuan(e.target.value)} aria-label="Satuan">
                <option value="">{cocok?.satuan_kode ? `(katalog: ${cocok.satuan_kode})` : "—"}</option>
                {daftarSatuan.map((s) => <option key={s.kode} value={s.kode}>{s.nama}</option>)}
              </Pilihan>
            </Isian>
          )}
          <Isian label="Berlaku mulai" petunjuk="Kosong = sejak awal seri">
            <Pilihan value={mulai} onChange={(e) => setMulai(e.target.value)} aria-label="Berlaku mulai">
              <option value="">—</option>
              {periode.map((u) => <option key={u} value={u}>{labelPeriode(u)}</option>)}
            </Pilihan>
          </Isian>
          <Isian label="Berlaku sampai" petunjuk="Kosong = masih berlaku">
            <Pilihan value={selesaiP} onChange={(e) => setSelesaiP(e.target.value)} aria-label="Berlaku sampai">
              <option value="">—</option>
              {periode.map((u) => <option key={u} value={u}>{labelPeriode(u)}</option>)}
            </Pilihan>
          </Isian>
        </div>
        <Isian label="Sumber data"><Masukan value={sumber} onChange={(e) => setSumber(e.target.value)} maxLength={300} /></Isian>
        <Isian label="Alasan" petunjuk="Wajib, min. 10 karakter (tercatat di jejak audit).">
          <Masukan value={alasan} onChange={(e) => setAlasan(e.target.value)} minLength={10} required />
        </Isian>
        {galat && <Pesan jenis="galat">{galat}</Pesan>}
        <div className="flex justify-end gap-2">
          <Tombol onClick={tutup}>Batal</Tombol>
          <Tombol varian="utama" type="submit" disabled={!nama.trim() || alasan.trim().length < 10}>Tambah</Tombol>
        </div>
      </form>
    </Dialog>
  );
}
