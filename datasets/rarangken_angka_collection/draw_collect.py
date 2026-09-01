# -*- coding: utf-8 -*-
"""Rapid mouse-drawing data-entry tool for the rarangken/angka classes --
draw, hit one key, it saves and clears automatically. No file dialogs, no
"save as", no manual renaming: much faster than Paint for producing many
samples in a row.

Also supports EDIT MODE: browse and touch up already-saved images (e.g. to
thicken strokes that came out too thin once scaled down as a small
attached mark in the compositor) instead of only ever drawing fresh ones.

Usage:
    python datasets/rarangken_angka_collection/draw_collect.py

Controls (drawing):
    draw          left mouse drag
    Enter/Space   save current drawing to the active class, clear canvas
    Backspace     clear canvas WITHOUT saving (undo a mistake)
    Right / ]     next class
    Left  / [     previous class
    Ctrl+Z        undo last stroke
    Esc           quit

Controls (edit mode -- Tab to toggle):
    Tab           enter/exit edit mode for the current class
    Page Down     next existing image
    Page Up       previous existing image
    T             thicken current image's strokes one step (repeatable)
    Enter/Space   save changes (overwrites the file), advance to next
    Backspace     revert to the originally-loaded version (no exit)

Controls (always available):
    O             toggle a faint reference-glyph overlay on the canvas
                  itself, as a tracing guide (separate from the side panel)
    ,  /  .       step the preview thumbnails to the previous/next saved
                  image for this class (view-only, doesn't touch the canvas)
    brush slider  drag to change live brush thickness (right panel)
"""
import os
import tkinter as tk
from datetime import datetime

from PIL import Image, ImageDraw, ImageTk

from glyph_render import shape_and_render, DOTTED_CIRCLE as DOTTED
from generate_worksheets import RARANGKEN, ANGKA
from image_utils import finalize_224, thicken_stroke

ROOT = os.path.dirname(os.path.abspath(__file__))
DATASET_DIR = os.path.join(os.path.dirname(ROOT), "aksara_sunda_full")

CANVAS_PX = 480          # on-screen drawing surface
SUPERSAMPLE = 2          # draw at 2x then downsample for smoother strokes
DRAW_PX = CANVAS_PX * SUPERSAMPLE
OUT_SIZE = 224
BRUSH_W_DEFAULT = 10 * SUPERSAMPLE  # reverted: a thinner live brush made
                             # short/fast strokes drop out or fragment after
                             # resize+threshold -- kept as the slider's
                             # default rather than a hard floor, so it's
                             # still adjustable but starts at the value
                             # already known to work.
BRUSH_W_MIN = 4 * SUPERSAMPLE
BRUSH_W_MAX = 24 * SUPERSAMPLE
TARGET_PER_CLASS = 250
OVERLAY_ALPHA = 0.18     # tracing-guide opacity: glyph mixed toward white
PREVIEW_THUMB_PX = 100

CLASSES = RARANGKEN + ANGKA  # [(folder, unicode_text, label, desc), ...]


class DrawCollectApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Koleksi Tulisan Tangan - Aksara Sunda")
        self.class_idx = 0

        self.img = Image.new("L", (DRAW_PX, DRAW_PX), 255)
        self.draw = ImageDraw.Draw(self.img)
        self.strokes = []          # list of point-lists, for undo
        self.current_stroke = None
        self.last_xy = None

        self.edit_mode = False
        self.edit_files = []       # existing filenames for the current class
        self.edit_idx = -1
        self.edit_original = None  # snapshot loaded from disk, for revert
        self._bg_photo = None

        self.brush_w = BRUSH_W_DEFAULT  # live brush width in draw-buffer px

        self.overlay_on = False
        self._overlay_photo = None      # low-opacity glyph, canvas-sized
        self._overlay_base = None       # PIL "L" version, re-blended on resize

        self.preview_files = []         # sorted saved filenames, current class
        self.preview_idx = -1           # index of the "previous" thumbnail
        self._preview_prev_photo = None
        self._preview_next_photo = None

        # --- layout ---
        main = tk.Frame(root)
        main.pack(padx=12, pady=12)

        left = tk.Frame(main)
        left.grid(row=0, column=0, padx=(0, 16))
        self.canvas = tk.Canvas(left, width=CANVAS_PX, height=CANVAS_PX,
                                 bg="white", cursor="pencil", highlightthickness=1,
                                 highlightbackground="#999999")
        self.canvas.pack()
        self.canvas.bind("<Button-1>", self.on_press)
        self.canvas.bind("<B1-Motion>", self.on_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_release)

        right = tk.Frame(main, width=260)
        right.grid(row=0, column=1, sticky="n")

        self.title_lbl = tk.Label(right, text="", font=("Segoe UI", 16, "bold"), anchor="w", justify="left")
        self.title_lbl.pack(fill="x")
        self.desc_lbl = tk.Label(right, text="", font=("Segoe UI", 11), fg="#444444", anchor="w",
                                  justify="left", wraplength=240)
        self.desc_lbl.pack(fill="x", pady=(2, 10))

        self.ref_lbl = tk.Label(right, bd=1, relief="solid")
        self.ref_lbl.pack(pady=(0, 10))

        self.progress_lbl = tk.Label(right, text="", font=("Segoe UI", 12, "bold"), fg="#1a6b1a")
        self.progress_lbl.pack(pady=(0, 14))

        brush_frame = tk.Frame(right)
        brush_frame.pack(fill="x", pady=(0, 12))
        tk.Label(brush_frame, text="Ketebalan kuas", font=("Segoe UI", 10), fg="#444444",
                 anchor="w").pack(fill="x")
        self.brush_scale = tk.Scale(
            brush_frame, from_=BRUSH_W_MIN, to=BRUSH_W_MAX, orient="horizontal",
            showvalue=True, length=240, command=self.on_brush_change,
        )
        self.brush_scale.set(BRUSH_W_DEFAULT)
        self.brush_scale.pack(fill="x")

        preview_frame = tk.Frame(right)
        preview_frame.pack(fill="x", pady=(0, 12))
        tk.Label(preview_frame, text="Preview gambar tersimpan (, / .)", font=("Segoe UI", 10),
                 fg="#444444", anchor="w").pack(fill="x")
        thumbs = tk.Frame(preview_frame)
        thumbs.pack(fill="x", pady=(4, 0))
        prev_col = tk.Frame(thumbs)
        prev_col.pack(side="left", expand=True)
        tk.Label(prev_col, text="sebelumnya", font=("Segoe UI", 8), fg="#888888").pack()
        self.preview_prev_lbl = tk.Label(prev_col, bd=1, relief="solid")
        self.preview_prev_lbl.pack()
        next_col = tk.Frame(thumbs)
        next_col.pack(side="left", expand=True)
        tk.Label(next_col, text="berikutnya", font=("Segoe UI", 8), fg="#888888").pack()
        self.preview_next_lbl = tk.Label(next_col, bd=1, relief="solid")
        self.preview_next_lbl.pack()
        self.preview_pos_lbl = tk.Label(preview_frame, text="", font=("Segoe UI", 8), fg="#888888")
        self.preview_pos_lbl.pack(pady=(2, 0))

        help_text = (
            "Gambar: klik-tahan-tarik mouse\n\n"
            "Enter / Spasi  = simpan & lanjut\n"
            "Backspace      = hapus tanpa simpan\n"
            "Ctrl+Z         = undo goresan terakhir\n"
            "← / [           = kelas sebelumnya\n"
            "→ / ]           = kelas berikutnya\n"
            "Tab            = mode edit gambar lama\n"
            "O              = tampilkan/sembunyikan panduan\n"
            "                 aksara transparan di kanvas\n"
            ",  /  .         = preview gambar sebelum/sesudah\n"
            "Esc            = keluar\n\n"
            "-- Mode edit (Tab) --\n"
            "PgDn / PgUp    = gambar berikut/sebelum\n"
            "T              = tebalkan goresan\n"
            "Enter/Spasi    = simpan, lanjut gambar\n"
            "Backspace      = kembalikan ke asli"
        )
        self.help_lbl = tk.Label(right, text=help_text, font=("Consolas", 10), fg="#555555",
                                  justify="left", anchor="w")
        self.help_lbl.pack(fill="x")

        self.status_lbl = tk.Label(root, text="", font=("Segoe UI", 10), fg="#888888")
        self.status_lbl.pack(pady=(0, 8))

        root.bind("<Return>", lambda e: self.save_and_clear())
        root.bind("<space>", lambda e: self.save_and_clear())
        root.bind("<BackSpace>", lambda e: self.clear(save=False))
        root.bind("<Control-z>", lambda e: self.undo())
        root.bind("<Right>", lambda e: self.switch_class(1))
        root.bind("<bracketright>", lambda e: self.switch_class(1))
        root.bind("<Left>", lambda e: self.switch_class(-1))
        root.bind("<bracketleft>", lambda e: self.switch_class(-1))
        root.bind("<Tab>", lambda e: self.toggle_edit_mode())
        root.bind("<Prior>", lambda e: self.edit_navigate(-1))   # Page Up
        root.bind("<Next>", lambda e: self.edit_navigate(1))     # Page Down
        root.bind("<KeyPress-t>", lambda e: self.thicken_current())
        root.bind("<KeyPress-T>", lambda e: self.thicken_current())
        root.bind("<KeyPress-o>", lambda e: self.toggle_overlay())
        root.bind("<KeyPress-O>", lambda e: self.toggle_overlay())
        root.bind("<comma>", lambda e: self.preview_navigate(-1))
        root.bind("<period>", lambda e: self.preview_navigate(1))
        root.bind("<Escape>", lambda e: root.destroy())

        self.load_class()

    # --- drawing ---
    def on_press(self, event):
        self.current_stroke = [(event.x, event.y)]
        self.last_xy = (event.x, event.y)

    def on_drag(self, event):
        x, y = event.x, event.y
        if self.last_xy is not None:
            self.canvas.create_line(self.last_xy[0], self.last_xy[1], x, y,
                                     width=self.brush_w // SUPERSAMPLE, fill="black",
                                     capstyle=tk.ROUND, smooth=True, tags="ink")
            sx0, sy0 = [c * SUPERSAMPLE for c in self.last_xy]
            sx1, sy1 = x * SUPERSAMPLE, y * SUPERSAMPLE
            self.draw.line([sx0, sy0, sx1, sy1], fill=0, width=self.brush_w)
            r = self.brush_w // 2
            self.draw.ellipse([sx1 - r, sy1 - r, sx1 + r, sy1 + r], fill=0)
        self.last_xy = (x, y)
        if self.current_stroke is not None:
            self.current_stroke.append((x, y))

    def on_brush_change(self, value):
        self.brush_w = int(float(value))

    def on_release(self, event):
        if self.current_stroke:
            self.strokes.append(self.current_stroke)
        self.current_stroke = None
        self.last_xy = None

    def get_base_image(self):
        """The canvas starting point: a blank white sheet normally, or the
        untouched loaded image while in edit mode (so undo/clear/redraw
        never lose an in-progress edit back to blank white)."""
        if self.edit_mode and self.edit_original is not None:
            return self.edit_original.copy()
        return Image.new("L", (DRAW_PX, DRAW_PX), 255)

    def refresh_canvas_from_img(self):
        """Redraw the on-screen canvas to match self.img -- used whenever
        self.img is replaced wholesale (entering edit mode, thicken, undo,
        revert) rather than incrementally drawn into."""
        self.canvas.delete("all")
        display_img = self.img.resize((CANVAS_PX, CANVAS_PX), Image.LANCZOS)
        self._bg_photo = ImageTk.PhotoImage(display_img)
        self.canvas.create_image(0, 0, anchor="nw", image=self._bg_photo, tags="bg")
        self.draw_overlay()

    def undo(self):
        if not self.strokes:
            return
        self.strokes.pop()
        self.img = self.get_base_image()
        self.draw = ImageDraw.Draw(self.img)
        self.refresh_canvas_from_img()
        for stroke in self.strokes:
            for i in range(1, len(stroke)):
                x0, y0 = stroke[i - 1]
                x1, y1 = stroke[i]
                self.canvas.create_line(x0, y0, x1, y1, width=self.brush_w // SUPERSAMPLE,
                                         fill="black", capstyle=tk.ROUND, smooth=True, tags="ink")
                sx0, sy0 = x0 * SUPERSAMPLE, y0 * SUPERSAMPLE
                sx1, sy1 = x1 * SUPERSAMPLE, y1 * SUPERSAMPLE
                self.draw.line([sx0, sy0, sx1, sy1], fill=0, width=self.brush_w)
                r = self.brush_w // 2
                self.draw.ellipse([sx1 - r, sy1 - r, sx1 + r, sy1 + r], fill=0)
        self.set_status("Goresan terakhir dihapus.")

    def clear(self, save):
        if not save:
            self.img = self.get_base_image()
            self.draw = ImageDraw.Draw(self.img)
            self.strokes = []
            self.refresh_canvas_from_img()
            self.set_status("Dikembalikan ke versi asli." if self.edit_mode
                             else "Dibersihkan tanpa disimpan.")

    def is_blank(self):
        extrema = self.img.getextrema()
        return extrema == (255, 255)

    # --- tracing-guide overlay (feature 1) ---
    def build_overlay_image(self, unicode_text):
        """Pre-render the current class's glyph as a faint, canvas-sized
        tracing guide (never baked into self.img -- purely a screen-only
        aid, so it can never leak into a saved sample)."""
        ref = shape_and_render(DOTTED + unicode_text, px_size=280).convert("L")
        ref.thumbnail((360, 360))
        composed = Image.new("L", (CANVAS_PX, CANVAS_PX), 255)
        x = (CANVAS_PX - ref.width) // 2
        y = (CANVAS_PX - ref.height) // 2
        composed.paste(ref, (x, y))
        white = Image.new("L", (CANVAS_PX, CANVAS_PX), 255)
        self._overlay_base = Image.blend(white, composed, OVERLAY_ALPHA)

    def draw_overlay(self):
        """(Re)place the overlay layer, keeping it sandwiched between the
        background image and any ink strokes regardless of draw order."""
        self.canvas.delete("overlay")
        if not self.overlay_on or self._overlay_base is None:
            return
        self._overlay_photo = ImageTk.PhotoImage(self._overlay_base)
        self.canvas.create_image(0, 0, anchor="nw", image=self._overlay_photo, tags="overlay")
        try:
            self.canvas.tag_raise("overlay", "bg")
        except tk.TclError:
            pass  # no "bg" item yet on the very first call

    def toggle_overlay(self):
        self.overlay_on = not self.overlay_on
        self.draw_overlay()
        self.set_status("Panduan aksara: AKTIF" if self.overlay_on else "Panduan aksara: nonaktif")

    # --- previous/next saved-image preview (feature 3) ---
    def update_preview(self):
        out_dir = os.path.join(DATASET_DIR, self.current_folder)
        self.preview_files = sorted(f for f in os.listdir(out_dir) if f.lower().endswith(".png"))
        self.preview_idx = len(self.preview_files) - 1  # "previous" = most recently saved
        self.render_preview_thumbs()

    def render_preview_thumbs(self):
        def load_thumb(idx):
            if idx < 0 or idx >= len(self.preview_files):
                return None
            path = os.path.join(DATASET_DIR, self.current_folder, self.preview_files[idx])
            im = Image.open(path).convert("L")
            im.thumbnail((PREVIEW_THUMB_PX, PREVIEW_THUMB_PX))
            return ImageTk.PhotoImage(im)

        self._preview_prev_photo = load_thumb(self.preview_idx)
        self._preview_next_photo = load_thumb(self.preview_idx + 1)
        self.preview_prev_lbl.config(image=self._preview_prev_photo or "",
                                      text="" if self._preview_prev_photo else "(kosong)")
        self.preview_next_lbl.config(image=self._preview_next_photo or "",
                                      text="" if self._preview_next_photo else "(kosong)")
        total = len(self.preview_files)
        self.preview_pos_lbl.config(
            text="Belum ada gambar tersimpan." if total == 0 else f"{self.preview_idx + 1} / {total}")

    def preview_navigate(self, delta):
        if not self.preview_files:
            return
        self.preview_idx = max(0, min(len(self.preview_files) - 1, self.preview_idx + delta))
        self.render_preview_thumbs()

    # --- class navigation ---
    def load_class(self):
        folder, unicode_text, label, desc = CLASSES[self.class_idx]
        self.current_folder = folder
        os.makedirs(os.path.join(DATASET_DIR, folder), exist_ok=True)

        self.title_lbl.config(text=f"{label}")
        self.desc_lbl.config(text=f"({folder})\n{desc}")

        ref_img = shape_and_render(DOTTED + unicode_text, px_size=180)
        ref_img.thumbnail((220, 220))
        self._ref_photo = ImageTk.PhotoImage(ref_img)
        self.ref_lbl.config(image=self._ref_photo)
        self.build_overlay_image(unicode_text)

        self.edit_mode = False
        self.edit_files = []
        self.edit_idx = -1
        self.edit_original = None

        self.update_progress()
        self.update_preview()
        self.clear(save=False)
        self.set_status(f"Kelas {self.class_idx + 1}/{len(CLASSES)}")

    def switch_class(self, delta):
        self.class_idx = (self.class_idx + delta) % len(CLASSES)
        self.load_class()

    def update_progress(self):
        n = len([f for f in os.listdir(os.path.join(DATASET_DIR, self.current_folder))
                 if f.lower().endswith(".png")])
        self.progress_lbl.config(text=f"Tersimpan: {n} / {TARGET_PER_CLASS}")

    # --- edit mode ---
    def toggle_edit_mode(self):
        if self.edit_mode:
            self.exit_edit_mode()
            return
        out_dir = os.path.join(DATASET_DIR, self.current_folder)
        files = sorted(f for f in os.listdir(out_dir) if f.lower().endswith(".png"))
        if not files:
            self.set_status("Tidak ada gambar tersimpan untuk kelas ini.")
            return
        self.edit_files = files
        self.edit_idx = 0
        self.edit_mode = True
        self.load_edit_image()

    def exit_edit_mode(self):
        self.edit_mode = False
        self.edit_files = []
        self.edit_idx = -1
        self.edit_original = None
        self.clear(save=False)
        self.set_status("Keluar dari mode edit.")

    def edit_navigate(self, delta):
        if not self.edit_mode or not self.edit_files:
            return
        self.edit_idx = (self.edit_idx + delta) % len(self.edit_files)
        self.load_edit_image()

    def load_edit_image(self):
        fname = self.edit_files[self.edit_idx]
        path = os.path.join(DATASET_DIR, self.current_folder, fname)
        im = Image.open(path).convert("L").resize((DRAW_PX, DRAW_PX), Image.LANCZOS)
        self.edit_original = im
        self.strokes = []
        self.img = self.get_base_image()
        self.draw = ImageDraw.Draw(self.img)
        self.refresh_canvas_from_img()
        self.set_status(f"Edit {self.edit_idx + 1}/{len(self.edit_files)}: {fname}")

    def thicken_current(self):
        if not self.edit_mode:
            self.set_status("Penebalan (T) hanya aktif di mode edit -- tekan Tab dulu.")
            return
        self.img = thicken_stroke(self.img, target_factor=1.30)
        self.draw = ImageDraw.Draw(self.img)
        self.strokes = []  # baked into self.img; Backspace still reverts to the true original
        self.refresh_canvas_from_img()
        self.set_status("Ditebalkan (tekan T lagi untuk lebih tebal, Backspace untuk batal semua).")

    # --- save ---
    def save_and_clear(self):
        if self.is_blank():
            self.set_status("Kanvas kosong, tidak disimpan.")
            return

        small = finalize_224(self.img, out_size=OUT_SIZE)
        if small is None:
            self.set_status("Goresan terlalu kecil, tidak disimpan.")
            return

        if self.edit_mode:
            fname = self.edit_files[self.edit_idx]
            out_path = os.path.join(DATASET_DIR, self.current_folder, fname)
            small.save(out_path)
            self.update_progress()
            self.render_preview_thumbs()  # this file's thumbnail may have changed
            if self.edit_idx + 1 < len(self.edit_files):
                self.edit_idx += 1
                self.load_edit_image()
                self.set_status(f"Disimpan: {fname} -- lanjut ke gambar berikutnya.")
            else:
                self.set_status(f"Disimpan: {fname} -- semua gambar di kelas ini sudah direview.")
                self.exit_edit_mode()
            return

        out_dir = os.path.join(DATASET_DIR, self.current_folder)
        os.makedirs(out_dir, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d%H%M%S%f")
        out_path = os.path.join(out_dir, f"handdraw_{ts}.png")
        small.save(out_path)

        self.clear(save=False)
        self.update_progress()
        self.update_preview()
        self.set_status(f"Tersimpan: {os.path.basename(out_path)}")

    def set_status(self, text):
        self.status_lbl.config(text=text)


if __name__ == "__main__":
    root = tk.Tk()
    app = DrawCollectApp(root)
    root.mainloop()
