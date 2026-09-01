# Alur Data: Dari Tulisan Tangan sampai Data Latih Model

Dokumen ini menjelaskan **dari mana data kita berasal, bagaimana data itu
diproses, dan bagaimana kita tahu mana yang sebenarnya dipakai** —
ditulis supaya bisa dipahami tanpa perlu paham kode Python.

---

## Ringkasan singkat

```
Karakter tulisan tangan  →  Compositor (perangkai)  →  Kalimat jadi citra
        ↑                                                      ↑
   (dikumpulkan manual)                              (dari 2 jenis sumber)
                                                       ↓
                                        ┌──────────────┴──────────────┐
                                   NusaAksara                  Artikel Wikipedia
                                (kalimat Sunda asli,          (diterjemahkan mesin
                                 801 kalimat)                  ke bahasa Sunda)
                                                                       ↓
                                                              Kurasi otomatis
                                                            (saring yang bermasalah)
                                                                       ↓
                                                          corpus.db (sumber kebenaran)
                                                                       ↓
                                                   manifest.csv + vocab.json (untuk training)
```

---

## Tahap 1 — Mengumpulkan karakter dasar (kerja manual)

Model kita tidak "tahu" bagaimana rupa Aksara Sunda dari awal. Semuanya
dimulai dari **mengumpulkan contoh tulisan tangan** untuk tiap karakter:

- **Swara** (huruf vokal mandiri): a, i, u, é, o, e, eu — 7 karakter
- **Ngalagena** (huruf konsonan dasar): ka, ga, nga, ca, dst — 23 karakter
- **Rarangkén** (tanda diakritik yang menempel ke konsonan, mengubah
  bunyi vokalnya, atau menandai konsonan penutup suku kata) — 13 jenis
- **Angka** (0-9) — 10 karakter

Setiap karakter digambar berulang kali dengan variasi bentuk tulisan
tangan (target awal 250 contoh per kelas), memakai alat gambar sendiri
(`datasets/rarangken_angka_collection/draw_collect.py`) yang punya
panduan transparan di kanvas, slider ketebalan kuas, dan preview
kalimat sebelum/sesudah untuk mempercepat proses menggambar.

**Kenapa manual, bukan pakai font komputer saja?** Karena tujuan
akhirnya adalah OCR untuk tulisan tangan / hasil scan yang bervariasi —
kalau cuma dilatih dari font digital yang seragam, model tidak akan
terbiasa dengan variasi bentuk tulisan tangan asli.

---

## Tahap 2 — Compositor: merangkai karakter jadi kalimat

`compositor.py` adalah "perakit" yang mengambil crop karakter tulisan
tangan tadi dan menyusunnya jadi kalimat utuh:

1. Baca teks Aksara Sunda (atau hasil transliterasi dari teks Latin),
   pecah jadi rangkaian suku kata (konsonan + tanda-tanda yang menempel).
2. Untuk tiap suku kata, ambil **crop fisik acak** dari koleksi tulisan
   tangan yang cocok (misal untuk suku kata "ka", ambil salah satu dari
   ratusan contoh tulisan tangan huruf "ka" yang ada).
3. Posisikan tanda-tanda diakritik dengan tepat — diukur langsung dari
   geometri font referensi (bukan angka yang dikira-kira), supaya posisi
   menempelnya realistis.
4. Rangkai semua suku kata jadi satu citra kalimat panjang.

Karena crop-nya diambil **acak** tiap kali suatu suku kata dirender,
kalimat yang sama bisa dirender berkali-kali dan menghasilkan citra yang
**berbeda secara visual** setiap kali (kombinasi tulisan tangan yang
berbeda) — ini yang disebut *render multiplier*, cara memperbanyak
keragaman visual data latih tanpa perlu menggambar lebih banyak
karakter dasar.

---

## Tahap 3 — Sumber kalimat: dari mana teksnya berasal

Compositor butuh TEKS untuk dirangkai jadi citra. Ada dua jenis sumber:

### 3a. NusaAksara (sumber asli, tepercaya penuh)
801 kalimat cerita rakyat Sunda dari korpus akademik NusaAksara — sudah
berupa Aksara Sunda asli (bukan hasil terjemahan), jadi **tidak perlu
divalidasi ulang**. Ini fondasi data kita yang paling bisa dipercaya.

### 3b. Pengayaan lewat terjemahan mesin (perlu tinjauan lebih hati-hati)
Karena 801 kalimat itu jenis ceritanya sempit (cerita rakyat sehari-hari),
kita perkaya dengan artikel sejarah Indonesia dari Wikipedia (50 artikel,
prasejarah sampai zaman kolonial), yang **aslinya berbahasa Indonesia**,
lalu diterjemahkan otomatis ke bahasa Sunda pakai **NLLB-200** (model
terjemahan mesin gratis, jalan di komputer sendiri, tanpa biaya).

Teks Sunda hasil terjemahan ini lalu diubah jadi Aksara Sunda lewat
**transliterator** — program yang menerjemahkan ejaan huruf Latin Sunda
jadi karakter Aksara Sunda yang benar (dibangun dari aturan resmi
Unicode, sudah diuji akurat >99% pada kalimat NusaAksara yang sudah
tahu jawaban benarnya).

**Kenapa ini butuh perlakuan berbeda?** Karena hasil terjemahan mesin
bisa saja salah/tidak wajar — belum ada penutur asli yang memeriksanya.
Makanya batch ini ditandai statusnya berbeda di database (lihat Tahap 5).

---

## Tahap 4 — Kurasi otomatis: apa yang disaring, dan kenapa

Tidak semua kalimat yang berhasil diterjemahkan otomatis lolos dipakai.
Ada beberapa saringan otomatis, masing-masing dengan alasan teknis:

| Saringan | Kenapa perlu |
|---|---|
| **Kalimat identik dengan sumber Indonesia** | Berarti mesin terjemahan gagal total, bukan Aksara Sunda sungguhan |
| **Mengandung aksara asing** (Arab, Jawa, dsb) | Beberapa artikel menyisipkan kutipan naskah kuno dalam aksara lain — bukan bahasa Indonesia/Sunda yang bisa diterjemahkan |
| **Kalimat gagal dirender** | Kata yang mengandung karakter yang belum ada datanya (misal angka "0", belum ada contoh tulisan tangannya) |
| **Batasan panjang simbol (250 simbol)** | Kalimat yang sangat panjang membuat model "auxiliary decoder" (bantu latihan) butuh memori berlebihan |
| **Batasan lebar citra (2000 piksel)** | Ini yang paling penting: kalimat sangat panjang menghasilkan citra sangat lebar, yang kalau digabung dalam satu batch training bisa membuat memori GPU penuh dan training crash. Ditemukan lewat pemantauan langsung saat training berjalan (lihat riwayat di `filter_events`). |

**Semua kalimat yang disaring TETAP TERSIMPAN** (bukan dihapus) — cuma
ditandai statusnya di database, lengkap dengan alasan dan angka batasnya.
Jadi kalau nanti kita tambah data crop angka "0" misalnya, kita bisa
lihat persis kalimat mana saja yang tadinya gagal karena itu, dan
proses ulang tanpa kehilangan jejak.

---

## Tahap 5 — `corpus.db`: satu tempat kebenaran, bukan banyak file terpisah

Sebelumnya, tiap batch data (NusaAksara, artikel sejarah, dst) punya file
`manifest.csv` sendiri-sendiri. Masalahnya: begitu satu file diperbarui
(digabung, disaring) tapi yang lain tidak, **file-file itu jadi tidak
sinkron** — informasi yang saling bertentangan, tidak jelas mana yang
benar. Sekarang semuanya konsolidasi jadi **satu database**
(`datasets/synthesis/corpus.db`, format SQLite — satu file, tidak perlu
software server, bisa dibuka pakai banyak tool gratis).

### Enam "buku catatan" di dalam database ini

1. **`source_batches`** — daftar dari mana tiap kelompok data berasal:
   apakah asli atau hasil terjemahan mesin (dan mesin apa), kapan dibuat,
   sudah ditinjau manusia atau belum.
2. **`sentences`** — satu baris per kalimat unik: teksnya, label karakter
   Aksara Sunda-nya, masuk split train/val/test yang mana, dan status
   (aktif dipakai, atau disaring dengan alasan apa).
3. **`images`** — satu baris per file citra hasil render (satu kalimat
   bisa punya banyak citra, hasil render-multiplier).
4. **`vocab_symbols`** — daftar simbol (suku kata Aksara Sunda) yang
   dikenal model, lengkap dengan batch mana yang pertama kali
   memunculkannya.
5. **`filter_events`** — catatan permanen tiap kali sebuah kalimat
   disaring/dikeluarkan: kapan, kenapa, dengan batas angka berapa.
6. **`training_runs`** — riwayat setiap percobaan training yang pernah
   dijalankan, terikat ke kondisi data persis saat itu, supaya hasil
   eksperimen bisa dilacak balik ke data apa yang sebenarnya dipakai.

### Kenapa ini tidak memperlambat training

Database ini **hanya dibaca sekali di awal** setiap sesi training (satu
kali ambil semua data aktif, disimpan di memori komputer) — bukan
dibaca berulang-ulang selama training berjalan. Jadi secanggih apa pun
isinya, tidak pernah jadi penghambat kecepatan.

### Bagaimana `manifest.csv`/`vocab.json` sekarang diperlakukan

File-file itu **masih ada dan masih dipakai kode training** — tapi
sekarang statusnya "hasil ekspor" dari database, bukan lagi sumber asli.
Kalau ada perubahan kurasi di database, jalankan:

```
python datasets/synthesis/export_manifest.py
```

untuk memperbarui `manifest.csv`/`vocab.json` supaya sinkron kembali.

---

## Contoh pertanyaan yang sekarang bisa dijawab langsung dari database

*(pakai `sqlite3 datasets/synthesis/corpus.db` di terminal, atau tool
GUI gratis seperti DB Browser for SQLite kalau tidak familiar command line)*

- **"Berapa kalimat yang benar-benar dipakai untuk training sekarang?"**
  → `SELECT split, COUNT(*) FROM sentences WHERE status='active' GROUP BY split;`
- **"Kenapa data dari artikel sejarah berkurang dari 7.497 jadi 5.174?"**
  → `SELECT event_type, COUNT(*) FROM filter_events GROUP BY event_type;`
- **"Kosakata mana saja yang pertama kali muncul dari data terjemahan
  mesin (bukan dari NusaAksara)?"**
  → `SELECT symbol FROM vocab_symbols WHERE first_seen_batch_id != 1;`
- **"Bagaimana hasil semua percobaan training sejauh ini?"**
  → `SELECT tag, test_cer, test_wer FROM training_runs ORDER BY test_cer;`

---

## Istilah singkat

| Istilah | Artinya |
|---|---|
| **Manifest** | Daftar/katalog — dalam konteks ini, daftar semua citra yang dipakai untuk melatih model |
| **Split** | Pembagian data jadi train (untuk belajar), val (untuk memantau selama latihan), test (untuk nilai akhir, tidak pernah dilihat model) |
| **CTC** | Metode pelatihan yang memungkinkan model belajar membaca urutan karakter tanpa perlu tahu persis di piksel mana tiap karakter berada |
| **Transliterasi** | Mengubah ejaan dari satu sistem tulisan ke sistem tulisan lain berdasarkan bunyi (di sini: Latin → Aksara Sunda) |
| **SQLite** | Jenis database yang tidak butuh instalasi software server — cuma satu file, bisa dibawa/disalin seperti dokumen biasa |
