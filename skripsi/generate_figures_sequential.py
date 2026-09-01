# -*- coding: utf-8 -*-
"""Generate the 5 missing figures for the sequential Aksara Sunda OCR skripsi proposal.

Outputs (skripsi/figures/):
  gambar_2_1_ctc_pemetaan.png
  gambar_2_2_pareto_frontier.png
  gambar_3_1_diagram_alir_penelitian.png
  gambar_3_2_sintesis_data.png
  gambar_3_3_arsitektur_crnn.png
"""
import os
import random
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch, Rectangle
from PIL import Image

random.seed(7)
np.random.seed(7)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIG_DIR = os.path.join(ROOT, "skripsi", "figures")
DATA_DIR = os.path.join(ROOT, "datasets", "aksara_sunda", "train")
os.makedirs(FIG_DIR, exist_ok=True)

plt.rcParams["font.family"] = "serif"
plt.rcParams["font.serif"] = ["Times New Roman", "DejaVu Serif", "Georgia"]

# ---- shared palette (matched to skripsi/figures/gambar_3_1_arsitektur.png style) ----
BLUE_FILL, BLUE_EDGE = "#dbe7f5", "#2e6da4"
GREEN_FILL, GREEN_EDGE = "#dff0d8", "#4a7a3d"
GRAY_FILL, GRAY_EDGE = "#f0f0f0", "#595959"
RED_EDGE = "#b32b2b"
TEXT_DARK = "#1a1a1a"
TEXT_GRAY = "#404040"
DIM_BLUE = "#2e6da4"


def box(ax, x, y, w, h, text, fc=BLUE_FILL, ec=BLUE_EDGE, fs=15, lw=1.6,
        weight="normal", style="square", text_color=TEXT_DARK, dashed=False):
    boxstyle = "round,pad=0.006,rounding_size=0.02" if style == "round" else "square,pad=0.0"
    p = FancyBboxPatch((x, y), w, h, boxstyle=boxstyle, linewidth=lw,
                        edgecolor=ec, facecolor=fc,
                        linestyle="dashed" if dashed else "solid")
    ax.add_patch(p)
    ax.text(x + w / 2, y + h / 2, text, ha="center", va="center",
             fontsize=fs, color=text_color, weight=weight, linespacing=1.3)
    return p


def arrow(ax, x0, y0, x1, y1, color="#333333", lw=1.6, style="-|>", connectionstyle=None):
    a = FancyArrowPatch((x0, y0), (x1, y1), arrowstyle=style, mutation_scale=14,
                         linewidth=lw, color=color, shrinkA=0, shrinkB=0,
                         connectionstyle=connectionstyle)
    ax.add_patch(a)
    return a


def new_ax(figsize, dpi=150):
    fig = plt.figure(figsize=figsize, dpi=dpi)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    return fig, ax


def save(fig, name):
    path = os.path.join(FIG_DIR, name)
    fig.savefig(path, dpi=fig.dpi, facecolor="white")
    plt.close(fig)
    print("saved", path)


# =====================================================================
# GAMBAR 2.1 -- Pemetaan banyak-ke-satu pada CTC
# =====================================================================
def make_gambar_2_1():
    fig, ax = new_ax((16, 6), dpi=150)
    ax.set_xlim(0, 16)
    ax.set_ylim(0, 6)

    ax.text(8, 5.55, "Pemetaan Banyak-ke-Satu pada Connectionist Temporal Classification",
            ha="center", va="center", fontsize=19, weight="bold", color=TEXT_DARK)

    stage_a = ["k", "k", "ε", "a", "a", "ε", "t", "a", "a"]
    stage_b = ["k", "ε", "a", "ε", "t", "a"]

    bw, bh, gap = 0.62, 0.62, 0.12
    y_row = 3.55

    def draw_row(tokens, x_start, y):
        xs = []
        for i, t in enumerate(tokens):
            x = x_start + i * (bw + gap)
            is_blank = t == "ε"
            box(ax, x, y, bw, bh, t,
                fc=GRAY_FILL if is_blank else BLUE_FILL,
                ec=GRAY_EDGE if is_blank else BLUE_EDGE,
                fs=17, lw=1.4, dashed=is_blank)
            xs.append(x + bw / 2)
        return xs

    total_a = len(stage_a) * (bw + gap) - gap
    xA0 = 0.5
    xsA = draw_row(stage_a, xA0, y_row)
    ax.text(xA0 + total_a / 2, y_row + bh + 0.32,
            "Barisan token per-langkah-waktu ($\\pi$)", ha="center", va="bottom",
            fontsize=13.5, color=TEXT_GRAY, style="italic")

    total_b = len(stage_b) * (bw + gap) - gap
    xB0 = xA0 + total_a + 1.9
    xsB = draw_row(stage_b, xB0, y_row)
    ax.text(xB0 + total_b / 2, y_row + bh + 0.32,
            "Setelah pengulangan berturutan digabung", ha="center", va="bottom",
            fontsize=13.5, color=TEXT_GRAY, style="italic")

    arrow(ax, xA0 + total_a + 0.12, y_row + bh / 2, xB0 - 0.12, y_row + bh / 2,
          color=RED_EDGE, lw=2.0)
    ax.text(xA0 + total_a + (xB0 - xA0 - total_a) / 2, y_row - 0.28,
            "gabungkan pengulangan\nberturutan", ha="center", va="top",
            fontsize=12.5, color=RED_EDGE, weight="bold", linespacing=1.3)

    xC0 = xB0 + total_b / 2 - 1.1
    yC = y_row - 2.05
    box(ax, xC0, yC, 2.2, 0.85, "kata", fc=GREEN_FILL, ec=GREEN_EDGE, fs=22, weight="bold")
    ax.text(xC0 + 1.1, yC - 0.32,
            "Label barisan akhir ($y$)", ha="center", va="top",
            fontsize=13.5, color=TEXT_GRAY, style="italic")

    arrow(ax, xB0 + total_b / 2, y_row - 0.12, xC0 + 1.1, yC + 0.85 + 0.12,
          color=RED_EDGE, lw=2.0)
    ax.text(xB0 + total_b / 2 + 1.35, (y_row + yC + 0.85) / 2 + 0.05,
            "buang token\nkosong ($\\varepsilon$)", ha="left", va="center",
            fontsize=12.5, color=RED_EDGE, weight="bold", linespacing=1.3)

    ax.text(8, 0.55,
            "Fungsi $\\mathcal{B}:\\Sigma'^{T}\\rightarrow \\Sigma^{\\leq T}$ memetakan setiap barisan token per-langkah-waktu ke satu label unik dengan\n"
            "menggabungkan pengulangan simbol yang berdekatan lalu menghapus token kosong ($\\varepsilon$); banyak barisan $\\pi$ berbeda dapat\n"
            "menghasilkan label $y$ yang sama, sehingga model dilatih tanpa memerlukan penjajaran eksplisit antara citra dan label.",
            ha="center", va="center", fontsize=12.5, color=TEXT_GRAY, linespacing=1.55)

    save(fig, "gambar_2_1_ctc_pemetaan.png")


# =====================================================================
# GAMBAR 2.2 -- Ilustrasi frontier Pareto akurasi-latensi-ukuran model
# =====================================================================
def make_gambar_2_2():
    fig = plt.figure(figsize=(13, 9.6), dpi=150)
    ax = fig.add_axes([0.11, 0.17, 0.82, 0.68])

    dominated_x = np.array([38, 55, 62, 70, 80, 88, 95, 60, 45])
    dominated_y = np.array([72, 74, 70, 78, 80, 79, 81, 68, 65])
    dominated_s = np.array([260, 520, 340, 780, 1000, 620, 1300, 300, 200])

    pareto_x = np.array([15, 22, 34, 50, 72, 105])
    pareto_y = np.array([66, 76, 83, 87.5, 90.5, 92.2])
    pareto_s = np.array([90, 180, 340, 560, 900, 1500])

    ax.scatter(dominated_x, dominated_y, s=dominated_s, c="#c9c9c9",
               edgecolors="#8a8a8a", linewidths=1.1, alpha=0.85, zorder=2,
               label="Model didominasi")
    ax.plot(pareto_x, pareto_y, "-", color=RED_EDGE, lw=2.0, zorder=3)
    ax.scatter(pareto_x, pareto_y, s=pareto_s, c=BLUE_FILL, edgecolors=BLUE_EDGE,
               linewidths=2.0, zorder=4, label="Frontier Pareto (non-dominasi)")

    labels = ["A", "B", "C", "D", "E", "F"]
    offsets = [(-0.35, 3.2), (-0.2, 3.6), (0.3, 3.8), (0.3, 4.2), (0.3, 4.6), (0.3, 4.6)]
    for xi, yi, lab, (dx, dy) in zip(pareto_x, pareto_y, labels, offsets):
        ax.annotate(lab, (xi, yi), xytext=(xi + dx, yi + dy), fontsize=13,
                    weight="bold", color=BLUE_EDGE, ha="center")

    ax.annotate("Didominasi pada ketiga\nsumbu sekaligus", xy=(80, 80),
                xytext=(58, 55), fontsize=12, color="#606060", ha="center",
                arrowprops=dict(arrowstyle="-", color="#9a9a9a", lw=1.1))
    ax.annotate("Ukuran gelembung $\\propto$\njumlah parameter model", xy=(105, 92.2),
                xytext=(78, 96.5), fontsize=12, color=BLUE_EDGE, ha="left")

    ax.set_xlabel("Latensi inferensi (ms)", fontsize=14.5)
    ax.set_ylabel("Akurasi (%)", fontsize=14.5)
    ax.set_xlim(5, 125)
    ax.set_ylim(50, 100)
    ax.grid(True, linestyle=":", linewidth=0.7, color="#c9c9c9", alpha=0.9)
    for spine in ["top", "right"]:
        ax.spines[spine].set_visible(False)
    ax.tick_params(labelsize=12.5)
    ax.legend(loc="lower right", fontsize=12.5, frameon=False)

    fig.text(0.5, 0.96, "Ilustrasi Frontier Pareto pada Ruang Akurasi–Latensi–Ukuran Model",
              ha="center", va="center", fontsize=19, weight="bold", color=TEXT_DARK)
    fig.text(0.5, 0.045,
             "Titik A–F membentuk frontier Pareto: tidak ada model lain yang lebih akurat, lebih cepat, dan lebih kecil\n"
             "sekaligus. Titik abu-abu didominasi oleh minimal satu titik pada frontier di ketiga sumbu tujuan.",
             ha="center", va="center", fontsize=12.5, color=TEXT_GRAY, linespacing=1.5)

    save(fig, "gambar_2_2_pareto_frontier.png")


# =====================================================================
# GAMBAR 3.1 -- Diagram alir pelaksanaan penelitian
# =====================================================================
def make_gambar_3_1():
    W, H = 11, 17.6
    fig, ax = new_ax((W, H), dpi=140)
    ax.set_xlim(0, W)
    ax.set_ylim(0, H)

    ax.text(W / 2, H - 0.55, "Diagram Alir Pelaksanaan Penelitian", ha="center", va="center",
            fontsize=19, weight="bold", color=TEXT_DARK)

    cx = 5.5
    w_proc, h_proc = 5.6, 0.85
    w_dec, h_dec = 5.0, 1.15
    x_bypass = 1.35

    def proc_box(y_top, text, fc, ec, fs=12.5, weight="normal", w=w_proc):
        x0 = cx - w / 2
        y_bot = y_top - h_proc
        box(ax, x0, y_bot, w, h_proc, text, fc=fc, ec=ec, fs=fs, weight=weight)
        return y_bot

    def dec_diamond(y_top, text):
        y_bot = y_top - h_dec
        yc = y_top - h_dec / 2
        pts = [(cx, y_top), (cx + w_dec / 2, yc), (cx, y_bot), (cx - w_dec / 2, yc)]
        ax.add_patch(mpatches.Polygon(pts, closed=True, facecolor="#fdf3d9",
                                       edgecolor="#a67c00", linewidth=1.6))
        ax.text(cx, yc, text, ha="center", va="center", fontsize=12.5,
                color=TEXT_DARK, linespacing=1.3)
        return y_bot, yc

    gap = 0.55
    y = H - 1.15

    y_bot1 = proc_box(y, "Studi Literatur & Perumusan Masalah", GRAY_FILL, GRAY_EDGE,
                       fs=13, weight="bold")
    arrow(ax, cx, y_bot1, cx, y_bot1 - gap, lw=1.6)
    y -= (h_proc + gap)

    y_bot2 = proc_box(y, "Pengumpulan Korpus Karakter Terisolasi\nAksara Sunda (multi-sumber)",
                       BLUE_FILL, BLUE_EDGE)
    arrow(ax, cx, y_bot2, cx, y_bot2 - gap, lw=1.6)
    y -= (h_proc + gap)

    y_bot3 = proc_box(y, "Sintesis Korpus Kata/Kalimat Bertingkat\n(kata & instans crop tak-terlihat pada uji)",
                       BLUE_FILL, BLUE_EDGE)
    arrow(ax, cx, y_bot3, cx, y_bot3 - gap, lw=1.6)
    y -= (h_proc + gap)

    y_bot4 = proc_box(y, "Fase 1: Bangun CRNN + CTC, Baseline\nSegmentasi Trivial, dan Pemindaian Pengali Lebar",
                       BLUE_FILL, BLUE_EDGE)
    arrow(ax, cx, y_bot4, cx, y_bot4 - gap, lw=1.6)
    y -= (h_proc + gap)

    y_dec1_bot, y_dec1_c = dec_diamond(y, "Fase 1 berhasil &\nwaktu memadai?")
    x_dec1_left = cx - w_dec / 2
    ax.text(cx + 0.28, y_dec1_bot + 0.14, "ya", fontsize=12, color=TEXT_DARK, style="italic")
    arrow(ax, cx, y_dec1_bot, cx, y_dec1_bot - gap, lw=1.6)
    arrow(ax, x_dec1_left, y_dec1_c, x_bypass, y_dec1_c, lw=1.6)
    ax.text((x_dec1_left + x_bypass) / 2, y_dec1_c + 0.16, "tidak", fontsize=12,
            color=TEXT_DARK, style="italic", ha="center")
    y -= (h_dec + gap)

    y_bot5 = proc_box(y, "Fase 2: Tambah Model\nBerbasis Atensi (RARE)", GREEN_FILL, GREEN_EDGE,
                       weight="bold")
    arrow(ax, cx, y_bot5, cx, y_bot5 - gap, lw=1.6)
    y -= (h_proc + gap)

    y_dec2_bot, y_dec2_c = dec_diamond(y, "Waktu masih\nmemadai?")
    x_dec2_left = cx - w_dec / 2
    ax.text(cx + 0.28, y_dec2_bot + 0.14, "ya", fontsize=12, color=TEXT_DARK, style="italic")
    arrow(ax, cx, y_dec2_bot, cx, y_dec2_bot - gap, lw=1.6)
    arrow(ax, x_dec2_left, y_dec2_c, x_bypass, y_dec2_c, lw=1.6)
    ax.text((x_dec2_left + x_bypass) / 2, y_dec2_c + 0.16, "tidak", fontsize=12,
            color=TEXT_DARK, style="italic", ha="center")
    y -= (h_dec + gap)

    y_bot6 = proc_box(y, "Fase 3: Tambah Model\nBerbasis Transformer (TrOCR)", GREEN_FILL, GREEN_EDGE,
                       weight="bold")
    arrow(ax, cx, y_bot6, cx, y_bot6 - gap, lw=1.6)
    y -= (h_proc + gap)

    y_eval_top = y
    y_eval_bot = proc_box(y, "Evaluasi & Analisis Frontier Pareto\n(CER, WER, Latensi, Ukuran Model)",
                           BLUE_FILL, BLUE_EDGE)

    y_merge1 = y_eval_top - 0.24
    y_merge2 = y_eval_top - 0.55
    ax.plot([x_bypass, x_bypass], [y_merge2, y_dec1_c], color="#333333", lw=1.6, zorder=1)
    arrow(ax, x_bypass, y_merge1, cx - w_proc / 2, y_merge1, lw=1.6)
    arrow(ax, x_bypass, y_merge2, cx - w_proc / 2, y_merge2, lw=1.6)

    arrow(ax, cx, y_eval_bot, cx, y_eval_bot - gap, lw=1.6)
    y -= (h_proc + gap)

    proc_box(y, "Penyusunan Laporan Skripsi", GRAY_FILL, GRAY_EDGE, fs=13, weight="bold")

    ax.text(W / 2, 0.55,
            "Kotak biru: tahap wajib. Kotak hijau: tahap bertingkat sesuai anggaran waktu.\n"
            "Belah ketupat: titik keputusan. Jalur kiri: lintasan singkat bila waktu tidak memadai.",
            ha="center", va="center", fontsize=11.5, color=TEXT_GRAY, style="italic", linespacing=1.4)

    save(fig, "gambar_3_1_diagram_alir_penelitian.png")


# =====================================================================
# GAMBAR 3.2 -- Prosedur sintesis citra kata dari korpus karakter terisolasi
# =====================================================================
def load_char_sample(cls, target_h=170):
    folder = os.path.join(DATA_DIR, cls)
    files = sorted(os.listdir(folder))
    fpath = os.path.join(folder, files[0])
    im = Image.open(fpath).convert("L")
    bg = Image.new("L", im.size, 255)
    im = Image.eval(im, lambda p: p)
    arr = np.array(im)
    mask = arr < 250
    if mask.any():
        rows = np.any(mask, axis=1)
        cols = np.any(mask, axis=0)
        r0, r1 = np.where(rows)[0][[0, -1]]
        c0, c1 = np.where(cols)[0][[0, -1]]
        im = im.crop((max(c0 - 4, 0), max(r0 - 4, 0), min(c1 + 5, im.width), min(r1 + 5, im.height)))
    ratio = target_h / im.height
    im = im.resize((max(1, int(im.width * ratio)), target_h))
    return im


def compose_word(classes, target_h=170):
    imgs = [load_char_sample(c, target_h) for c in classes]
    pad = 14
    total_w = sum(im.width for im in imgs) + pad * (len(imgs) + 1)
    canvas_h = target_h + 40
    canvas = Image.new("L", (total_w, canvas_h), 255)
    x = pad
    for im in imgs:
        jitter_y = random.randint(-8, 8)
        y = (canvas_h - im.height) // 2 + jitter_y
        canvas.paste(im, (x, y))
        x += im.width + pad
    return canvas


def make_gambar_3_2():
    classes = ["ka", "u", "da"]
    samples = [load_char_sample(c) for c in classes]
    word_img = compose_word(classes)

    fig = plt.figure(figsize=(15, 8.2), dpi=150)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, 15)
    ax.set_ylim(0, 8.2)
    ax.axis("off")

    FW, FH = 15, 9.6
    fig.set_size_inches(FW, FH)
    ax.set_xlim(0, FW)
    ax.set_ylim(0, FH)

    ax.text(FW / 2, FH - 0.55, "Prosedur Sintesis Citra Kata Aksara Sunda dari Korpus Karakter Terisolasi",
            ha="center", va="center", fontsize=18.5, weight="bold", color=TEXT_DARK)
    ax.text(FW / 2, FH - 1.15,
            "Langkah 1 — ambil satu instans crop per kelas aksara dari korpus terisolasi",
            ha="center", va="center", fontsize=13.5, color=TEXT_GRAY, style="italic")

    n = len(samples)
    thumb_w, thumb_h = 2.7, 2.7
    gap = 1.0
    total_w = n * thumb_w + (n - 1) * gap
    x0 = (FW - total_w) / 2
    y0 = FH - 1.7 - thumb_h

    for i, (cls, im) in enumerate(zip(classes, samples)):
        x = x0 + i * (thumb_w + gap)
        box(ax, x, y0, thumb_w, thumb_h, "", fc="white", ec=BLUE_EDGE, lw=1.8)
        arr = np.array(im)
        pad_frac = 0.14
        ix0, iy0 = x + thumb_w * pad_frac, y0 + thumb_h * pad_frac * 1.3
        iw, ih = thumb_w * (1 - 2 * pad_frac), thumb_h * (1 - 2 * pad_frac) - 0.2
        aximg = fig.add_axes([ix0 / FW, iy0 / FH, iw / FW, ih / FH])
        aximg.imshow(arr, cmap="gray", vmin=0, vmax=255)
        aximg.axis("off")
        ax.text(x + thumb_w / 2, y0 - 0.30, f"kelas: “{cls}”", ha="center", va="top",
                fontsize=13.5, color=TEXT_DARK, weight="bold")

    y_label_bot = y0 - 0.30 - 0.42
    word_w, word_h = 5.4, 1.35
    word_top = 1.55
    xw = FW / 2 - word_w / 2

    arrow(ax, FW / 2, y_label_bot, FW / 2, word_top + word_h + 0.15, color=RED_EDGE, lw=2.2)
    ax.text(FW / 2 + 0.5, (y_label_bot + word_top + word_h) / 2,
            "penggabungan terprogram\n(posisi berurutan, sela acak,\njitter vertikal ringan)",
            ha="left", va="center", fontsize=12, color=RED_EDGE, weight="bold", linespacing=1.35)

    box(ax, xw, word_top, word_w, word_h, "", fc=GREEN_FILL, ec=GREEN_EDGE, lw=2.0)
    warr = np.array(word_img)
    pad = 0.12
    aximg2 = fig.add_axes([(xw + word_w * pad) / FW, (word_top + word_h * 0.18) / FH,
                            (word_w * (1 - 2 * pad)) / FW, (word_h * 0.64) / FH])
    aximg2.imshow(warr, cmap="gray", vmin=0, vmax=255)
    aximg2.axis("off")

    ax.text(FW / 2, word_top - 0.28,
            "Citra kata tersintesis — label acuan: “kuda” (tepat by construction)",
            ha="center", va="top", fontsize=13.5, color=TEXT_DARK, weight="bold")
    ax.text(FW / 2, 0.5,
            "Karena posisi dan identitas setiap karakter diketahui pada saat penyusunan, label ground truth diperoleh tanpa\n"
            "anotasi manual, dan segmentasi karakter yang trivial (posisi diketahui) tersedia sebagai baseline pembanding.",
            ha="center", va="center", fontsize=11.8, color=TEXT_GRAY, linespacing=1.5)

    save(fig, "gambar_3_2_sintesis_data.png")


# =====================================================================
# GAMBAR 3.3 -- Arsitektur CRNN yang diusulkan
# =====================================================================
def make_gambar_3_3():
    fig, ax = new_ax((22, 8), dpi=140)
    ax.set_xlim(0, 22)
    ax.set_ylim(0, 8)

    ax.text(11, 7.6, "Arsitektur CRNN yang Diusulkan beserta Dimensi Peta Fitur",
            ha="center", va="center", fontsize=20, weight="bold", color=TEXT_DARK)

    stages = [
        ("Citra\nmasukan", "32 x W x 1", GRAY_FILL, GRAY_EDGE, None),
        ("Konv-1\n32 kanal", "32 x W x 32", BLUE_FILL, BLUE_EDGE, "MaxPool 2x2"),
        ("Konv-2\n64 kanal", "16 x W/2 x 64", BLUE_FILL, BLUE_EDGE, "MaxPool 2x2"),
        ("Konv-3\n128 kanal", "8 x W/4 x 128", BLUE_FILL, BLUE_EDGE, "MaxPool 2x1"),
        ("Konv-4\n128 kanal", "4 x W/4 x 128", BLUE_FILL, BLUE_EDGE, "MaxPool 2x1\n+ pool adaptif"),
        ("Bentuk\nsekuens", "T x 128", GRAY_FILL, GRAY_EDGE, None),
        ("BiLSTM\n2 lapis, 256 unit", "T x 512", GREEN_FILL, GREEN_EDGE, None),
        ("Proyeksi\nlinear", "T x (C+1)", GREEN_FILL, GREEN_EDGE, None),
        ("Kerugian\nCTC", "greedy /\nbeam decode", "#fbe0df", RED_EDGE, None),
    ]

    n = len(stages)
    bw, bh = 1.95, 1.55
    gap = 0.42
    total_w = n * bw + (n - 1) * gap
    x0 = (22 - total_w) / 2
    y = 3.6

    xs = []
    for i, (label, dim, fc, ec, sub) in enumerate(stages):
        x = x0 + i * (bw + gap)
        xs.append(x)
        box(ax, x, y, bw, bh, label, fc=fc, ec=ec, fs=13.5,
            weight="bold" if fc in (GREEN_FILL, "#fbe0df") else "normal")
        ax.text(x + bw / 2, y + bh + 0.22, dim, ha="center", va="bottom",
                fontsize=12.5, color=DIM_BLUE, weight="bold")
        if sub:
            ax.text(x + bw / 2, y - 0.2, sub, ha="center", va="top",
                    fontsize=10.8, color=TEXT_GRAY, linespacing=1.3)
        if i < n - 1:
            arrow(ax, x + bw + 0.03, y + bh / 2, x + bw + gap - 0.03, y + bh / 2,
                  color="#333333", lw=1.6)

    ax.annotate("", xy=(xs[4] + bw, y + bh + 1.55), xytext=(xs[0], y + bh + 1.55),
                arrowprops=dict(arrowstyle="-", color="#8a8a8a", lw=1.2))
    ax.plot([xs[0], xs[0]], [y + bh + 1.45, y + bh + 1.55], color="#8a8a8a", lw=1.2)
    ax.plot([xs[4] + bw, xs[4] + bw], [y + bh + 1.45, y + bh + 1.55], color="#8a8a8a", lw=1.2)
    ax.text((xs[0] + xs[4] + bw) / 2, y + bh + 1.75, "Tulang punggung konvolusi (penurunan resolusi asimetris: tinggi hingga 1, lebar dijaga)",
            ha="center", va="bottom", fontsize=12.5, color="#606060", style="italic")

    ax.annotate("", xy=(xs[8] + bw, y - 0.85), xytext=(xs[6], y - 0.85),
                arrowprops=dict(arrowstyle="-", color="#8a8a8a", lw=1.2))
    ax.plot([xs[6], xs[6]], [y - 0.75, y - 0.85], color="#8a8a8a", lw=1.2)
    ax.plot([xs[8] + bw, xs[8] + bw], [y - 0.75, y - 0.85], color="#8a8a8a", lw=1.2)
    ax.text((xs[6] + xs[8] + bw) / 2, y - 1.05, "Kepala sekuensial (rekuren dwiarah + proyeksi linear + CTC)",
            ha="center", va="top", fontsize=12.5, color="#606060", style="italic")

    ax.text(11, 0.35,
            "W: lebar citra masukan (variabel); T = W/4: panjang langkah waktu; C: jumlah kelas aksara. "
            "Pengali lebar kanal $\\alpha$ menskalakan 32, 64, 128, 128 pada seluruh blok konvolusi (Tabel 3.2).",
            ha="center", va="center", fontsize=12, color=TEXT_GRAY)

    save(fig, "gambar_3_3_arsitektur_crnn.png")


if __name__ == "__main__":
    make_gambar_2_1()
    make_gambar_2_2()
    make_gambar_3_1()
    make_gambar_3_2()
    make_gambar_3_3()
    print("done")
