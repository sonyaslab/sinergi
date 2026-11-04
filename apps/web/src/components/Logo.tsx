// Logo teks SINERGI (placeholder SVG; ganti dengan logo resmi bila tersedia).
export function Logo({ ukuran = 32 }: { ukuran?: number }) {
  return (
    <svg width={ukuran} height={ukuran} viewBox="0 0 64 64" role="img" aria-label="Logo SINERGI">
      <rect width="64" height="64" rx="14" fill="#1559b0" />
      <path d="M14 44 L26 30 L34 37 L50 18" fill="none" stroke="#fff" strokeWidth="6" strokeLinecap="round" strokeLinejoin="round" />
      <circle cx="50" cy="18" r="4.5" fill="#ffd34d" />
    </svg>
  );
}

export const NAMA_PRODUK = "SINERGI";
export const KEPANJANGAN = "Sistem Neraca Ekonomi Regional Terintegrasi";
export const INSTITUSI = "BPS Provinsi Kalimantan Utara";
