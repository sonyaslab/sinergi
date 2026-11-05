// Tipe respons API master (F1).
export type JenisLapus =
  | "kategori" | "sub" | "daun" | "kelompok" | "ntb" | "top" | "sop" | "topsop" | "pdrb" | "pdrb_nonmigas";

export interface Lapus {
  id: number;
  tahun_dasar_id: number;
  kode: string;
  nama: string;
  induk_id: number | null;
  level: number;
  urutan: number;
  jenis: JenisLapus;
  kode_lk_bps: string | null;
  is_migas: boolean;
  aktif: boolean;
  anggota: number[];
  jumlah_item: number;
}

export interface Konkordansi {
  id: number;
  lapus_asal_id: number;
  kode_asal: string;
  nama_asal: string;
  td_asal: string;
  lapus_tujuan_id: number;
  kode_tujuan: string;
  nama_tujuan: string;
  td_tujuan: string;
  bobot: number | null;
  catatan: string | null;
}
export interface RingkasanAsal {
  jumlah_tujuan: number;
  jumlah_bobot: number;
  bobot_kosong: number;
  lengkap: boolean;
}

export interface Katalog {
  id: number;
  nama_baku: string;
  sinonim: string[];
  satuan_kode: string | null;
  kbli: string | null;
  catatan: string | null;
  aktif: boolean;
}
export interface Satuan { kode: string; nama: string; aktif: boolean }
export interface SumberData { id: number; nama: string; instansi: string | null; keterangan: string | null; aktif: boolean }
export interface Wilayah { kode: string; nama: string; level: "provinsi" | "kabupaten" | "kota"; induk: string | null; urutan: number; aktif: boolean }

export interface PenggunaAdmin {
  id: number;
  username: string;
  nama: string;
  email: string | null;
  nip: string | null;
  aktif: boolean;
  totp_aktif: boolean;
  wajib_ganti_sandi: boolean;
  terakhir_login: string | null;
  terkunci: boolean;
  akun_sistem: boolean;
  peran: string[];
}
export interface Peran { id: number; kode: string; nama: string; aktif: boolean; izin: string[]; jumlah_pengguna: number }
export interface Izin { kode: string; nama: string }
export interface Penugasan {
  id: number;
  pengguna_id: number;
  username: string;
  nama: string;
  tahun_dasar_id: number;
  tahun_dasar: string;
  wilayah_kode: string;
  lapus_id: number;
  kode_lapus: string;
  nama_lapus: string;
  peran_tugas: "operator" | "pemeriksa";
  berlaku_mulai: string;
  berlaku_sampai: string | null;
  aktif: boolean;
}
export interface BarisAudit {
  id: number;
  waktu: string;
  pengguna_id: number | null;
  username: string | null;
  ip: string | null;
  aksi: string;
  entitas: string;
  entitas_id: string | null;
  putaran_id: number | null;
  alasan: string | null;
  nilai_lama: Record<string, unknown> | null;
  nilai_baru: Record<string, unknown> | null;
}
export interface HasilHapus { hasil: "dihapus" | "dinonaktifkan" | "diakhiri"; pesan: string }
