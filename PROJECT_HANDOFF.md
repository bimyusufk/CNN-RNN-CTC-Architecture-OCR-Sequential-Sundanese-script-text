# Ringkasan Konteks Proyek (untuk sesi Claude baru / device baru)

Ditulis 2026-09-11. Ini bukan dokumentasi permanen proyek (itu ada di
README.md/DATA_PIPELINE.md/RESULTS.md) -- ini catatan **status kerja
saat ini** supaya sesi Claude baru bisa langsung paham tanpa membaca
ulang seluruh riwayat percakapan.

## Identitas proyek

Skripsi S1 Teknik Informatika Unpad: "Pencarian Model Pareto-Optimal
Akurasi, Latensi, dan Ukuran Model pada Pengenalan Karakter Optik
Sekuensial Aksara Sunda". Arsitektur inti **wajib CRNN+CTC** (batasan
judul) -- LR scheduler, aux decoder, augmentasi semuanya cuma bantuan
training yang dibuang saat inferensi.

## Checkpoint mana yang "terbaik" sekarang -- BELUM final, masih keputusan terbuka

| Checkpoint | Test CER | Catatan |
|---|---|---|
| `crnn_w0.50_finalcorpus_best.pt` | **0,43%** | Kandidat terkuat saat ini -- lemah cuma di ekor distribusi (simbol langka) |
| `crnn_w1.00_finalcorpus_best.pt` | 0,41% (agregat) | Menang tipis di agregat TAPI kalah di 3 dari 4 tingkat kelangkaan non-trivial (lihat `stratified_cer_w1.00.json`) -- jangan tertipu angka agregat |
| `crnn_w0.50_imbalancefix_best.pt` | 0,96% | **Eksperimen gagal-terkendali** -- loss-reweighting memperbaiki simbol sangat-langka (85%→100%) tapi merusak tingkat umum/sedang, CER agregat memburuk. Disimpan sebagai catatan, BUKAN direkomendasikan sebagai model produksi. |

**Rencana yang sedang berjalan** (lihat `training/CLASS_IMBALANCE_PLAN.md`):
pendekatan loss-reweighting sudah terbukti kurang berhasil secara neto.
Arah berikutnya yang disepakati: **data-level oversampling** (naikkan
render-multiplier khusus kalimat bersimbol langka) sebagai pengganti,
BUKAN pelengkap, loss-reweighting -- ini **belum diimplementasikan**.

## Temuan besar sesi ini (kronologis, paling relevan untuk Bab IV skripsi)

1. **Class imbalance ekstrem ditemukan**: rasio kemunculan simbol
   tersering:terjarang = 63.298:1 di ruang label CTC (869 kelas).
   Berkorelasi kuat dengan kompleksitas simbol (0% kelas langka pada
   huruf dasar, 82% pada kombinasi 3-rarangkén) -- akibat ledakan
   kombinatorial, bukan kekurangan crop tulisan tangan.
2. **CER agregat menyembunyikan kegagalan ekor**: dipecah per-tingkat
   kelangkaan (`stratified_cer.py`), simbol yang tidak pernah muncul di
   train = 0% akurasi, simbol sangat langka = 85%, vs simbol umum 99,8%
   -- padahal CER agregat cuma 0,43%.
3. **Gap generalisasi font dibuktikan nyata**: gambar Aksara Sunda dari
   internet (font italic asing) awalnya gagal total (CER 166,7%,
   salah baca jadi angka Sundanese -- kelas dengan crop paling sedikit).
   Setelah menambah batch font-rendered (novel "Budak Teuneung" via 4
   font asli terverifikasi), membaik ke CER 33,3%.
4. **Perbaikan split berhasil bersih** (beda dari loss-reweighting):
   `fix_split_rare_coverage.py` menjamin tiap simbol di val/test
   minimal punya 1 kemunculan di train -- BERHASIL tanpa merugikan
   tingkat lain sama sekali.

## Yang BELUM dikerjakan / keputusan tertunda

- [ ] Implementasi data-level oversampling untuk kalimat bersimbol langka
- [ ] Keputusan: apakah `imbalancefix` dibuang, atau dicoba ulang dengan
      pembobotan lebih lembut setelah oversampling data diterapkan
- [ ] Validasi pada data NYATA (bukan sintetis) -- masih prioritas
      tertinggi yang belum tersentuh, cuma 2 gambar internet sejauh ini
- [ ] Segmentasi baris teks (line detection) -- belum ada sama sekali,
      diperlukan untuk deployment pada dokumen/foto utuh
- [ ] Benchmark latensi & ukuran model -- judul skripsi menyebutnya
      eksplisit, belum ada pengukuran formal

## File kunci untuk orientasi cepat

- `README.md` -- struktur repo, setup
- `datasets/DATA_PIPELINE.md` -- alur data awam-friendly
- `training/RESULTS.md` -- semua hasil eksperimen training (kronologis)
- `training/CLASS_IMBALANCE_PLAN.md` -- rencana + evidensi class imbalance
- `datasets/synthesis/corpus.db` -- single source of truth data (SQLite)

## Yang TIDAK ada di git (perlu dipindah manual / diunduh ulang)

- `training/checkpoints/*.pt` -- lihat daftar prioritas di bawah
- `datasets/rarangken_angka_collection/fonts/font_synthesis/` -- font
  pihak ketiga (Caringin, Gede Pangrango: lisensi CC BY-NC-ND; Sundanese
  Unicode 2013: lisensi komunitas tidak jelas) -- sumber unduhan sudah
  dicatat dalam riwayat percakapan sesi sebelumnya, belum didokumentasikan
  ulang di file manapun -- **catatan untuk sesi mendatang: pertimbangkan
  menulis sumber unduhannya ke DATA_PIPELINE.md supaya tidak hilang jejak**
