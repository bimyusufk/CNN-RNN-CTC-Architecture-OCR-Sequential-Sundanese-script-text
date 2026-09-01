# -*- coding: utf-8 -*-
"""Orchestrator: baseline, then all 5 CRNN width-multiplier configs
(smallest -> largest), then writes a final RESULTS.md comparing everything.
Meant to run unattended for hours -- run in background, check RESULTS.md
when done (or logs/*.json for live per-epoch progress in the meantime).

Usage: python run_all.py
"""
import json
import os
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TRAINING_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_DIR = os.path.join(TRAINING_DIR, "logs")
RESULTS_PATH = os.path.join(TRAINING_DIR, "RESULTS.md")

WIDTHS = [0.25, 0.50, 0.75, 1.00, 1.50]
CRNN_EPOCHS = 120
CRNN_PATIENCE = 20
BASELINE_EPOCHS = 50
BASELINE_PATIENCE = 12


def run(cmd, label):
    print(f"\n{'='*70}\n{label}\n{'='*70}", flush=True)
    t0 = time.time()
    result = subprocess.run(cmd, cwd=TRAINING_DIR)
    elapsed = time.time() - t0
    status = "OK" if result.returncode == 0 else f"GAGAL (exit {result.returncode})"
    print(f"[{label}] {status}, {elapsed/60:.1f} menit", flush=True)
    return result.returncode == 0, elapsed


def main():
    overall_start = time.time()
    run_log = []

    ok, elapsed = run([sys.executable, "baseline_train.py",
                        "--epochs", str(BASELINE_EPOCHS), "--patience", str(BASELINE_PATIENCE)],
                       "BASELINE (trivial segmentation)")
    run_log.append({"stage": "baseline", "ok": ok, "elapsed_s": elapsed})

    for w in WIDTHS:
        ok, elapsed = run([sys.executable, "train_crnn.py",
                            "--width", str(w), "--epochs", str(CRNN_EPOCHS),
                            "--patience", str(CRNN_PATIENCE)],
                           f"CRNN width={w}")
        run_log.append({"stage": f"crnn_w{w:.2f}", "ok": ok, "elapsed_s": elapsed})

    total_elapsed = time.time() - overall_start
    print(f"\nSEMUA SELESAI dalam {total_elapsed/3600:.2f} jam. Menulis RESULTS.md...", flush=True)
    write_results_md(run_log, total_elapsed)


def load_json(path):
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def write_results_md(run_log, total_elapsed):
    lines = []
    lines.append("# Hasil Eksperimen: Baseline vs CRNN+CTC (Aksara Sunda Sekuensial)\n")
    lines.append(f"Dijalankan otomatis semalaman. Total waktu: {total_elapsed/3600:.2f} jam.\n")
    lines.append("Data: 801 kalimat NusaAksara (filtered), split 640/80/81 kalimat "
                  "(train/val/test), pool instans crop 80/20 (train/eval), render 8x/3x/3x.\n")

    lines.append("\n## Status tiap tahap\n")
    lines.append("| Tahap | Status | Waktu |\n|---|---|---|\n")
    for r in run_log:
        status = "OK" if r["ok"] else "**GAGAL**"
        lines.append(f"| {r['stage']} | {status} | {r['elapsed_s']/60:.1f} menit |\n")

    lines.append("\n## Baseline (segmentasi trivial, klasifikasi per-suku-kata)\n")
    base_test = load_json(os.path.join(LOG_DIR, "baseline_test.json"))
    base_hist = load_json(os.path.join(LOG_DIR, "baseline.json"))
    if base_test and base_hist:
        best_epoch = min(base_hist["history"], key=lambda h: h["cer"])
        lines.append(f"- Parameter: {base_hist['n_params']:,}\n")
        lines.append(f"- Kelas suku kata: {base_hist['n_classes']}\n")
        lines.append(f"- Val CER terbaik: {best_epoch['cer']:.4f} (epoch {best_epoch['epoch']})\n")
        lines.append(f"- **Test CER: {base_test['cer']:.4f}, WER: {base_test['wer']:.4f}, "
                      f"Exact match: {base_test['exact_match']:.4f}** (n={base_test['n']})\n")
    else:
        lines.append("- (data tidak tersedia -- kemungkinan tahap ini gagal, cek log)\n")

    lines.append("\n## CRNN+CTC per pengali lebar (Tabel 3.2)\n")
    lines.append("| Pengali | Parameter | Epoch terbaik | Val CER | Test CER | Test WER | Test Exact |\n")
    lines.append("|---|---|---|---|---|---|---|\n")
    crnn_results = []
    for w in WIDTHS:
        tag = f"w{w:.2f}"
        hist = load_json(os.path.join(LOG_DIR, f"crnn_{tag}.json"))
        test = load_json(os.path.join(LOG_DIR, f"crnn_{tag}_test.json"))
        if hist and test:
            best_epoch = min(hist["history"], key=lambda h: h["cer"])
            crnn_results.append({"width": w, "n_params": hist["n_params"], "test": test, "best_val": best_epoch})
            lines.append(f"| {w:.2f} | {hist['n_params']:,} | {best_epoch['epoch']} | "
                          f"{best_epoch['cer']:.4f} | {test['cer']:.4f} | {test['wer']:.4f} | "
                          f"{test['exact_match']:.4f} |\n")
        else:
            lines.append(f"| {w:.2f} | - | - | - | (gagal/belum selesai) | - | - |\n")

    lines.append("\n## Interpretasi\n")
    if base_test and crnn_results:
        best_crnn = min(crnn_results, key=lambda r: r["test"]["cer"])
        base_cer = base_test["cer"]
        best_cer = best_crnn["test"]["cer"]
        lines.append(f"- CRNN+CTC terbaik: pengali {best_crnn['width']:.2f} "
                      f"({best_crnn['n_params']:,} parameter), Test CER {best_cer:.4f}.\n")
        lines.append(f"- Baseline (segmentasi trivial): Test CER {base_cer:.4f}.\n")
        if best_cer < base_cer:
            lines.append(f"- **CRNN+CTC mengungguli baseline** ({best_cer:.4f} < {base_cer:.4f}) -- model "
                          "belajar sesuatu di luar sekadar klasifikasi per-suku-kata terisolasi "
                          "(mis. konteks antar-suku-kata via BiLSTM), bukan cuma soal data cukup/tidak.\n")
        else:
            lines.append(f"- **CRNN+CTC BELUM mengungguli baseline** ({best_cer:.4f} >= {base_cer:.4f}). "
                          "Karena baseline pakai segmentasi yang diketahui persis (bukan trik), sedangkan "
                          "CRNN+CTC harus belajar menyelaraskan sendiri (alignment-free), ini mengindikasikan "
                          "MASALAH TRAINING/ARSITEKTUR CTC (mis. kurang epoch, learning rate, atau sequence "
                          "length T=W/4 terlalu pendek untuk vocabulary 349 kelas) -- BUKAN otomatis berarti "
                          "datanya kurang, karena baseline dengan data yang sama (dan volume data latih yang "
                          "sama besarnya) sudah bisa lebih baik.\n")

        widths_sorted = sorted(crnn_results, key=lambda r: r["width"])
        increasing = all(widths_sorted[i]["test"]["cer"] >= widths_sorted[i+1]["test"]["cer"] * 0.98
                          for i in range(len(widths_sorted)-1))
        lines.append(f"\n- Soal hipotesis 'aksara Sunda lebih rumit, mungkin butuh model lebih besar': "
                      f"lihat kolom Test CER pada tabel di atas dari pengali 0.25 ke 1.50. ")
        if widths_sorted[-1]["test"]["cer"] < widths_sorted[0]["test"]["cer"]:
            lines.append("Pengali terbesar (1.50) mengungguli pengali terkecil (0.25) -- ada indikasi "
                          "kapasitas lebih besar membantu, konsisten dengan hipotesis tersebut.\n")
        else:
            lines.append("Pengali terbesar (1.50) TIDAK mengungguli yang terkecil (0.25) di sini -- "
                          "kapasitas model kemungkinan bukan bottleneck utama saat ini (lebih mungkin "
                          "soal volume/keragaman data atau training), jadi menaikkan ukuran model dulu "
                          "belum tentu prioritas paling efektif.\n")
    else:
        lines.append("- Data belum cukup untuk interpretasi (ada tahap yang gagal, cek tabel status di atas "
                      "dan log mentah di training/logs/).\n")

    lines.append("\n## Catatan jujur / batasan\n")
    lines.append("- Seluruh data latih synthetic (karakter asli, disusun algoritmik) -- generalisasi ke "
                  "dokumen tulisan tangan Sunda sungguhan belum diuji di sini, di luar scope run ini.\n")
    lines.append("- OOV terhadap vocabulary train (diukur sebelumnya): val 0.9% instans simbol, test 1.8% -- "
                  "sebagian kecil kesalahan CER pada test TIDAK bisa dihindari model manapun.\n")
    lines.append("- Vocabulary CTC (349 simbol) diturunkan murni dari 640 kalimat train, bukan dienumerasi.\n")

    with open(RESULTS_PATH, "w", encoding="utf-8") as f:
        f.writelines(lines)
    print(f"RESULTS.md ditulis ke {RESULTS_PATH}")


if __name__ == "__main__":
    main()
