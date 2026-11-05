import { useState, type FormEvent } from "react";
import { api } from "../../api/klien";
import { useAksi, useDaftar } from "../../api/hooks";
import type { PenggunaAdmin, Peran } from "../../api/tipe";
import { Centang, Isian, Lencana, Masukan, Panel, Pesan, Tombol, kelasTabel, kelasTd, kelasTh } from "../../components/ui";

function SandiSementara({ username, sandi, tutup }: { username: string; sandi: string; tutup: () => void }) {
  return (
    <Panel judul="Sandi sementara" tutup={tutup}>
      <p className="mb-2 text-sm">Berikan kepada <b>{username}</b> lewat jalur aman. Sandi ini hanya tampil sekali; pengguna wajib menggantinya dan mendaftarkan TOTP saat login pertama.</p>
      <div className="flex items-center gap-2">
        <code className="rounded bg-amber-50 px-3 py-2 font-mono text-lg" aria-label="Sandi sementara">{sandi}</code>
        <Tombol onClick={() => navigator.clipboard?.writeText(sandi)}>Salin</Tombol>
      </div>
    </Panel>
  );
}

function Formulir({ lama, peran, selesai }: { lama: PenggunaAdmin | null; peran: Peran[]; selesai: (r?: { pesan: string; sandi?: { username: string; sandi: string } }) => void }) {
  const [f, setF] = useState({ username: lama?.username ?? "", nama: lama?.nama ?? "", email: lama?.email ?? "", nip: lama?.nip ?? "", aktif: lama?.aktif ?? true });
  const [pilih, setPilih] = useState<Set<string>>(new Set(lama?.peran ?? []));
  const aksi = useAksi([["pengguna"]]);
  async function kirim(e: FormEvent) {
    e.preventDefault();
    const data = { nama: f.nama, email: f.email || null, nip: f.nip || null, peran: [...pilih] };
    if (lama) {
      const r = await aksi.jalankan(() => api(`/api/pengguna/${lama.id}`, { metode: "PATCH", isi: { ...data, aktif: f.aktif } }));
      if (r) selesai({ pesan: `${lama.username} tersimpan.` });
    } else {
      const r = await aksi.jalankan(() => api<{ username: string; sandi_sementara: string }>("/api/pengguna", { metode: "POST", isi: { ...data, username: f.username } }));
      if (r) selesai({ pesan: `${r.username} dibuat.`, sandi: { username: r.username, sandi: r.sandi_sementara } });
    }
  }
  return (
    <Panel judul={lama ? `Ubah ${lama.username}` : "Tambah pengguna"} tutup={() => selesai()}>
      <form onSubmit={kirim} className="space-y-2">
        {aksi.pesan && <Pesan jenis={aksi.pesan.jenis}>{aksi.pesan.teks}</Pesan>}
        <Isian label="Nama pengguna" petunjuk="huruf kecil/angka/titik, mis. op.nunukan">
          <Masukan required disabled={!!lama} pattern="[a-z0-9._\-]{3,40}" value={f.username} onChange={(e) => setF({ ...f, username: e.target.value })} />
        </Isian>
        <Isian label="Nama lengkap"><Masukan required value={f.nama} onChange={(e) => setF({ ...f, nama: e.target.value })} /></Isian>
        <div className="grid grid-cols-2 gap-2">
          <Isian label="Email"><Masukan type="email" value={f.email} onChange={(e) => setF({ ...f, email: e.target.value })} /></Isian>
          <Isian label="NIP"><Masukan value={f.nip} onChange={(e) => setF({ ...f, nip: e.target.value })} /></Isian>
        </div>
        <fieldset className="text-sm">
          <legend className="mb-1 text-slate-700">Peran</legend>
          <div className="flex flex-wrap gap-3">
            {peran.filter((p) => p.aktif).map((p) => (
              <Centang key={p.kode} label={p.nama} checked={pilih.has(p.kode)}
                onChange={(e) => setPilih((s) => { const n = new Set(s); if (e.target.checked) n.add(p.kode); else n.delete(p.kode); return n; })} />
            ))}
          </div>
        </fieldset>
        {lama && <Centang label="Aktif" checked={f.aktif} onChange={(e) => setF({ ...f, aktif: e.target.checked })} />}
        <div><Tombol varian="utama" type="submit" disabled={aksi.sibuk || pilih.size === 0}>Simpan</Tombol></div>
      </form>
    </Panel>
  );
}

export function PenggunaTab() {
  const q = useDaftar<PenggunaAdmin[]>(["pengguna"], "/api/pengguna");
  const peran = useDaftar<Peran[]>(["peran"], "/api/peran").data ?? [];
  const aksi = useAksi([["pengguna"]]);
  const [mode, setMode] = useState<{ lama: PenggunaAdmin | null } | null>(null);
  const [sandi, setSandi] = useState<{ username: string; sandi: string } | null>(null);

  async function tindakan(u: PenggunaAdmin, jenis: "reset-sandi" | "reset-totp" | "buka-kunci" | "nonaktif") {
    const tanya = { "reset-sandi": `Reset sandi ${u.username}? Sesi aktifnya dicabut.`, "reset-totp": `Reset TOTP ${u.username}? Ia mendaftar ulang saat login berikutnya.`, "buka-kunci": "", nonaktif: `Nonaktifkan ${u.username}? Semua sesinya dicabut.` }[jenis];
    if (tanya && !window.confirm(tanya)) return;
    if (jenis === "reset-sandi") {
      const r = await aksi.jalankan(() => api<{ sandi_sementara: string }>(`/api/pengguna/${u.id}/reset-sandi`, { metode: "POST" }), "Sandi direset.");
      if (r) setSandi({ username: u.username, sandi: r.sandi_sementara });
    } else if (jenis === "nonaktif") {
      await aksi.jalankan(() => api(`/api/pengguna/${u.id}`, { metode: "DELETE" }), `${u.username} dinonaktifkan.`);
    } else {
      await aksi.jalankan(() => api(`/api/pengguna/${u.id}/${jenis}`, { metode: "POST" }), jenis === "reset-totp" ? "TOTP direset." : "Kunci dibuka.");
    }
  }

  return (
    <div className="grid gap-4 xl:grid-cols-[minmax(0,2fr)_minmax(320px,1fr)]">
      <div className="min-w-0 space-y-2">
        <Tombol varian="utama" onClick={() => setMode({ lama: null })}>+ Pengguna</Tombol>
        {aksi.pesan && <Pesan jenis={aksi.pesan.jenis}>{aksi.pesan.teks}</Pesan>}
        <div className="overflow-auto rounded border border-slate-200 bg-white">
          <table className={kelasTabel} aria-label="Pengguna">
            <thead><tr>{["Pengguna", "Peran", "Status", "Login terakhir", "Aksi"].map((h) => <th key={h} className={kelasTh}>{h}</th>)}</tr></thead>
            <tbody>
              {(q.data ?? []).map((u) => (
                <tr key={u.id} className={u.aktif ? "" : "text-slate-400"}>
                  <td className={kelasTd}><div className="font-medium">{u.nama}</div><div className="font-mono text-xs text-slate-500">{u.username}</div></td>
                  <td className={kelasTd}>{u.peran.join(", ")}</td>
                  <td className={`${kelasTd} space-x-1`}>
                    {u.akun_sistem ? <Lencana>akun sistem</Lencana> : <>
                      {u.aktif ? <Lencana warna="hijau">aktif</Lencana> : <Lencana>nonaktif</Lencana>}
                      {!u.totp_aktif && <Lencana warna="kuning">TOTP belum</Lencana>}
                      {u.wajib_ganti_sandi && <Lencana warna="kuning">sandi sementara</Lencana>}
                      {u.terkunci && <Lencana warna="merah">terkunci</Lencana>}
                    </>}
                  </td>
                  <td className={`${kelasTd} text-xs`}>{u.terakhir_login ? new Date(u.terakhir_login).toLocaleString("id-ID") : "—"}</td>
                  <td className={`${kelasTd} whitespace-nowrap`}>
                    {!u.akun_sistem && <>
                      <Tombol kecil varian="teks" onClick={() => setMode({ lama: u })}>Ubah</Tombol>
                      <Tombol kecil varian="teks" onClick={() => tindakan(u, "reset-sandi")}>Reset sandi</Tombol>
                      <Tombol kecil varian="teks" onClick={() => tindakan(u, "reset-totp")}>Reset TOTP</Tombol>
                      {u.terkunci && <Tombol kecil varian="teks" onClick={() => tindakan(u, "buka-kunci")}>Buka kunci</Tombol>}
                      {u.aktif && <Tombol kecil varian="teks" className="text-red-700" onClick={() => tindakan(u, "nonaktif")}>Nonaktifkan</Tombol>}
                    </>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
      <div className="space-y-4">
        {sandi && <SandiSementara {...sandi} tutup={() => setSandi(null)} />}
        {mode && <Formulir key={mode.lama?.id ?? "baru"} lama={mode.lama} peran={peran}
          selesai={(r) => { setMode(null); if (r) { aksi.setPesan({ jenis: "ok", teks: r.pesan }); if (r.sandi) setSandi(r.sandi); } }} />}
      </div>
    </div>
  );
}
