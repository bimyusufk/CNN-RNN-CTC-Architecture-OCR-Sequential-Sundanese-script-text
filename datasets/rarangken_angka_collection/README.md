# Koleksi tulisan tangan: rarangkén + angka Aksara Sunda

Tidak ada dataset publik/akademik yang menyediakan 13 rarangkén sebagai tanda
**terisolasi** (semua sumber yang ditemukan menggabungkannya dengan ngalagena,
mis. Widiastuti & Chandra 2026, JESTEC — 18 ngalagena x 7 rarangkén = 126 kelas
kombinasi) atau angka Sunda sama sekali. Ke-23 kelas ini harus dikumpulkan
sendiri. Folder ini berisi alat bantunya.

**Status 2026-08-27**: `angka_*` (10 kelas) dikesampingkan dulu atas
keputusan user — fokus koleksi saat ini hanya 13 kelas `rarangken_*`. Lembar
kerja `angka_*` tetap tersedia di `worksheets/` kalau nanti mau dilanjutkan;
tidak perlu dibuat ulang.

## Cara tercepat: gambar langsung di layar (rekomendasi kalau kerja sendiri)

```
python datasets/rarangken_angka_collection/draw_collect.py
```

Aplikasi desktop kecil (Tkinter, tidak perlu instalasi tambahan): gambar
pakai mouse di kanvas, tekan **Enter/Spasi** untuk simpan-lalu-bersihkan
otomatis — tidak ada dialog "save as", tidak perlu pilih folder atau ganti
nama file manual, semua langsung ke `datasets/aksara_sunda_full/<kelas>/`
dengan nama file otomatis. Glyph acuan (dari font, sama seperti di lembar
kerja) ditampilkan di sebelah kanan, plus penghitung progres per kelas.
Tombol panah kiri/kanan pindah kelas, Ctrl+Z undo goresan terakhir,
Backspace bersihkan tanpa simpan. Cocok untuk mengumpulkan banyak sampel
sendirian dengan cepat.

Ini melengkapi, bukan menggantikan, alur cetak-isi-scan di bawah — alur
cetak lebih pas kalau ingin melibatkan beberapa orang lain untuk variasi
gaya tulisan tangan (fisik, bisa dibagikan), sedangkan `draw_collect.py`
lebih pas untuk kamu sendiri mengisi cepat di depan komputer.

## Alur kerja (cetak - isi - scan, cocok untuk melibatkan banyak orang)

1. **Cetak** lembar kerja dari `worksheets/<nama_kelas>.pdf` (23 file, 6
   halaman/kelas @ 42 sel = ±252 sel/kelas). Bisa dicetak bertahap — tidak
   perlu 6 halaman sekaligus untuk mulai.
2. **Isi** setiap sel dengan pena hitam, **hanya bentuk tandanya** (rujuk
   glyph acuan di pojok kanan atas tiap halaman), variasikan gaya tulisan
   antar sel/orang supaya model tidak overfit ke satu gaya tangan.
3. **Scan tiap halaman pakai aplikasi scan HP** (Google Drive Scan, Adobe
   Scan, CamScanner, atau scanner flatbed kampus) — bukan foto mentah.
   Aplikasi ini otomatis meluruskan & memotong halaman jadi persegi panjang
   bersih, yang membuat langkah berikutnya jauh lebih akurat.
4. Simpan hasil scan ke `scans/<nama_kelas>/*.jpg` (nama file bebas).
5. Jalankan:
   ```
   python datasets/rarangken_angka_collection/crop_worksheets.py
   ```
   Setiap sel otomatis dipotong (posisi diketahui by construction — sama
   seperti baseline segmentasi trivial pada proposal skripsi), dibersihkan
   jadi biner hitam-putih, di-resize ke 224x224, dan disimpan ke
   `datasets/aksara_sunda_full/<nama_kelas>/`. Sel kosong (belum diisi)
   otomatis dilewati, jadi script ini aman dijalankan berulang setiap kali
   ada scan baru — tidak akan menambah gambar kosong.

## Kalau tidak pakai aplikasi scan (foto langsung/flatbed manual)

Script tetap mencoba mendeteksi 4 kotak hitam registrasi di sudut grid untuk
mengoreksi perspektif secara otomatis. Ini best-effort — pastikan ke-4 kotak
hitam sudut ikut terfoto dan halaman relatif rata/tidak terlalu miring. Kalau
`crop_worksheets.py` melaporkan "registrasi gagal", pakai aplikasi scan
seperti di langkah 3 di atas, jauh lebih andal.

## Pemetaan kelas -> Unicode Sundanese (U+1B80-1BBF, diverifikasi dari
Unicode Standard 17.0 chart resmi)

| Folder | Nama Unicode | Codepoint | Arti |
|---|---|---|---|
| rarangken_panghulu | VOWEL SIGN PANGHULU | U+1BA4 | a -> i |
| rarangken_panyuku | VOWEL SIGN PANYUKU | U+1BA5 | a -> u |
| rarangken_paneuleung | VOWEL SIGN PANEULEUNG | U+1BA9 | a -> eu |
| rarangken_paneleng | VOWEL SIGN PANAELAENG | U+1BA6 | a -> é |
| rarangken_panolong | VOWEL SIGN PANOLONG | U+1BA7 | a -> o |
| rarangken_pamepet | VOWEL SIGN PAMEPET | U+1BA8 | a -> e (pepet) |
| rarangken_panyecek | SIGN PANYECEK | U+1B80 | koda nasal "ng" (anusvara) |
| rarangken_panglayar | SIGN PANGLAYAR | U+1B81 | koda "r" (final r) |
| rarangken_pangwisad | SIGN PANGWISAD | U+1B82 | koda "h" (visarga) |
| rarangken_pamaeh | SIGN PAMAAEH | U+1BAA | mematikan vokal (virama) |
| rarangken_pamingkal | CONSONANT SIGN PAMINGKAL | U+1BA1 | medial "y" (subjoined ya) |
| rarangken_panyakra | CONSONANT SIGN PANYAKRA | U+1BA2 | medial "r" (subjoined ra) |
| rarangken_panyiku | CONSONANT SIGN PANYIKU | U+1BA3 | medial "l" (subjoined la) |
| angka_0 .. angka_9 | DIGIT ZERO .. NINE | U+1BB0-1BB9 | angka 0-9 |

Sumber: `unicode.org/charts/PDF/U1B80.pdf` (The Unicode Standard, v17.0).

## File pendukung

- `fonts/NotoSansSundanese.ttf` — font referensi (Google Fonts, Noto Sans
  Sundanese) dipakai untuk merender glyph acuan di tiap lembar kerja.
  Renderingnya lewat HarfBuzz (`uharfbuzz`) + FreeType (`freetype-py`) supaya
  tanda diakritik diposisikan dengan benar relatif ke lingkaran titik-titik
  (U+25CC DOTTED CIRCLE) acuannya — font-rendering naif (tanpa text shaping)
  akan salah menempatkan tanda ini.
- `generate_worksheets.py` — generator lembar kerja (regenerasi aman, hasilnya
  deterministik per kelas).
- `crop_worksheets.py` — pemroses hasil scan.
