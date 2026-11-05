// Menu samping. Tiap item tampil bila pengguna memiliki SALAH SATU izin pada `izin` (kode dari sec.peran_izin).
// `izin` kosong = semua pengguna yang sudah masuk. `fase` = fase rencana kerja tempat layar dibangun.

export interface ItemMenu {
  jalur: string;
  label: string;
  izin: string[];
  fase: string;
}

export const MENU: ItemMenu[] = [
  { jalur: "/", label: "Beranda", izin: [], fase: "F0" },
  { jalur: "/data-dasar", label: "Data Dasar", izin: ["data_dasar.isi", "data_dasar.impor", "lk.setujui"], fase: "F3" },
  { jalur: "/lk-hitung", label: "LK Hitung NTB", izin: ["data_dasar.isi", "lk.setujui", "simulasi.edit"], fase: "F4" },
  { jalur: "/biaya-antara", label: "Biaya Antara", izin: ["biaya_antara.isi", "lk.setujui"], fase: "F4" },
  {
    jalur: "/putaran",
    label: "Putaran & Adjustment",
    izin: ["putaran.kelola", "putaran.kunci", "penyesuaian.usul", "penyesuaian.putus", "lk.ajukan", "lk.setujui"],
    fase: "F4",
  },
  { jalur: "/kompilasi", label: "Kompilasi & Simulasi", izin: ["simulasi.edit"], fase: "F4" },
  { jalur: "/tabel-pokok", label: "Tabel Pokok", izin: ["tabel_pokok.lihat"], fase: "F5" },
  { jalur: "/dashboard", label: "Dashboard Pimpinan", izin: ["dashboard.lihat"], fase: "F5" },
  { jalur: "/master", label: "Master Data", izin: ["master.kelola"], fase: "F1" },
  { jalur: "/pengguna", label: "Pengguna & Hak Akses", izin: ["pengguna.kelola"], fase: "F1" },
  { jalur: "/audit", label: "Jejak Audit", izin: ["audit.lihat"], fase: "F1" },
];

export function menuUntuk(izinPengguna: readonly string[]): ItemMenu[] {
  const punya = new Set(izinPengguna);
  return MENU.filter((m) => m.izin.length === 0 || m.izin.some((k) => punya.has(k)));
}
