# Rencana Mitigasi Class Imbalance (belum diimplementasikan)

Ditulis 2026-09-05, setelah run `finalcorpus` (width=0.50, fine-tune dari
`bigcorpus3`). Status: **rencana tersimpan, menunggu keputusan implementasi**
-- tidak mengubah apa pun di pipeline saat ini.

## Temuan yang melatarbelakangi

CER agregat run `finalcorpus` (0,43%, n=927) ternyata **menyembunyikan**
kegagalan besar pada simbol langka -- CER agregat adalah rata-rata yang
didominasi simbol umum (yang jumlahnya jauh lebih banyak di test set),
sehingga kegagalan pada simbol langka nyaris tidak terlihat di angka
tunggal itu.

Analisis stratifikasi (`stratified_cer.py`, akurasi per-simbol referensi
di test set, dikelompokkan berdasar seberapa sering simbol itu muncul di
TRAIN):

| Tingkat kelangkaan (kemunculan di train) | n di test | Akurasi |
|---|---|---|
| Tidak pernah muncul di train | 11 | **0,0%** |
| Sangat langka (<10x) | 61 | **85,2%** |
| Langka (10-99x) | 487 | 98,6% |
| Sedang (100-999x) | 3.544 | 99,9% |
| Umum (>=1000x) | 37.380 | 99,8% |

Gabungan 3 tingkat paling rawan (unseen+sangat langka+langka): 27 salah
dari 559 posisi = **~4,8% error** -- lebih dari 10x lipat dari CER agregat
0,43%.

Distribusi kemunculan simbol di seluruh train (17.456 kalimat, 869 kelas
simbol): rasio max/min **63.298x**, median cuma 36 kemunculan (rata-rata
806, tertarik oleh segelintir simbol super-umum). Kelangkaan berkorelasi
kuat dengan kompleksitas simbol (jumlah rarangkén yang menempel):

| Kompleksitas | Jumlah kelas | % kelas yang langka (<10x) |
|---|---|---|
| 1 codepoint (huruf dasar) | 40 | 0% |
| 2 codepoint (+1 rarangkén) | 284 | 13% |
| 3 codepoint (+2 rarangkén) | 489 | 43% |
| 4 codepoint (+3 rarangkén) | 56 | 82% |

Root cause: BUKAN kekurangan crop tulisan tangan (crop huruf dasar jumlahnya
rata di semua kelas, ~265/kelas) -- murni ledakan kombinatorial: makin
banyak rarangkén yang bisa menempel, makin banyak KELAS LABEL CTC berbeda
yang harus diwakili oleh jumlah kalimat yang sama.

Kasus konkret yang memicu investigasi ini: gambar uji "beureum" dari
internet (font digital asing) salah dibaca ᮘᮩ (ba+eu, 474 kemunculan di
train) sebagai ᮔ (na, 26.893 kemunculan) -- rasio 1:57 antara kedua
simbol itu.

## Rencana mitigasi (urutan prioritas: dampak besar/biaya kecil dulu)

### 1. Perbaiki logika split train/val/test (PRIORITAS TERTINGGI)
Split saat ini per-batch, modulo sederhana (mis. `i % 20 == 18/19` untuk
wikipedia_sunda, `i % 8 == 6/7` untuk budak_teuneung_fonts) -- tidak
peduli cakupan simbol langka. Perbaikan: sebelum split, identifikasi
simbol dengan kemunculan total rendah (mis. <100), **jamin train
kebagian representasi** simbol itu sebelum sisanya dibagi ke val/test.
Untuk simbol yang SANGAT jarang (<20 total), pertimbangkan semua
instance masuk train saja (tidak dievaluasi di val/test sama sekali --
sampel terlalu kecil untuk evaluasi bermakna).
Ini menghilangkan kegagalan "0% karena tidak pernah diajarkan" yang
murni kecelakaan pembagian, bukan kekurangan data sungguhan.
**Risiko: rendah. Tidak mengganggu training yang sedang berjalan** --
perubahan split cuma berlaku saat re-export manifest + training
berikutnya.

### 2. Cek keabsahan linguistik simbol paling langka
Sebelum berinvestasi memperbaiki tingkat 4-codepoint (82% langka),
verifikasi dulu: apakah 56 kelas ini benar-benar suku kata Sunda yang
valid, atau artefak transliterasi dari nama asing/istilah teknis di
artikel Wikipedia? Kalau artefak, tidak perlu diperjuangkan.

### 3. Pembobotan loss untuk simbol langka
CTC loss sulit diberi bobot per-simbol langsung (beroperasi di level
alignment path, bukan per-posisi sederhana). Jalur yang lebih mudah:
**aux decoder** (dilatih pakai cross-entropy, yang secara native
mendukung parameter `weight` per-kelas) -- naikkan bobot loss untuk
simbol langka di situ. Karena aux decoder berbagi representasi
CNN+BiLSTM dengan jalur CTC utama, sinyal belajar yang lebih kuat di
situ ikut menguntungkan jalur utama tanpa mengubah struktur CTC sama
sekali.

### 4. Render lebih banyak variasi untuk kalimat bersimbol langka
Manfaatkan render-multiplier yang sudah ada di compositor -- kalimat
yang mengandung simbol dari tingkat "sangat langka"/"langka" dirender
dengan variasi tulisan tangan lebih banyak dibanding kalimat biasa.
Menambah eksposur absolut tanpa perlu menyamaratakan seluruh distribusi
data secara paksa (yang berisiko merusak representasi frekuensi bahasa
asli).

### 5. Jadikan analisis stratifikasi sebagai laporan standar
Pakai `stratified_cer.py` (atau turunannya) di setiap training run
berikutnya, bukan cuma CER/WER agregat -- supaya perbaikan di atas bisa
diverifikasi dengan data, bukan diasumsikan berhasil.

## File terkait
- `stratified_cer.py` (scratchpad sesi ini) -- skrip analisis stratifikasi, load checkpoint + manifest test split, alignment Levenshtein dengan traceback per-posisi.
- Laporan visual ketimpangan kelas (artifact, dipublikasikan 2026-09-05): distribusi Zipf rank-frekuensi 869 simbol + breakdown kompleksitas.
