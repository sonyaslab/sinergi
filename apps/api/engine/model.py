"""Model masukan dan hasil mesin hitung (murni, tanpa I/O).

Periode memakai `urut` = tahun × 4 + triwulan − 1 (sama dengan kolom `ref.periode.urut`).
Seri = dict urut -> nilai; kunci yang tidak ada = sel kosong (dihitung 0, rata-rata mengabaikannya).
"""
from __future__ import annotations

from dataclasses import dataclass, field

Seri = dict[int, float]

VERSI_MESIN = "1.0.0"

METODE_HITUNG = ("REV", "EKS", "DEF")  # PDK (pendukung) tidak dihitung
BERITEM = ("daun", "top", "sop")  # lapus berdata (boleh punya item)
TANPA_KA = ("top", "sop")  # keputusan 1: konsumsi antara = 0, NTB = output
TAHAP_LAPUS = ("PRE", "POST", "BENC", "FINAL")


class GalatMesin(ValueError):
    """Masukan tidak dapat dihitung. Pesan aman untuk pengguna (tanpa angka PDRB)."""


class SiklusTautan(GalatMesin):
    """Tautan antarlapus (HASIL_LAPUS/MARGIN) membentuk siklus."""


def urut(tahun: int, triwulan: int) -> int:
    return tahun * 4 + triwulan - 1


def label(u: int) -> str:
    return f"Q{u % 4 + 1}-{u // 4}"


def urut_tahun(tahun: int) -> list[int]:
    """4 triwulan satu tahun (mis. tahun baseline T₀)."""
    return [urut(tahun, q) for q in (1, 2, 3, 4)]


@dataclass(frozen=True)
class Sumbu:
    """Rentang periode hitung (inklusif), berurutan tanpa celah."""

    awal: int
    akhir: int

    def __post_init__(self) -> None:
        if self.akhir < self.awal:
            raise GalatMesin("Rentang periode putaran tidak valid.")

    @property
    def periode(self) -> range:
        return range(self.awal, self.akhir + 1)

    def __len__(self) -> int:
        return self.akhir - self.awal + 1

    def i(self, u: int) -> int:
        return u - self.awal

    def mencakup(self, *us: int) -> Sumbu:
        return Sumbu(min(self.awal, *us), max(self.akhir, *us))


@dataclass(frozen=True)
class KonfigTD:
    """Konfigurasi tahun dasar (ref.tahun_dasar)."""

    tahun_baseline: int  # tahun_baseline_eks: TD2025 = 2025, TD2010 = mis. 2024
    jangkar_dari_data: bool  # TD2025 true; TD2010 false (keputusan 3)

    @property
    def t0(self) -> list[int]:
        return urut_tahun(self.tahun_baseline)


@dataclass(frozen=True)
class Tautan:
    """lk.tautan_seri: seri item diambil dari seri referensi, hasil lapus lain, atau rumus baku."""

    jenis_seri: str
    sumber: str  # SERI_REFERENSI | HASIL_LAPUS | RUMUS
    rumus: str | None = None
    seri_ref: str | None = None
    lapus_sumber: tuple[int, ...] = ()
    besaran: str | None = None  # OUT_CP | OUT_K | GVA_CP | GVA_K | IMPLISIT_OUT
    faktor: float = 1.0


@dataclass
class Item:
    id: int
    metode: str  # REV | EKS | DEF | PDK
    jenis_indeks: str | None = None  # EKS: IP | IB
    seri: dict[str, Seri] = field(default_factory=dict)
    parameter: dict[str, float] = field(default_factory=dict)  # RKA_TD, H_TD, IH_TD, R_MARGIN_TD
    tautan: tuple[Tautan, ...] = ()
    mulai: int | None = None  # masa berlaku (urut); nilai di luar masa dianggap tidak ada
    selesai: int | None = None


@dataclass
class ItemSiap:
    """Item setelah masa berlaku, tautan, dan rumus turunan diselesaikan (siap dihitung metodenya)."""

    id: int
    metode: str
    jenis_indeks: str | None
    seri: dict[str, Seri]
    parameter: dict[str, float]
    out_k: Seri | None = None  # output ADHK langsung (margin arus barang); None = rumus metode biasa

    def s(self, kode: str) -> Seri:
        return self.seri.get(kode) or {}

    def p(self, kode: str) -> float | None:
        return self.parameter.get(kode)


@dataclass(frozen=True)
class Penyesuaian:
    """Hanya penyesuaian yang ikut angka resmi (status disetujui; keputusan 8a) dan mengubah angka."""

    tahap: str  # METODE | REKON | SIMULASI
    jenis: str  # ADJ1 ADJ2 SC | ADJ3 ADJ4_OUTPUT ADJ4_NTB | SIM_NTB
    harga: str  # CP | K
    periode: int  # urut
    nilai: float
    metode: str | None = None


@dataclass
class DataLapus:
    item: list[Item] = field(default_factory=list)
    penyesuaian: list[Penyesuaian] = field(default_factory=list)

    def berdata(self) -> bool:
        return any(i.metode in METODE_HITUNG for i in self.item) or bool(self.penyesuaian)


@dataclass(frozen=True)
class Lapus:
    """Satu baris pohon ref.lapus (hanya baris aktif)."""

    id: int
    kode: str
    jenis: str
    induk_id: int | None
    urutan: int
    is_migas: bool = False
    anggota: tuple[int, ...] = ()  # kelompok publikasi


@dataclass
class MasukanWilayah:
    konfig: KonfigTD
    sumbu: Sumbu  # periode putaran; diperluas otomatis agar mencakup T₀
    pohon: list[Lapus]
    data: dict[int, DataLapus]
    referensi: dict[str, Seri] = field(default_factory=dict)  # seri referensi wilayah ini, kunci = kode


@dataclass
class Empat:
    """Empat seri utama sepanjang sumbu."""

    out_cp: list[float]
    gva_cp: list[float]
    out_k: list[float]
    gva_k: list[float]

    @staticmethod
    def nol(n: int) -> Empat:
        return Empat([0.0] * n, [0.0] * n, [0.0] * n, [0.0] * n)

    def salin(self) -> Empat:
        return Empat(list(self.out_cp), list(self.gva_cp), list(self.out_k), list(self.gva_k))

    def tambah(self, lain: Empat) -> None:
        for a, b in ((self.out_cp, lain.out_cp), (self.gva_cp, lain.gva_cp), (self.out_k, lain.out_k),
                     (self.gva_k, lain.gva_k)):
            for t in range(len(a)):
                a[t] += b[t]

    def kurang(self, lain: Empat) -> Empat:
        return Empat([x - y for x, y in zip(self.out_cp, lain.out_cp, strict=True)],
                     [x - y for x, y in zip(self.gva_cp, lain.gva_cp, strict=True)],
                     [x - y for x, y in zip(self.out_k, lain.out_k, strict=True)],
                     [x - y for x, y in zip(self.gva_k, lain.gva_k, strict=True)])

    def besaran(self, kode: str) -> list[float]:
        return getattr(self, kode.lower())


@dataclass
class HasilLapus:
    tahap: dict[str, Empat] = field(default_factory=dict)  # PRE, POST, BENC, FINAL (agregat: BENC, FINAL)
    metode: dict[str, tuple[Empat, Empat]] = field(default_factory=dict)  # PR, PRE per metode
    item: dict[int, Empat] = field(default_factory=dict)
    hash_input: str = ""


@dataclass
class HasilWilayah:
    sumbu: Sumbu  # sumbu hitung (mencakup T₀); tulis hanya periode putaran
    lapus: dict[int, HasilLapus]
    urutan_hitung: list[int]
    versi_mesin: str = VERSI_MESIN
