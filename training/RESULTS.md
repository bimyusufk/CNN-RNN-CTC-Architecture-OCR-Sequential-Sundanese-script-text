# Hasil Eksperimen: Baseline vs CRNN+CTC (Aksara Sunda Sekuensial)
Dijalankan otomatis semalaman. Total waktu: 2.12 jam.
Data: 801 kalimat NusaAksara (filtered), split 640/80/81 kalimat (train/val/test), pool instans crop 80/20 (train/eval), render 8x/3x/3x.

## Status tiap tahap
| Tahap | Status | Waktu |
|---|---|---|
| baseline | OK | 2.3 menit |
| crnn_w0.25 | OK | 30.0 menit |
| crnn_w0.50 | OK | 27.3 menit |
| crnn_w0.75 | OK | 30.6 menit |
| crnn_w1.00 | OK | 18.6 menit |
| crnn_w1.50 | OK | 18.7 menit |

## Baseline (segmentasi trivial, klasifikasi per-suku-kata)
- Parameter: 285,852
- Kelas suku kata: 348
- Val CER terbaik: 0.0332 (epoch 38)
- **Test CER: 0.0484, WER: 0.1092, Exact match: 0.7407** (n=81)

## CRNN+CTC per pengali lebar (Tabel 3.2)
| Pengali | Parameter | Epoch terbaik | Val CER | Test CER | Test WER | Test Exact |
|---|---|---|---|---|---|---|
| 0.25 | 2,365,742 | 53 | 0.0720 | 0.1168 | 0.2362 | 0.5062 |
| 0.50 | 2,476,542 | 45 | 0.0496 | 0.0641 | 0.1452 | 0.6255 |
| 0.75 | 2,617,294 | 51 | 0.0424 | 0.0724 | 0.1479 | 0.6502 |
| 1.00 | 2,787,998 | 23 | 0.0509 | 0.0720 | 0.1439 | 0.6502 |
| 1.50 | 3,219,262 | 21 | 0.0434 | 0.0871 | 0.1703 | 0.6255 |

## Interpretasi

**PERBAIKAN dari ringkasan otomatis di atas**: skrip `run_all.py` menulis kesimpulan soal hipotesis ukuran model dengan cara yang menyesatkan (cuma membandingkan 0.25 vs 1.50, dua ujungnya saja). Setelah saya periksa manual seluruh kurva dan histori per-epoch, gambarannya berbeda -- bagian ini menggantikan interpretasi otomatis di atas.

**1. Tidak ada CRNN+CTC yang mengungguli baseline** (terbaik 0.0641 vs baseline 0.0484). Ini WAJAR untuk percobaan pertama tanpa tuning apa pun (belum ada learning-rate scheduler, belum ada augmentasi) -- CTC memang tugas lebih sulit (harus belajar penjajaran sendiri) dibanding klasifikasi dengan posisi yang sudah diketahui. Bukan tanda kegagalan, tapi juga belum jadi bukti kuat "datanya kurang" -- baseline dengan volume data latih yang SAMA sudah jauh lebih baik, jadi datanya sendiri cukup informatif; masalahnya lebih ke arah proses training CTC-nya.

**2. Hipotesis "aksara Sunda lebih rumit, butuh model lebih besar" -- TIDAK didukung data ini.** Urutan Test CER dari kecil ke besar pengali: 0,25→**0,1168** (terburuk) → 0,50→**0,0641** (TERBAIK) → 0,75→0,0724 → 1,00→0,0720 → 1,50→0,0871 (terburuk kedua). Ini pola **U-shape**, bukan "makin besar makin baik": 0,25 memang terlalu kecil (jelas kurang kapasitas), tapi begitu lewat 0,50 performa justru **menurun lagi** sampai 1,50. Pengali 1,50 (parameter TERBANYAK, 3,2 juta) hasilnya lebih buruk dari 0,50 (2,5 juta) DAN dari 0,75 DAN dari 1,00. Kalau cuma lihat ujung-ujungnya (0,25 vs 1,50) memang kelihatan "1,50 menang", tapi itu mengabaikan bahwa 0,50 mengalahkan 1,50 dengan selisih cukup jauh (0,0641 vs 0,0871). Kesimpulan yang lebih akurat: **ada titik jenuh kapasitas di sekitar 0,50-0,75; menambah ukuran model lagi (ke 1,00 apalagi 1,50) tidak membantu dan cenderung sedikit merugikan** -- kemungkinan overfitting (lihat poin 3), bukan kekurangan kapasitas.

**3. Temuan metodologis paling actionable: SEMUA konfigurasi overfit dan tidak ada learning-rate scheduling.** Saya periksa histori loss per-epoch: train_loss turun ke ~0,000-0,001 (hafal set latih nyaris sempurna) sudah sejak epoch ~15-20 di SEMUA konfigurasi, sementara val CER berosilasi naik-turun secara tidak stabil sesudahnya (mis. width=0,75 val CER melonjak dari 0,043 ke 0,204 di epoch 26 lalu turun lagi; width=1,50 melonjak ke 0,478 di epoch 11). Ini pola klasik: model sudah konvergen/hafal, learning rate tetap (1e-3, tidak pernah diturunkan) membuatnya "memantul" di sekitar minimum tanpa menetap. **Ini kemungkinan perbaikan paling berdampak untuk iterasi berikutnya** -- tambahkan LR scheduler (mis. ReduceLROnPlateau atau cosine annealing) -- kemungkinan lebih berpengaruh ke akurasi akhir daripada memilih pengali lebar yang mana.

**4. Perbedaan antar 0,50/0,75/1,00 kemungkinan berada dalam rentang noise.** Val set cuma 80 kalimat, test 81 -- japat kecil untuk CER di kisaran 5-7%. Sebagai pembanding: ranking terbaik di VAL (0,75 menang, 0,0424) beda dengan ranking di TEST (0,50 menang, 0,0641) -- ketidakkonsistenan ini sendiri adalah sinyal bahwa selisih di rentang itu belum tentu signifikan secara statistik dengan set seukuran ini. Yang robust dari data ini cuma dua hal: (a) 0,25 jelas paling buruk, (b) tidak satu pun konfigurasi mengungguli baseline.

**Rekomendasi konkret untuk lanjutan**: pengali **0,50** adalah pilihan Pareto paling masuk akal sekarang (parameter tersedikit di antara yang "cukup besar", CER test terbaik) -- BUKAN karena ukurannya, tapi karena efisiensinya. Prioritas perbaikan berikutnya: (1) tambahkan LR scheduler, (2) lebih banyak epoch dengan scheduler tsb (early stopping mungkin memotong terlalu dini sebelum scheduler sempat membantu), (3) baru pertimbangkan menambah data/augmentasi kalau #1-2 belum cukup.

## Catatan jujur / batasan
- Seluruh data latih synthetic (karakter asli, disusun algoritmik) -- generalisasi ke dokumen tulisan tangan Sunda sungguhan belum diuji di sini, di luar scope run ini.
- OOV terhadap vocabulary train (diukur sebelumnya): val 0.9% instans simbol, test 1.8% -- sebagian kecil kesalahan CER pada test TIDAK bisa dihindari model manapun.
- Vocabulary CTC (349 simbol) diturunkan murni dari 640 kalimat train, bukan dienumerasi.
