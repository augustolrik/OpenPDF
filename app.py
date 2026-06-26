from __future__ import annotations

import math
import json
import queue
import threading
import traceback
from dataclasses import dataclass
from pathlib import Path
import tkinter as tk
from tkinter import colorchooser, filedialog, messagebox, simpledialog, ttk

try:
    import fitz
    from PIL import Image, ImageTk
except ImportError as error:
    raise SystemExit("Missing packages. Run Setup.bat first.") from error

from ocr_pipeline import (
    IMAGE_TYPES,
    export_searchable_pdf,
    ocr_text,
    process_photo,
)
from pdf_engine import (
    add_image_annotation,
    add_ocr_layer,
    configure_tesseract,
    find_text_block,
    parse_page_ranges,
    render_page,
    replace_text,
)


APP_TITLE = "OpenPDF"
PAGE_MARGIN = 22
COLORS = {
    "purple": "#6036A6",
    "purple_dark": "#321B52",
    "purple_deep": "#241535",
    "purple_soft": "#EEE7FA",
    "pink": "#ED5DA8",
    "pink_dark": "#D94691",
    "yellow": "#FFD84D",
    "yellow_dark": "#EDC12D",
    "cream": "#FFF9E8",
    "surface": "#FAF8FD",
    "white": "#FFFFFF",
    "ink": "#2B2135",
    "muted": "#756A80",
    "workspace": "#2A2132",
    "shadow": "#19131F",
}
TOOLS = {
    "select": "Select",
    "edit_text": "Change text",
    "text_box": "Text box",
    "line": "Line",
    "shape": "Shapes",
    "image": "Image",
}
SHAPES = ("Rectangle", "Square", "Circle")
LINE_STYLES = ("Solid", "Dotted", "Arrow")
PAGE_SIZES = {
    "A5": (420.94, 595.28),
    "A4": (595.28, 841.89),
    "A3": (841.89, 1190.55),
    "Letter": (612.0, 792.0),
    "Legal": (612.0, 1008.0),
}


@dataclass
class OcrPage:
    image: Image.Image
    text: str = ""
    source: str = ""


def rounded_rectangle(canvas: tk.Canvas, x1, y1, x2, y2, radius, **kwargs):
    radius = min(radius, abs(x2 - x1) / 2, abs(y2 - y1) / 2)
    points = [
        x1 + radius, y1, x2 - radius, y1, x2, y1, x2, y1 + radius,
        x2, y2 - radius, x2, y2, x2 - radius, y2, x1 + radius, y2,
        x1, y2, x1, y2 - radius, x1, y1 + radius, x1, y1,
    ]
    return canvas.create_polygon(points, smooth=True, splinesteps=24, **kwargs)


class RoundedButton(tk.Canvas):
    def __init__(
        self,
        parent,
        text: str,
        command,
        *,
        bg: str,
        fg: str,
        hover: str,
        width: int = 112,
        height: int = 38,
        font=("Segoe UI Semibold", 9),
    ) -> None:
        parent_bg = parent.cget("bg")
        super().__init__(
            parent,
            width=width,
            height=height,
            bg=parent_bg,
            highlightthickness=0,
            bd=0,
            cursor="hand2",
        )
        self.command = command
        self.normal_bg = bg
        self.hover_bg = hover
        self.fg = fg
        self.font = font
        self.text = text
        self._draw(bg)
        self.bind("<Enter>", lambda _event: self._draw(self.hover_bg))
        self.bind("<Leave>", lambda _event: self._draw(self.normal_bg))
        self.bind("<ButtonRelease-1>", lambda _event: self.command())

    def _draw(self, color: str) -> None:
        self.delete("all")
        rounded_rectangle(self, 1, 1, int(self["width"]) - 1, int(self["height"]) - 1, 12, fill=color, outline="")
        self.create_text(
            int(self["width"]) / 2,
            int(self["height"]) / 2,
            text=self.text,
            fill=self.fg,
            font=self.font,
        )

    def set_palette(self, bg: str, fg: str, hover: str) -> None:
        self.normal_bg = bg
        self.hover_bg = hover
        self.fg = fg
        self._draw(bg)


class PdfEditor(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("1500x930")
        self.minsize(1050, 650)
        self.configure(bg=COLORS["surface"])

        self.document: fitz.Document | None = None
        self.filename: Path | None = None
        self.current_page = 0
        self.zoom = 1.05
        self.preview_photo: ImageTk.PhotoImage | None = None
        self.annotation_page: fitz.Page | None = None
        self.tool = "select"
        self.drag_start: tuple[float, float] | None = None
        self.drag_item: int | None = None
        self.selected_annot_xref: int | None = None
        self.object_drag_mode: str | None = None
        self.object_drag_start: fitz.Point | None = None
        self.object_original_rect: fitz.Rect | None = None
        self.object_original_vertices: list[fitz.Point] | None = None
        self.object_snapshot: bytes | None = None
        self.object_changed = False
        self.undo_stack: list[bytes] = []
        self.events: queue.Queue = queue.Queue()
        self.busy = False
        self.edge_color = (0.376, 0.212, 0.651)
        self.fill_color = (1.0, 0.847, 0.302)
        self.fill_enabled = tk.BooleanVar(value=False)
        self.shape_var = tk.StringVar(value=SHAPES[0])
        self.line_style_var = tk.StringVar(value=LINE_STYLES[0])
        self.line_width_var = tk.DoubleVar(value=1.5)
        self.tool_buttons: dict[str, RoundedButton] = {}
        self.ocr_pages: list[OcrPage] = []
        self.ocr_current_index: int | None = None
        self.ocr_preview_photo: ImageTk.PhotoImage | None = None
        self.ocr_busy = False
        self.ocr_two_page_var = tk.BooleanVar(value=False)
        self.ocr_already_cropped_var = tk.BooleanVar(value=False)
        self.ocr_status_var = tk.StringVar(value="Ready")
        self.ocr_progress_var = tk.DoubleVar(value=0)

        self.status_var = tk.StringVar(value="Open a PDF to begin")
        self.page_var = tk.StringVar(value="No document")
        self.tool_var = tk.StringVar(value=TOOLS[self.tool])
        self._build_ui()
        self.after(100, self._poll_events)

    def _build_ui(self) -> None:
        self.option_add("*Font", "{Segoe UI} 10")
        self.option_add("*Menu.background", COLORS["white"])
        self.option_add("*Menu.foreground", COLORS["ink"])
        self.option_add("*Menu.activeBackground", COLORS["pink"])
        self.option_add("*Menu.activeForeground", COLORS["white"])

        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure(
            "Modern.Horizontal.TProgressbar",
            troughcolor=COLORS["purple_soft"],
            background=COLORS["pink"],
            bordercolor=COLORS["purple_soft"],
            lightcolor=COLORS["pink"],
            darkcolor=COLORS["pink"],
        )
        style.configure(
            "Modern.Vertical.TScrollbar",
            troughcolor=COLORS["workspace"],
            background=COLORS["purple"],
            bordercolor=COLORS["workspace"],
            arrowcolor=COLORS["white"],
        )
        style.configure(
            "Modern.Horizontal.TScrollbar",
            troughcolor=COLORS["workspace"],
            background=COLORS["purple"],
            bordercolor=COLORS["workspace"],
            arrowcolor=COLORS["white"],
        )
        style.configure(
            "Modern.TCombobox",
            fieldbackground=COLORS["purple_soft"],
            background=COLORS["purple"],
            foreground=COLORS["purple_dark"],
            arrowcolor=COLORS["white"],
            bordercolor=COLORS["pink"],
            lightcolor=COLORS["pink"],
            darkcolor=COLORS["pink"],
            padding=5,
        )
        style.map(
            "Modern.TCombobox",
            fieldbackground=[
                ("readonly", COLORS["purple_soft"]),
                ("focus", "#E2D5F5"),
            ],
            foreground=[("readonly", COLORS["purple_dark"])],
            selectbackground=[("readonly", COLORS["purple_soft"])],
            selectforeground=[("readonly", COLORS["purple_dark"])],
        )
        style.configure(
            "Modern.TSpinbox",
            fieldbackground=COLORS["purple_soft"],
            background=COLORS["purple"],
            foreground=COLORS["purple_dark"],
            arrowcolor=COLORS["white"],
            bordercolor=COLORS["pink"],
            lightcolor=COLORS["pink"],
            darkcolor=COLORS["pink"],
            padding=5,
        )
        style.map(
            "Modern.TSpinbox",
            fieldbackground=[("readonly", COLORS["purple_soft"])],
            foreground=[("readonly", COLORS["purple_dark"])],
        )
        self.option_add("*TCombobox*Listbox.background", COLORS["purple_soft"])
        self.option_add("*TCombobox*Listbox.foreground", COLORS["purple_dark"])
        self.option_add("*TCombobox*Listbox.selectBackground", COLORS["pink"])
        self.option_add("*TCombobox*Listbox.selectForeground", COLORS["white"])

        menu = tk.Menu(self, bd=0)
        file_menu = tk.Menu(menu, tearoff=False, bd=0)
        file_menu.add_command(label="Open PDF...", command=self.open_pdf, accelerator="Ctrl+O")
        file_menu.add_command(label="Save", command=self.save_pdf, accelerator="Ctrl+S")
        file_menu.add_command(label="Save as...", command=self.save_as)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.destroy)
        menu.add_cascade(label="File", menu=file_menu)

        page_menu = tk.Menu(menu, tearoff=False, bd=0)
        page_menu.add_command(label="Add blank page", command=self.add_blank_page)
        page_menu.add_command(label="Insert pages from PDF...", command=self.insert_pdf)
        page_menu.add_command(label="Delete current page", command=self.delete_page)
        page_menu.add_command(label="Move page up", command=lambda: self.move_page(-1))
        page_menu.add_command(label="Move page down", command=lambda: self.move_page(1))
        menu.add_cascade(label="Pages", menu=page_menu)

        tools_menu = tk.Menu(menu, tearoff=False, bd=0)
        for key, label in TOOLS.items():
            tools_menu.add_command(label=label, command=lambda value=key: self.set_tool(value))
        tools_menu.add_separator()
        tools_menu.add_command(label="OCR selected pages...", command=self.run_ocr)
        menu.add_cascade(label="Tools", menu=tools_menu)
        self.config(menu=menu)

        self.bind_all("<Control-o>", lambda _event: self.open_pdf())
        self.bind_all("<Control-s>", lambda _event: self.save_pdf())
        self.bind_all("<Control-z>", lambda _event: self.undo())

        header = tk.Frame(self, bg=COLORS["purple_dark"], height=68)
        header.pack(fill="x")
        header.pack_propagate(False)

        brand = tk.Frame(header, bg=COLORS["purple_dark"])
        brand.pack(side="left", padx=(16, 24), fill="y")
        logo_stack = tk.Frame(brand, bg=COLORS["purple_dark"])
        logo_stack.pack(side="left", pady=7)
        logo = tk.Canvas(
            logo_stack, width=48, height=42, bg=COLORS["purple_dark"], highlightthickness=0
        )
        logo.pack()
        rounded_rectangle(logo, 3, 8, 45, 40, 13, fill=COLORS["yellow"], outline="")
        logo.create_polygon(10, 14, 16, 3, 22, 15, fill=COLORS["yellow"], outline="")
        logo.create_polygon(26, 15, 32, 3, 38, 14, fill=COLORS["yellow"], outline="")
        logo.create_oval(16, 21, 20, 25, fill=COLORS["purple_dark"], outline="")
        logo.create_oval(29, 21, 33, 25, fill=COLORS["purple_dark"], outline="")
        logo.create_polygon(23, 27, 25, 30, 27, 27, fill=COLORS["pink"], outline="")
        logo.create_line(24, 31, 18, 34, fill=COLORS["purple_dark"], width=1)
        logo.create_line(26, 31, 32, 34, fill=COLORS["purple_dark"], width=1)
        tk.Label(
            logo_stack,
            text="OpenPDF",
            bg=COLORS["purple_dark"],
            fg=COLORS["yellow"],
            font=("Segoe UI Semibold", 7),
        ).pack()
        title_box = tk.Frame(brand, bg=COLORS["purple_dark"])
        title_box.pack(side="left", padx=(10, 0), pady=9)
        tk.Label(
            title_box,
            text="OpenPDF",
            bg=COLORS["purple_dark"],
            fg=COLORS["white"],
            font=("Segoe UI Semibold", 17),
        ).pack(anchor="w")
        tk.Label(
            title_box,
            text="Clean PDF workspace",
            bg=COLORS["purple_dark"],
            fg="#CFC0E7",
            font=("Segoe UI", 8),
        ).pack(anchor="w")

        actions = tk.Frame(header, bg=COLORS["purple_dark"])
        actions.pack(side="left", fill="y", pady=14)
        RoundedButton(
            actions, "Open PDF", self.open_pdf, bg=COLORS["yellow"],
            fg=COLORS["purple_dark"], hover=COLORS["yellow_dark"], width=105,
        ).pack(side="left", padx=4)
        RoundedButton(
            actions, "Save", self.save_pdf, bg=COLORS["pink"],
            fg=COLORS["white"], hover=COLORS["pink_dark"], width=88,
        ).pack(side="left", padx=4)
        RoundedButton(
            header, "OCR pages", self.run_ocr, bg=COLORS["white"],
            fg=COLORS["purple"], hover=COLORS["purple_soft"], width=118,
        ).pack(side="right", padx=18, pady=14)

        style.configure(
            "Modern.TNotebook",
            background=COLORS["surface"],
            borderwidth=0,
            tabmargins=(18, 8, 18, 0),
        )
        style.configure(
            "Modern.TNotebook.Tab",
            background=COLORS["purple_soft"],
            foreground=COLORS["purple_dark"],
            padding=(18, 8),
            font=("Segoe UI Semibold", 10),
        )
        style.map(
            "Modern.TNotebook.Tab",
            background=[("selected", COLORS["pink"])],
            foreground=[("selected", COLORS["white"])],
        )
        self.notebook = ttk.Notebook(self, style="Modern.TNotebook")
        self.notebook.pack(fill="both", expand=True)
        self.editor_tab = tk.Frame(self.notebook, bg=COLORS["surface"])
        self.ocr_tab = tk.Frame(self.notebook, bg=COLORS["surface"])
        self.notebook.add(self.editor_tab, text="OpenPDF")
        self.notebook.add(self.ocr_tab, text="OCR Generator")

        body = tk.PanedWindow(
            self.editor_tab,
            orient="horizontal",
            bg=COLORS["purple_soft"],
            sashwidth=5,
            sashrelief="flat",
            bd=0,
        )
        body.pack(fill="both", expand=True)

        sidebar = tk.Frame(body, width=218, bg=COLORS["surface"], padx=12, pady=12)
        body.add(sidebar, minsize=190, width=218)
        tk.Label(
            sidebar,
            text="DOCUMENT PAGES",
            bg=COLORS["surface"],
            fg=COLORS["purple_dark"],
            font=("Segoe UI Semibold", 10),
        ).pack(anchor="w")
        tk.Label(
            sidebar,
            text="Select and arrange your PDF",
            bg=COLORS["surface"],
            fg=COLORS["muted"],
            font=("Segoe UI", 8),
        ).pack(anchor="w", pady=(2, 10))
        self.page_list = tk.Listbox(
            sidebar,
            exportselection=False,
            bg=COLORS["white"],
            fg=COLORS["ink"],
            selectbackground=COLORS["pink"],
            selectforeground=COLORS["white"],
            activestyle="none",
            bd=0,
            highlightthickness=1,
            highlightbackground=COLORS["purple_soft"],
            highlightcolor=COLORS["purple"],
            font=("Segoe UI Semibold", 10),
            relief="flat",
        )
        self.page_list.pack(fill="both", expand=True, pady=(0, 12), ipady=8)
        self.page_list.bind("<<ListboxSelect>>", self._select_page)

        page_buttons = tk.Frame(sidebar, bg=COLORS["surface"])
        page_buttons.pack(fill="x")
        RoundedButton(
            page_buttons, "+ Blank", self.add_blank_page, bg=COLORS["purple_soft"],
            fg=COLORS["purple_dark"], hover="#DED0F4", width=90, height=34,
        ).pack(side="left")
        RoundedButton(
            page_buttons, "+ PDF", self.insert_pdf, bg=COLORS["purple_soft"],
            fg=COLORS["purple_dark"], hover="#DED0F4", width=90, height=34,
        ).pack(side="right")
        order_buttons = tk.Frame(sidebar, bg=COLORS["surface"])
        order_buttons.pack(fill="x", pady=(7, 0))
        RoundedButton(
            order_buttons, "Move up", lambda: self.move_page(-1), bg=COLORS["purple_soft"],
            fg=COLORS["purple_dark"], hover="#DED0F4", width=90, height=32,
        ).pack(side="left")
        RoundedButton(
            order_buttons, "Move down", lambda: self.move_page(1), bg=COLORS["purple_soft"],
            fg=COLORS["purple_dark"], hover="#DED0F4", width=90, height=32,
        ).pack(side="right")
        RoundedButton(
            sidebar, "Delete page", self.delete_page, bg="#FCE3EF",
            fg=COLORS["pink_dark"], hover="#F7CADD", width=190, height=34,
        ).pack(pady=(7, 0))

        viewer = tk.Frame(body, bg=COLORS["workspace"])
        body.add(viewer, stretch="always")
        right_tools = tk.Frame(body, width=218, bg=COLORS["surface"], padx=14, pady=14)
        body.add(right_tools, minsize=200, width=218)
        tk.Label(
            right_tools,
            text="TOOLS",
            bg=COLORS["surface"],
            fg=COLORS["purple_dark"],
            font=("Segoe UI Semibold", 10),
        ).pack(anchor="w")
        tk.Label(
            right_tools,
            text="Choose when needed. The page stays large.",
            bg=COLORS["surface"],
            fg=COLORS["muted"],
            font=("Segoe UI", 8),
            wraplength=178,
            justify="left",
        ).pack(anchor="w", pady=(2, 10))
        for key in ("select", "edit_text", "text_box", "line", "shape", "image"):
            button = RoundedButton(
                right_tools,
                TOOLS[key],
                lambda value=key: self.set_tool(value),
                bg=COLORS["purple_soft"],
                fg=COLORS["purple_dark"],
                hover="#DED0F4",
                width=178,
                height=32,
            )
            button.pack(fill="x", pady=3)
            self.tool_buttons[key] = button

        tk.Frame(right_tools, bg=COLORS["purple_soft"], height=1).pack(fill="x", pady=10)
        tk.Label(
            right_tools, text="DRAW STYLE", bg=COLORS["surface"],
            fg=COLORS["purple_dark"], font=("Segoe UI Semibold", 9),
        ).pack(anchor="w", pady=(0, 6))
        tk.Label(
            right_tools, text="Figure", bg=COLORS["surface"], fg=COLORS["muted"],
            font=("Segoe UI", 9),
        ).pack(anchor="w")
        self.shape_picker = ttk.Combobox(
            right_tools, textvariable=self.shape_var, values=SHAPES,
            state="readonly", width=18, style="Modern.TCombobox",
        )
        self.shape_picker.pack(fill="x", pady=(3, 8))
        self.shape_picker.bind("<<ComboboxSelected>>", lambda _event: self.set_tool("shape"))
        tk.Label(
            right_tools, text="Line type", bg=COLORS["surface"], fg=COLORS["muted"],
            font=("Segoe UI", 9),
        ).pack(anchor="w")
        self.line_style_picker = ttk.Combobox(
            right_tools, textvariable=self.line_style_var, values=LINE_STYLES,
            state="readonly", width=18, style="Modern.TCombobox",
        )
        self.line_style_picker.pack(fill="x", pady=(3, 8))
        self.line_style_picker.bind("<<ComboboxSelected>>", lambda _event: self.set_tool("line"))
        tk.Label(
            right_tools, text="Width", bg=COLORS["surface"], fg=COLORS["muted"],
            font=("Segoe UI", 9),
        ).pack(anchor="w")
        ttk.Spinbox(
            right_tools,
            values=(0.5, 1, 1.5, 2, 3, 4, 6, 8, 10, 12),
            textvariable=self.line_width_var,
            width=8,
            state="readonly",
            style="Modern.TSpinbox",
        ).pack(fill="x", pady=(3, 8))
        color_grid = tk.Frame(right_tools, bg=COLORS["surface"])
        color_grid.pack(fill="x", pady=(2, 5))
        self.edge_swatch = self._make_swatch(color_grid, "#6036A6", self.choose_edge_color, COLORS["surface"])
        self.edge_swatch.pack(side="left", padx=(0, 5))
        self._property_button(color_grid, "Edge", self.choose_edge_color, COLORS["surface"]).pack(side="left")
        fill_grid = tk.Frame(right_tools, bg=COLORS["surface"])
        fill_grid.pack(fill="x", pady=(0, 5))
        self.fill_swatch = self._make_swatch(fill_grid, "#FFD84D", self.choose_fill_color, COLORS["surface"])
        self.fill_swatch.pack(side="left", padx=(0, 5))
        self._property_button(fill_grid, "Fill", self.choose_fill_color, COLORS["surface"]).pack(side="left")
        tk.Checkbutton(
            right_tools,
            text="Use fill",
            variable=self.fill_enabled,
            bg=COLORS["surface"],
            fg=COLORS["purple_dark"],
            activebackground=COLORS["surface"],
            selectcolor=COLORS["white"],
            font=("Segoe UI Semibold", 9),
            bd=0,
        ).pack(anchor="w", pady=(0, 8))

        tk.Frame(right_tools, bg=COLORS["purple_soft"], height=1).pack(fill="x", pady=8)
        tk.Label(
            right_tools, text="SELECTED OBJECT", bg=COLORS["surface"],
            fg=COLORS["purple_dark"], font=("Segoe UI Semibold", 9),
        ).pack(anchor="w", pady=(0, 6))
        RoundedButton(
            right_tools, "Edit text", self.edit_selected_text_object,
            bg=COLORS["purple_soft"], fg=COLORS["purple_dark"], hover="#DED0F4",
            width=178, height=32,
        ).pack(fill="x", pady=3)
        RoundedButton(
            right_tools, "Rotate left", lambda: self.rotate_selected_object(-90),
            bg=COLORS["purple_soft"], fg=COLORS["purple_dark"], hover="#DED0F4",
            width=178, height=32,
        ).pack(fill="x", pady=3)
        RoundedButton(
            right_tools, "Rotate right", lambda: self.rotate_selected_object(90),
            bg=COLORS["purple_soft"], fg=COLORS["purple_dark"], hover="#DED0F4",
            width=178, height=32,
        ).pack(fill="x", pady=3)
        RoundedButton(
            right_tools, "Delete object", self.delete_selected_object,
            bg="#FCE3EF", fg=COLORS["pink_dark"], hover="#F7CADD",
            width=178, height=32,
        ).pack(fill="x", pady=3)
        viewer_tools = tk.Frame(viewer, bg=COLORS["purple_deep"], height=49)
        viewer_tools.pack(fill="x")
        viewer_tools.pack_propagate(False)
        tk.Label(
            viewer_tools,
            textvariable=self.tool_var,
            bg=COLORS["purple_deep"],
            fg=COLORS["yellow"],
            font=("Segoe UI Semibold", 9),
        ).pack(side="left", padx=18)
        RoundedButton(
            viewer_tools, "-", lambda: self.change_zoom(0.85), bg="#49325E",
            fg=COLORS["white"], hover=COLORS["purple"], width=38, height=30,
            font=("Segoe UI Semibold", 13),
        ).pack(side="right", padx=(3, 12), pady=9)
        RoundedButton(
            viewer_tools, "+", lambda: self.change_zoom(1.18), bg="#49325E",
            fg=COLORS["white"], hover=COLORS["purple"], width=38, height=30,
            font=("Segoe UI Semibold", 13),
        ).pack(side="right", pady=9)
        tk.Label(
            viewer_tools,
            textvariable=self.page_var,
            bg=COLORS["purple_deep"],
            fg="#D9CEE3",
            font=("Segoe UI", 9),
        ).pack(side="right", padx=15)

        canvas_frame = tk.Frame(viewer, bg=COLORS["workspace"])
        canvas_frame.pack(fill="both", expand=True)
        self.canvas = tk.Canvas(
            canvas_frame, bg=COLORS["workspace"], highlightthickness=0
        )
        x_scroll = ttk.Scrollbar(
            canvas_frame, orient="horizontal", command=self.canvas.xview,
            style="Modern.Horizontal.TScrollbar",
        )
        y_scroll = ttk.Scrollbar(
            canvas_frame, orient="vertical", command=self.canvas.yview,
            style="Modern.Vertical.TScrollbar",
        )
        self.canvas.configure(xscrollcommand=x_scroll.set, yscrollcommand=y_scroll.set)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        y_scroll.grid(row=0, column=1, sticky="ns")
        x_scroll.grid(row=1, column=0, sticky="ew")
        canvas_frame.rowconfigure(0, weight=1)
        canvas_frame.columnconfigure(0, weight=1)

        self.canvas.bind("<ButtonPress-1>", self.canvas_press)
        self.canvas.bind("<B1-Motion>", self.canvas_drag)
        self.canvas.bind("<ButtonRelease-1>", self.canvas_release)
        self.canvas.bind("<Double-Button-1>", self.edit_text_object_at)
        self.bind_all("<Delete>", lambda _event: self.delete_selected_object())

        status = tk.Frame(self.editor_tab, bg=COLORS["white"], height=38)
        status.pack(fill="x")
        status.pack_propagate(False)
        status_dot = tk.Canvas(status, width=18, height=18, bg=COLORS["white"], highlightthickness=0)
        status_dot.pack(side="left", padx=(16, 2))
        status_dot.create_oval(5, 5, 13, 13, fill=COLORS["pink"], outline="")
        tk.Label(
            status,
            textvariable=self.status_var,
            bg=COLORS["white"],
            fg=COLORS["muted"],
            font=("Segoe UI", 9),
        ).pack(side="left")
        self.progress = ttk.Progressbar(
            status, mode="indeterminate", length=220, style="Modern.Horizontal.TProgressbar"
        )
        self.progress.pack(side="right", padx=16, pady=11)
        self.set_tool(self.tool)
        self._build_ocr_tab()

    def _make_swatch(self, parent, color: str, command, background: str | None = None) -> tk.Canvas:
        bg = background or COLORS["cream"]
        swatch = tk.Canvas(
            parent, width=24, height=24, bg=bg,
            highlightthickness=0, cursor="hand2",
        )
        swatch.create_oval(
            2, 2, 22, 22, fill=color, outline=COLORS["purple_soft"], width=2
        )
        swatch.bind("<Button-1>", lambda _event: command())
        return swatch

    def _property_button(self, parent, text: str, command, background: str | None = None) -> tk.Button:
        bg = background or COLORS["cream"]
        return tk.Button(
            parent, text=text, command=command, bg=bg,
            fg=COLORS["muted"], activebackground=bg,
            activeforeground=COLORS["pink"], bd=0, cursor="hand2",
            font=("Segoe UI", 9),
        )

    def _build_ocr_tab(self) -> None:
        toolbar = tk.Frame(self.ocr_tab, bg=COLORS["white"], height=62)
        toolbar.pack(fill="x")
        toolbar.pack_propagate(False)
        tk.Label(
            toolbar,
            text="PHOTO TO SEARCHABLE PDF",
            bg=COLORS["white"],
            fg=COLORS["muted"],
            font=("Segoe UI Semibold", 8),
        ).pack(side="left", padx=(23, 12))
        RoundedButton(
            toolbar, "Add images", self.ocr_add_images, bg=COLORS["yellow"],
            fg=COLORS["purple_dark"], hover=COLORS["yellow_dark"], width=106, height=36,
        ).pack(side="left", padx=4, pady=13)
        RoundedButton(
            toolbar, "Add folder", self.ocr_add_folder, bg=COLORS["pink"],
            fg=COLORS["white"], hover=COLORS["pink_dark"], width=106, height=36,
        ).pack(side="left", padx=4, pady=13)
        RoundedButton(
            toolbar, "Save project", self.ocr_save_project, bg=COLORS["purple_soft"],
            fg=COLORS["purple_dark"], hover="#DED0F4", width=112, height=36,
        ).pack(side="left", padx=4, pady=13)
        RoundedButton(
            toolbar, "Open project", self.ocr_open_project, bg=COLORS["purple_soft"],
            fg=COLORS["purple_dark"], hover="#DED0F4", width=112, height=36,
        ).pack(side="left", padx=4, pady=13)
        RoundedButton(
            toolbar, "Export PDF", self.ocr_export_pdf, bg=COLORS["purple"],
            fg=COLORS["white"], hover=COLORS["purple_dark"], width=112, height=36,
        ).pack(side="right", padx=(4, 22), pady=13)
        RoundedButton(
            toolbar, "Save text", self.ocr_save_text, bg=COLORS["purple_soft"],
            fg=COLORS["purple_dark"], hover="#DED0F4", width=96, height=36,
        ).pack(side="right", padx=4, pady=13)

        options = tk.Frame(self.ocr_tab, bg=COLORS["cream"], height=48)
        options.pack(fill="x")
        options.pack_propagate(False)
        tk.Checkbutton(
            options,
            text="Photos show 2 pages",
            variable=self.ocr_two_page_var,
            bg=COLORS["cream"],
            fg=COLORS["purple_dark"],
            activebackground=COLORS["cream"],
            selectcolor=COLORS["white"],
            font=("Segoe UI Semibold", 9),
            bd=0,
        ).pack(side="left", padx=(23, 16), pady=12)
        tk.Checkbutton(
            options,
            text="Already cropped / screenshots",
            variable=self.ocr_already_cropped_var,
            bg=COLORS["cream"],
            fg=COLORS["purple_dark"],
            activebackground=COLORS["cream"],
            selectcolor=COLORS["white"],
            font=("Segoe UI Semibold", 9),
            bd=0,
        ).pack(side="left", padx=8, pady=12)

        body = tk.PanedWindow(
            self.ocr_tab,
            orient="horizontal",
            bg=COLORS["purple_soft"],
            sashwidth=5,
            sashrelief="flat",
            bd=0,
        )
        body.pack(fill="both", expand=True)

        left = tk.Frame(body, width=260, bg=COLORS["surface"], padx=16, pady=16)
        body.add(left, minsize=230, width=260)
        tk.Label(
            left, text="OCR PAGES", bg=COLORS["surface"],
            fg=COLORS["purple_dark"], font=("Segoe UI Semibold", 10),
        ).pack(anchor="w")
        self.ocr_page_list = tk.Listbox(
            left,
            exportselection=False,
            bg=COLORS["white"],
            fg=COLORS["ink"],
            selectbackground=COLORS["pink"],
            selectforeground=COLORS["white"],
            activestyle="none",
            bd=0,
            highlightthickness=1,
            highlightbackground=COLORS["purple_soft"],
            highlightcolor=COLORS["purple"],
            font=("Segoe UI Semibold", 10),
            relief="flat",
        )
        self.ocr_page_list.pack(fill="both", expand=True, pady=(10, 12), ipady=8)
        self.ocr_page_list.bind("<<ListboxSelect>>", self.ocr_select_page)
        page_buttons = tk.Frame(left, bg=COLORS["surface"])
        page_buttons.pack(fill="x")
        RoundedButton(
            page_buttons, "Move up", lambda: self.ocr_move_page(-1),
            bg=COLORS["purple_soft"], fg=COLORS["purple_dark"],
            hover="#DED0F4", width=106, height=34,
        ).pack(side="left")
        RoundedButton(
            page_buttons, "Move down", lambda: self.ocr_move_page(1),
            bg=COLORS["purple_soft"], fg=COLORS["purple_dark"],
            hover="#DED0F4", width=106, height=34,
        ).pack(side="right")
        RoundedButton(
            left, "Delete page", self.ocr_delete_page, bg="#FCE3EF",
            fg=COLORS["pink_dark"], hover="#F7CADD", width=218, height=35,
        ).pack(pady=(7, 0))

        center = tk.Frame(body, bg=COLORS["workspace"])
        body.add(center, stretch="always")
        preview_tools = tk.Frame(center, bg=COLORS["purple_deep"], height=49)
        preview_tools.pack(fill="x")
        preview_tools.pack_propagate(False)
        tk.Label(
            preview_tools, text="Processed page preview", bg=COLORS["purple_deep"],
            fg=COLORS["yellow"], font=("Segoe UI Semibold", 9),
        ).pack(side="left", padx=18)
        RoundedButton(
            preview_tools, "Rotate right", lambda: self.ocr_rotate_page(-90),
            bg="#49325E", fg=COLORS["white"], hover=COLORS["purple"],
            width=96, height=30,
        ).pack(side="right", padx=(4, 14), pady=9)
        RoundedButton(
            preview_tools, "Rotate left", lambda: self.ocr_rotate_page(90),
            bg="#49325E", fg=COLORS["white"], hover=COLORS["purple"],
            width=92, height=30,
        ).pack(side="right", padx=4, pady=9)
        self.ocr_preview = tk.Label(
            center,
            bg=COLORS["workspace"],
            fg="#A899B5",
            text="Add images or a folder to begin",
            font=("Segoe UI Semibold", 15),
            anchor="center",
        )
        self.ocr_preview.pack(fill="both", expand=True, padx=20, pady=20)
        self.ocr_preview.bind("<Configure>", lambda _event: self.ocr_show_current())

        right = tk.Frame(body, width=390, bg=COLORS["surface"], padx=16, pady=16)
        body.add(right, minsize=320, width=410)
        header = tk.Frame(right, bg=COLORS["surface"])
        header.pack(fill="x")
        tk.Label(
            header, text="OCR TEXT", bg=COLORS["surface"],
            fg=COLORS["purple_dark"], font=("Segoe UI Semibold", 10),
        ).pack(side="left")
        RoundedButton(
            header, "Run OCR again", self.ocr_current,
            bg=COLORS["purple_soft"], fg=COLORS["purple_dark"],
            hover="#DED0F4", width=116, height=32,
        ).pack(side="right")
        self.ocr_text_editor = tk.Text(
            right,
            wrap="word",
            undo=True,
            bg=COLORS["white"],
            fg=COLORS["ink"],
            insertbackground=COLORS["pink"],
            font=("Segoe UI", 10),
            relief="flat",
            bd=8,
        )
        self.ocr_text_editor.pack(fill="both", expand=True, pady=(10, 8))
        self.ocr_text_editor.bind("<<Modified>>", self.ocr_text_changed)

        status = tk.Frame(self.ocr_tab, bg=COLORS["white"], height=38)
        status.pack(fill="x")
        status.pack_propagate(False)
        tk.Label(
            status,
            textvariable=self.ocr_status_var,
            bg=COLORS["white"],
            fg=COLORS["muted"],
            font=("Segoe UI", 9),
        ).pack(side="left", padx=16)
        self.ocr_progress = ttk.Progressbar(
            status,
            variable=self.ocr_progress_var,
            maximum=100,
            mode="determinate",
            length=260,
            style="Modern.Horizontal.TProgressbar",
        )
        self.ocr_progress.pack(side="right", padx=16, pady=11)

    def ocr_set_busy(self, busy: bool, status: str) -> None:
        self.ocr_busy = busy
        self.ocr_status_var.set(status)
        self.ocr_progress.configure(mode="indeterminate" if busy else "determinate")
        if busy:
            self.ocr_progress.start(12)
        else:
            self.ocr_progress.stop()
            self.ocr_progress_var.set(0)

    def ocr_add_images(self) -> None:
        paths = filedialog.askopenfilenames(
            title="Choose photos",
            filetypes=[("Images", "*.jpg *.jpeg *.png *.tif *.tiff *.bmp *.webp")],
        )
        if paths:
            self.ocr_process_paths([Path(path) for path in paths])

    def ocr_add_folder(self) -> None:
        folder = filedialog.askdirectory(title="Choose image folder")
        if not folder:
            return
        paths = sorted(
            path for path in Path(folder).iterdir() if path.suffix.lower() in IMAGE_TYPES
        )
        if not paths:
            messagebox.showinfo(APP_TITLE, "The folder contains no supported images.")
            return
        self.ocr_process_paths(paths)

    def ocr_process_paths(self, paths: list[Path]) -> None:
        if self.ocr_busy:
            return
        two_page_spread = self.ocr_two_page_var.get()
        already_cropped = self.ocr_already_cropped_var.get()
        action = "Loading" if already_cropped else "Correcting"
        self.ocr_set_busy(True, f"{action} and OCR-processing {len(paths)} image(s)...")

        def worker() -> None:
            try:
                total = len(paths)
                for number, path in enumerate(paths, 1):
                    self.events.put(("ocr_status", f"{action} {number}/{total}: {path.name}"))
                    images = process_photo(path, two_page_spread, already_cropped)
                    pages = []
                    for page_number, image in enumerate(images, 1):
                        self.events.put(
                            (
                                "ocr_status",
                                f"OCR {number}/{total}, page {page_number}/{len(images)}: {path.name}",
                            )
                        )
                        pages.append(OcrPage(image=image, text=ocr_text(image), source=str(path)))
                    self.events.put(("ocr_pages", pages))
                self.events.put(("ocr_done_generator", f"Done - processed {total} image(s)"))
            except Exception:
                self.events.put(("ocr_error", traceback.format_exc()))

        threading.Thread(target=worker, daemon=True).start()

    def ocr_refresh_page_list(self, select_last: bool = False) -> None:
        old = self.ocr_current_index
        self.ocr_page_list.delete(0, "end")
        for index, page in enumerate(self.ocr_pages, 1):
            source = Path(page.source).name if page.source else "project page"
            self.ocr_page_list.insert("end", f"{index:03d}  {source}")
        if self.ocr_pages:
            target = len(self.ocr_pages) - 1 if select_last else min(old or 0, len(self.ocr_pages) - 1)
            self.ocr_page_list.selection_clear(0, "end")
            self.ocr_page_list.selection_set(target)
            self.ocr_page_list.see(target)
            self.ocr_current_index = target
            self.ocr_show_current()
        else:
            self.ocr_current_index = None
            self.ocr_preview.configure(image="", text="Add images or a folder to begin")
            self.ocr_load_text("")

    def ocr_select_page(self, _event=None) -> None:
        selection = self.ocr_page_list.curselection()
        if not selection:
            return
        self.ocr_store_text()
        self.ocr_current_index = selection[0]
        self.ocr_show_current()

    def ocr_show_current(self) -> None:
        if self.ocr_current_index is None or not self.ocr_pages:
            return
        page = self.ocr_pages[self.ocr_current_index]
        image = page.image.copy()
        width = max(220, self.ocr_preview.winfo_width() - 34)
        height = max(220, self.ocr_preview.winfo_height() - 34)
        image.thumbnail((width, height), Image.Resampling.LANCZOS)
        self.ocr_preview_photo = ImageTk.PhotoImage(image)
        self.ocr_preview.configure(image=self.ocr_preview_photo, text="")
        self.ocr_load_text(page.text)

    def ocr_load_text(self, text: str) -> None:
        self.ocr_text_editor.delete("1.0", "end")
        self.ocr_text_editor.insert("1.0", text)
        self.ocr_text_editor.edit_modified(False)

    def ocr_store_text(self) -> None:
        if self.ocr_current_index is not None and self.ocr_current_index < len(self.ocr_pages):
            self.ocr_pages[self.ocr_current_index].text = self.ocr_text_editor.get("1.0", "end-1c")

    def ocr_text_changed(self, _event=None) -> None:
        if self.ocr_text_editor.edit_modified():
            self.ocr_store_text()
            self.ocr_text_editor.edit_modified(False)

    def ocr_rotate_page(self, degrees: int) -> None:
        if self.ocr_current_index is None:
            return
        self.ocr_pages[self.ocr_current_index].image = self.ocr_pages[self.ocr_current_index].image.rotate(
            degrees, expand=True
        )
        self.ocr_show_current()

    def ocr_move_page(self, direction: int) -> None:
        if self.ocr_current_index is None:
            return
        target = self.ocr_current_index + direction
        if not 0 <= target < len(self.ocr_pages):
            return
        self.ocr_pages[self.ocr_current_index], self.ocr_pages[target] = (
            self.ocr_pages[target],
            self.ocr_pages[self.ocr_current_index],
        )
        self.ocr_current_index = target
        self.ocr_refresh_page_list()
        self.ocr_page_list.selection_clear(0, "end")
        self.ocr_page_list.selection_set(target)

    def ocr_delete_page(self) -> None:
        if self.ocr_current_index is None:
            return
        del self.ocr_pages[self.ocr_current_index]
        self.ocr_current_index = min(self.ocr_current_index, len(self.ocr_pages) - 1) if self.ocr_pages else None
        self.ocr_refresh_page_list()

    def ocr_current(self) -> None:
        if self.ocr_current_index is None or self.ocr_busy:
            return
        index = self.ocr_current_index
        image = self.ocr_pages[index].image.copy()
        self.ocr_set_busy(True, f"OCR-processing page {index + 1}...")

        def worker() -> None:
            try:
                self.events.put(("ocr_text", (index, ocr_text(image))))
                self.events.put(("ocr_done_generator", f"OCR done for page {index + 1}"))
            except Exception:
                self.events.put(("ocr_error", traceback.format_exc()))

        threading.Thread(target=worker, daemon=True).start()

    def ocr_export_pdf(self) -> None:
        if not self.ocr_pages or self.ocr_busy:
            return
        self.ocr_store_text()
        destination = filedialog.asksaveasfilename(
            title="Save searchable PDF",
            defaultextension=".pdf",
            filetypes=[("PDF", "*.pdf")],
            initialfile="searchable_from_photos.pdf",
        )
        if not destination:
            return
        images = [page.image.copy() for page in self.ocr_pages]
        self.ocr_set_busy(True, "Creating searchable PDF...")

        def worker() -> None:
            try:
                export_searchable_pdf(images, destination)
                self.events.put(("ocr_pdf_done", destination))
            except Exception:
                self.events.put(("ocr_error", traceback.format_exc()))

        threading.Thread(target=worker, daemon=True).start()

    def ocr_save_text(self) -> None:
        if not self.ocr_pages:
            return
        self.ocr_store_text()
        destination = filedialog.asksaveasfilename(
            title="Save OCR text",
            defaultextension=".txt",
            filetypes=[("Text file", "*.txt")],
            initialfile="OCR_text.txt",
        )
        if not destination:
            return
        sections = [
            f"--- Page {index} ---\n{page.text.strip()}"
            for index, page in enumerate(self.ocr_pages, 1)
        ]
        Path(destination).write_text("\n\n".join(sections), encoding="utf-8")
        self.ocr_status_var.set(f"Text saved: {destination}")

    def ocr_save_project(self) -> None:
        if not self.ocr_pages:
            return
        self.ocr_store_text()
        folder = filedialog.askdirectory(title="Choose a project folder")
        if not folder:
            return
        project = Path(folder)
        pages_folder = project / "pages"
        pages_folder.mkdir(parents=True, exist_ok=True)
        data = {"version": 1, "pages": []}
        for index, page in enumerate(self.ocr_pages, 1):
            filename = f"page_{index:04d}.jpg"
            page.image.convert("RGB").save(pages_folder / filename, quality=92)
            data["pages"].append(
                {"image": f"pages/{filename}", "text": page.text, "source": page.source}
            )
        (project / "project.json").write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        self.ocr_status_var.set(f"Project saved: {project}")

    def ocr_open_project(self) -> None:
        filename = filedialog.askopenfilename(
            title="Open OCR project",
            filetypes=[("OCR project", "project.json"), ("JSON", "*.json")],
        )
        if not filename:
            return
        project_file = Path(filename)
        data = json.loads(project_file.read_text(encoding="utf-8"))
        pages = []
        for item in data.get("pages", []):
            image_path = project_file.parent / item["image"]
            with Image.open(image_path) as image:
                pages.append(
                    OcrPage(
                        image=image.convert("RGB").copy(),
                        text=item.get("text", ""),
                        source=item.get("source", ""),
                    )
                )
        self.ocr_pages = pages
        self.ocr_current_index = 0 if pages else None
        self.ocr_refresh_page_list()
        self.ocr_status_var.set(f"Project opened: {project_file.parent}")

    def require_document(self) -> bool:
        if self.document is None or self.document.page_count == 0:
            messagebox.showinfo(APP_TITLE, "Open a PDF first.")
            return False
        return True

    def set_tool(self, tool: str) -> None:
        self.tool = tool
        self.tool_var.set(f"Tool: {TOOLS[tool]}")
        for key, button in self.tool_buttons.items():
            if key == tool:
                button.set_palette(COLORS["purple"], COLORS["white"], COLORS["pink"])
            else:
                button.set_palette(
                    COLORS["purple_soft"], COLORS["purple_dark"], "#DED0F4"
                )
        cursors = {
            "select": "arrow",
            "edit_text": "xterm",
            "text_box": "crosshair",
            "line": "crosshair",
            "shape": "crosshair",
            "image": "crosshair",
        }
        self.canvas.configure(cursor=cursors[tool])

    def choose_edge_color(self) -> None:
        rgb, _hex = colorchooser.askcolor(
            color=self._color_hex(self.edge_color), title="Choose edge colour"
        )
        if rgb:
            self.edge_color = tuple(channel / 255 for channel in rgb)
            self.edge_swatch.itemconfigure(1, fill=self._color_hex(self.edge_color))

    def choose_fill_color(self) -> None:
        rgb, _hex = colorchooser.askcolor(
            color=self._color_hex(self.fill_color), title="Choose fill colour"
        )
        if rgb:
            self.fill_color = tuple(channel / 255 for channel in rgb)
            self.fill_enabled.set(True)
            self.fill_swatch.itemconfigure(1, fill=self._color_hex(self.fill_color))

    @staticmethod
    def _color_hex(color: tuple[float, float, float]) -> str:
        return "#%02x%02x%02x" % tuple(round(value * 255) for value in color)

    def open_pdf(self) -> None:
        filename = filedialog.askopenfilename(
            title="Open PDF", filetypes=[("PDF files", "*.pdf")]
        )
        if not filename:
            return
        self.open_pdf_path(filename)

    def open_pdf_path(self, filename: str | Path) -> None:
        try:
            document = fitz.open(filename)
            if document.needs_pass:
                password = simpledialog.askstring(APP_TITLE, "PDF password:", show="*")
                if not password or not document.authenticate(password):
                    document.close()
                    raise ValueError("The password was not accepted.")
            if self.document:
                self.document.close()
            self.document = document
            self.filename = Path(filename)
            self.current_page = 0
            self.selected_annot_xref = None
            self.undo_stack.clear()
            self._refresh_pages()
            self.status_var.set(f"Opened {self.filename}")
            if hasattr(self, "notebook"):
                self.notebook.select(self.editor_tab)
        except Exception as error:
            messagebox.showerror(APP_TITLE, str(error))

    def save_pdf(self) -> None:
        if not self.require_document():
            return
        if self.filename is None:
            self.save_as()
            return
        destination = self.filename
        try:
            self.document.saveIncr()
            self.status_var.set(f"Saved {destination}")
            messagebox.showinfo(APP_TITLE, f"Saved:\n{destination}", parent=self)
            self.render_current()
            return
        except Exception as error:
            incremental_error = error

        temporary = destination.with_name(destination.stem + ".openpdf.tmp.pdf")
        try:
            self.document.save(temporary, garbage=4, deflate=True)
            current_page = self.current_page
            self.document.close()
            self.document = None
            temporary.replace(destination)
            self.document = fitz.open(destination)
            self.current_page = min(current_page, self.document.page_count - 1)
            self.selected_annot_xref = None
            self._refresh_pages()
            self.status_var.set(f"Saved {destination}")
            messagebox.showinfo(APP_TITLE, f"Saved:\n{destination}", parent=self)
            self.render_current()
        except Exception as error:
            if self.document is None and destination.exists():
                try:
                    self.document = fitz.open(destination)
                    self._refresh_pages()
                    self.render_current()
                except Exception:
                    pass
            messagebox.showerror(
                APP_TITLE,
                (
                    "Could not overwrite the PDF.\n\n"
                    "If it is open in another PDF reader, close it and try again.\n"
                    "You can also use Save as to write a new file.\n\n"
                    f"First save attempt: {incremental_error}\n"
                    f"Fallback save attempt: {error}"
                ),
                parent=self,
            )
        finally:
            if temporary.exists():
                try:
                    temporary.unlink()
                except OSError:
                    pass

    def save_as(self) -> None:
        if not self.require_document():
            return
        destination = filedialog.asksaveasfilename(
            title="Save PDF as",
            defaultextension=".pdf",
            filetypes=[("PDF files", "*.pdf")],
            initialfile=(self.filename.stem + "_edited.pdf") if self.filename else "edited.pdf",
        )
        if not destination:
            return
        try:
            current_page = self.current_page
            self.document.save(destination, garbage=4, deflate=True)
            self.filename = Path(destination)
            self.document.close()
            self.document = fitz.open(destination)
            self.current_page = min(current_page, self.document.page_count - 1)
            self.selected_annot_xref = None
            self._refresh_pages()
            self.status_var.set(f"Saved {destination}")
            messagebox.showinfo(APP_TITLE, f"Saved:\n{destination}", parent=self)
            self.render_current()
        except Exception as error:
            messagebox.showerror(APP_TITLE, str(error))

    def snapshot(self) -> None:
        if self.document:
            self._push_undo_snapshot(self.document.tobytes(garbage=3, deflate=True))

    def _push_undo_snapshot(self, snapshot: bytes) -> None:
        self.undo_stack.append(snapshot)
        if len(self.undo_stack) > 15:
            del self.undo_stack[0]

    def undo(self) -> None:
        if not self.undo_stack:
            return
        current = self.current_page
        if self.document:
            self.document.close()
        self.document = fitz.open(stream=self.undo_stack.pop(), filetype="pdf")
        self.current_page = min(current, self.document.page_count - 1)
        self.selected_annot_xref = None
        self._refresh_pages()
        self.status_var.set("Undid last change")

    def _refresh_pages(self) -> None:
        self.page_list.delete(0, "end")
        if not self.document:
            return
        for index in range(self.document.page_count):
            self.page_list.insert("end", f"Page {index + 1}")
        if self.document.page_count:
            self.current_page = min(self.current_page, self.document.page_count - 1)
            self.page_list.selection_set(self.current_page)
            self.page_list.see(self.current_page)
        self.render_current()

    def _select_page(self, _event=None) -> None:
        selection = self.page_list.curselection()
        if selection:
            self.current_page = selection[0]
            self.selected_annot_xref = None
            self.render_current()

    def render_current(self) -> None:
        self.canvas.delete("all")
        if not self.document or self.document.page_count == 0:
            self.page_var.set("No document")
            self.canvas.create_text(
                70,
                70,
                anchor="nw",
                text="Open a PDF to start editing",
                fill="#A899B5",
                font=("Segoe UI Semibold", 16),
            )
            self.canvas.create_text(
                70,
                104,
                anchor="nw",
                text="Your document will appear in this workspace.",
                fill="#786A83",
                font=("Segoe UI", 10),
            )
            return
        page = self.document[self.current_page]
        image = render_page(page, self.zoom)
        self.preview_photo = ImageTk.PhotoImage(image)
        self.canvas.create_rectangle(
            PAGE_MARGIN + 8,
            PAGE_MARGIN + 10,
            PAGE_MARGIN + image.width + 8,
            PAGE_MARGIN + image.height + 10,
            fill=COLORS["shadow"],
            outline="",
        )
        self.canvas.create_image(
            PAGE_MARGIN,
            PAGE_MARGIN,
            image=self.preview_photo,
            anchor="nw",
            tags="page",
        )
        self._draw_object_selection()
        self.canvas.configure(
            scrollregion=(
                0,
                0,
                image.width + PAGE_MARGIN * 2,
                image.height + PAGE_MARGIN * 2,
            )
        )
        self.page_var.set(
            f"Page {self.current_page + 1} / {self.document.page_count}  |  {self.zoom * 100:.0f}%"
        )

    def change_zoom(self, factor: float) -> None:
        self.zoom = min(4.0, max(0.35, self.zoom * factor))
        self.render_current()

    def canvas_point(self, event) -> fitz.Point:
        x = (self.canvas.canvasx(event.x) - PAGE_MARGIN) / self.zoom
        y = (self.canvas.canvasy(event.y) - PAGE_MARGIN) / self.zoom
        return fitz.Point(x, y)

    def _pdf_to_canvas(self, point: fitz.Point) -> tuple[float, float]:
        return (
            PAGE_MARGIN + point.x * self.zoom,
            PAGE_MARGIN + point.y * self.zoom,
        )

    def _selected_annotation(self) -> fitz.Annot | None:
        if (
            self.document is None
            or self.selected_annot_xref is None
            or self.current_page >= self.document.page_count
        ):
            return None
        try:
            self.annotation_page = self.document[self.current_page]
            return self.annotation_page.load_annot(self.selected_annot_xref)
        except Exception:
            self.selected_annot_xref = None
            return None

    def _draw_object_selection(self) -> None:
        annotation = self._selected_annotation()
        if annotation is None:
            return
        rect = annotation.rect
        x0, y0 = self._pdf_to_canvas(rect.tl)
        x1, y1 = self._pdf_to_canvas(rect.br)
        self.canvas.create_rectangle(
            x0, y0, x1, y1,
            outline=COLORS["pink"],
            width=2,
            dash=(6, 3),
            tags="selection",
        )
        handle_size = 5
        for name, x, y in (
            ("nw", x0, y0),
            ("ne", x1, y0),
            ("se", x1, y1),
            ("sw", x0, y1),
        ):
            self.canvas.create_rectangle(
                x - handle_size,
                y - handle_size,
                x + handle_size,
                y + handle_size,
                fill=COLORS["yellow"],
                outline=COLORS["purple_dark"],
                width=1,
                tags=("selection", f"handle-{name}"),
            )

    def _selection_handle_at(self, event) -> str | None:
        x = self.canvas.canvasx(event.x)
        y = self.canvas.canvasy(event.y)
        for item in reversed(self.canvas.find_overlapping(x - 2, y - 2, x + 2, y + 2)):
            for tag in self.canvas.gettags(item):
                if tag.startswith("handle-"):
                    return tag.removeprefix("handle-")
        return None

    def _annotation_at(self, point: fitz.Point) -> fitz.Annot | None:
        if self.document is None:
            return None
        self.annotation_page = self.document[self.current_page]
        annotations = list(self.annotation_page.annots() or [])
        tolerance = 4 / self.zoom
        hit_rect = fitz.Rect(
            point.x - tolerance,
            point.y - tolerance,
            point.x + tolerance,
            point.y + tolerance,
        )
        for annotation in reversed(annotations):
            if annotation.rect.intersects(hit_rect):
                return annotation
        return None

    def _start_object_transform(self, event, point: fitz.Point) -> None:
        annotation = self._selected_annotation()
        handle = self._selection_handle_at(event) if annotation else None
        if annotation is not None and handle:
            mode = f"resize-{handle}"
        elif annotation is not None and annotation.rect.contains(point):
            mode = "move"
        else:
            annotation = self._annotation_at(point)
            if annotation is None:
                self.selected_annot_xref = None
                self.render_current()
                self.status_var.set("No object selected")
                return
            self.selected_annot_xref = annotation.xref
            mode = "move"

        self.object_drag_mode = mode
        self.object_drag_start = point
        self.object_original_rect = fitz.Rect(annotation.rect)
        self.object_original_vertices = (
            [fitz.Point(vertex) for vertex in annotation.vertices]
            if annotation.type[0] == fitz.PDF_ANNOT_LINE
            else None
        )
        self.object_snapshot = self.document.tobytes(garbage=3, deflate=True)
        self.object_changed = False
        self.render_current()
        self.status_var.set("Object selected - drag to move or use a corner to resize")

    def _drag_selected_object(self, event) -> None:
        annotation = self._selected_annotation()
        if (
            annotation is None
            or self.object_drag_start is None
            or self.object_original_rect is None
            or self.object_drag_mode is None
        ):
            return
        current = self.canvas_point(event)
        original = self.object_original_rect
        dx = current.x - self.object_drag_start.x
        dy = current.y - self.object_drag_start.y

        if self.object_drag_mode == "move":
            new_rect = original + (dx, dy, dx, dy)
            page_rect = self.document[self.current_page].rect
            if new_rect.x0 < page_rect.x0:
                new_rect += (page_rect.x0 - new_rect.x0, 0, page_rect.x0 - new_rect.x0, 0)
            if new_rect.y0 < page_rect.y0:
                new_rect += (0, page_rect.y0 - new_rect.y0, 0, page_rect.y0 - new_rect.y0)
            if new_rect.x1 > page_rect.x1:
                new_rect += (page_rect.x1 - new_rect.x1, 0, page_rect.x1 - new_rect.x1, 0)
            if new_rect.y1 > page_rect.y1:
                new_rect += (0, page_rect.y1 - new_rect.y1, 0, page_rect.y1 - new_rect.y1)
        else:
            new_rect = self._resized_object_rect(
                original,
                current,
                self.object_drag_mode.removeprefix("resize-"),
                annotation.info.get("content", "") in {"image", "square", "circle"},
            )

        try:
            self._set_annotation_rect(annotation, new_rect)
            self.object_changed = True
            self.render_current()
        except Exception as error:
            self.status_var.set(f"Object could not be transformed: {error}")

    @staticmethod
    def _resized_object_rect(
        original: fitz.Rect,
        point: fitz.Point,
        handle: str,
        preserve_ratio: bool = False,
    ) -> fitz.Rect:
        minimum = 12.0
        if preserve_ratio:
            anchor_x = original.x1 if "w" in handle else original.x0
            anchor_y = original.y1 if "n" in handle else original.y0
            width = max(minimum, abs(point.x - anchor_x))
            height = max(minimum, abs(point.y - anchor_y))
            ratio = original.width / max(original.height, 0.001)
            if width / height > ratio:
                height = width / ratio
            else:
                width = height * ratio
            x0, x1 = (
                (anchor_x - width, anchor_x)
                if "w" in handle
                else (anchor_x, anchor_x + width)
            )
            y0, y1 = (
                (anchor_y - height, anchor_y)
                if "n" in handle
                else (anchor_y, anchor_y + height)
            )
            return fitz.Rect(x0, y0, x1, y1)

        x0, y0, x1, y1 = original
        if "w" in handle:
            x0 = min(point.x, x1 - minimum)
        if "e" in handle:
            x1 = max(point.x, x0 + minimum)
        if "n" in handle:
            y0 = min(point.y, y1 - minimum)
        if "s" in handle:
            y1 = max(point.y, y0 + minimum)
        return fitz.Rect(x0, y0, x1, y1)

    def _finish_object_transform(self) -> None:
        if self.object_changed and self.object_snapshot is not None:
            self._push_undo_snapshot(self.object_snapshot)
            self.status_var.set("Object transformed")
        self.object_drag_mode = None
        self.object_drag_start = None
        self.object_original_rect = None
        self.object_original_vertices = None
        self.object_snapshot = None
        self.object_changed = False

    def rotate_selected_object(self, degrees: int) -> None:
        annotation = self._selected_annotation()
        if annotation is None:
            self.status_var.set("Select an object before rotating")
            return
        try:
            self.snapshot()
            if annotation.type[0] == fitz.PDF_ANNOT_LINE:
                vertices = [fitz.Point(vertex) for vertex in annotation.vertices]
                center = fitz.Point(
                    sum(point.x for point in vertices) / len(vertices),
                    sum(point.y for point in vertices) / len(vertices),
                )
                radians = math.radians(degrees)
                rotated = []
                for point in vertices:
                    dx = point.x - center.x
                    dy = point.y - center.y
                    rotated.append(
                        fitz.Point(
                            center.x + dx * math.cos(radians) - dy * math.sin(radians),
                            center.y + dx * math.sin(radians) + dy * math.cos(radians),
                        )
                    )
                self._set_line_vertices(annotation, rotated)
            else:
                annotation.set_rotation((annotation.rotation + degrees) % 360)
                annotation.update()
            self.render_current()
            self.status_var.set("Object rotated")
        except Exception as error:
            messagebox.showerror(APP_TITLE, f"This object cannot be rotated:\n{error}")

    def delete_selected_object(self) -> None:
        annotation = self._selected_annotation()
        if annotation is None:
            return
        self.snapshot()
        self.document[self.current_page].delete_annot(annotation)
        self.selected_annot_xref = None
        self.render_current()
        self.status_var.set("Object deleted")

    def edit_text_object_at(self, event) -> None:
        if not self.require_document() or self.busy:
            return
        point = self.canvas_point(event)
        annotation = self._annotation_at(point)
        if annotation is None or annotation.type[0] != fitz.PDF_ANNOT_FREE_TEXT:
            return
        self.selected_annot_xref = annotation.xref
        self.edit_selected_text_object()

    def edit_selected_text_object(self) -> None:
        annotation = self._selected_annotation()
        if annotation is None:
            self.status_var.set("Select a text box before editing")
            return
        if annotation.type[0] != fitz.PDF_ANNOT_FREE_TEXT:
            self.status_var.set("The selected object is not a text box")
            return
        current_text = annotation.info.get("content", "")
        new_text = simpledialog.askstring(
            "Edit text box",
            "Text:",
            initialvalue=current_text,
            parent=self,
        )
        if new_text is None or new_text == current_text:
            return
        self.snapshot()
        annotation = self._selected_annotation()
        annotation.set_info(content=new_text)
        annotation.update()
        self.render_current()
        self.status_var.set("Text box updated")

    def _set_annotation_rect(
        self, annotation: fitz.Annot, new_rect: fitz.Rect
    ) -> None:
        if (
            annotation.type[0] != fitz.PDF_ANNOT_LINE
            or not self.object_original_vertices
            or self.object_original_rect is None
        ):
            annotation.set_rect(new_rect)
            annotation.update()
            return

        old = self.object_original_rect
        scale_x = new_rect.width / max(old.width, 0.001)
        scale_y = new_rect.height / max(old.height, 0.001)
        vertices = [
            fitz.Point(
                new_rect.x0 + (point.x - old.x0) * scale_x,
                new_rect.y0 + (point.y - old.y0) * scale_y,
            )
            for point in self.object_original_vertices
        ]
        self._set_line_vertices(annotation, vertices)

    def _set_line_vertices(
        self, annotation: fitz.Annot, vertices: list[fitz.Point]
    ) -> None:
        page = self.document[self.current_page]
        inverse = ~page.transformation_matrix
        pdf_points = [point * inverse for point in vertices]
        value = "[%s]" % " ".join(
            f"{coordinate:g}"
            for point in pdf_points
            for coordinate in (point.x, point.y)
        )
        self.document.xref_set_key(annotation.xref, "L", value)
        annotation = page.load_annot(annotation.xref)
        annotation.update()

    def canvas_press(self, event) -> None:
        if not self.require_document() or self.busy:
            return
        point = self.canvas_point(event)
        page = self.document[self.current_page]
        if not page.rect.contains(point):
            return

        if self.tool == "select":
            self._start_object_transform(event, point)
            return

        if self.tool == "edit_text":
            block = find_text_block(page, point)
            if not block:
                self.status_var.set("No editable text line found at that position")
                return
            new_text = simpledialog.askstring(
                "Change text",
                "Replace this text:",
                initialvalue=block.text,
                parent=self,
            )
            if new_text is not None and new_text != block.text:
                self.snapshot()
                replace_text(page, block, new_text)
                self.render_current()
                self.status_var.set("Text replaced")
            return

        self.drag_start = (self.canvas.canvasx(event.x), self.canvas.canvasy(event.y))
        color = self._color_hex(self.edge_color)
        if self.tool == "line":
            style = self.line_style_var.get()
            self.drag_item = self.canvas.create_line(
                *self.drag_start,
                *self.drag_start,
                fill=color,
                width=max(1, self.line_width_var.get() * self.zoom),
                dash=(3, 4) if style == "Dotted" else (),
                arrow=tk.LAST if style == "Arrow" else tk.NONE,
                arrowshape=(12, 14, 5),
            )
        elif self.tool == "shape" and self.shape_var.get() == "Circle":
            self.drag_item = self.canvas.create_oval(
                *self.drag_start,
                *self.drag_start,
                outline=color,
                fill=self._color_hex(self.fill_color) if self.fill_enabled.get() else "",
                width=max(1, self.line_width_var.get() * self.zoom),
            )
        else:
            self.drag_item = self.canvas.create_rectangle(
                *self.drag_start,
                *self.drag_start,
                outline=color,
                fill=(
                    self._color_hex(self.fill_color)
                    if self.tool == "shape" and self.fill_enabled.get()
                    else ""
                ),
                width=max(1, self.line_width_var.get() * self.zoom),
                dash=(5, 3) if self.tool != "shape" else (),
            )

    def canvas_drag(self, event) -> None:
        if self.object_drag_mode:
            self._drag_selected_object(event)
            return
        if self.drag_item is None or self.drag_start is None:
            return
        end_x = self.canvas.canvasx(event.x)
        end_y = self.canvas.canvasy(event.y)
        if self.tool == "shape" and self.shape_var.get() in {"Square", "Circle"}:
            end_x, end_y = self._equal_dimension_endpoint(
                self.drag_start[0], self.drag_start[1], end_x, end_y
            )
        self.canvas.coords(
            self.drag_item,
            *self.drag_start,
            end_x,
            end_y,
        )

    def canvas_release(self, event) -> None:
        if self.object_drag_mode:
            self._finish_object_transform()
            return
        if self.drag_start is None:
            return
        end_canvas = (self.canvas.canvasx(event.x), self.canvas.canvasy(event.y))
        if self.tool == "shape" and self.shape_var.get() in {"Square", "Circle"}:
            end_canvas = self._equal_dimension_endpoint(
                self.drag_start[0], self.drag_start[1], *end_canvas
            )
        start = fitz.Point(
            (self.drag_start[0] - PAGE_MARGIN) / self.zoom,
            (self.drag_start[1] - PAGE_MARGIN) / self.zoom,
        )
        end = fitz.Point(
            (end_canvas[0] - PAGE_MARGIN) / self.zoom,
            (end_canvas[1] - PAGE_MARGIN) / self.zoom,
        )
        self.drag_start = None
        if self.drag_item is not None:
            self.canvas.delete(self.drag_item)
            self.drag_item = None

        page = self.document[self.current_page]
        rect = fitz.Rect(start, end).normalize() & page.rect
        if self.tool != "line" and (rect.width < 8 or rect.height < 8):
            return

        try:
            if self.tool == "line":
                self.snapshot()
                annotation = self._add_line_annotation(page, start, end)
                self.selected_annot_xref = annotation.xref
            elif self.tool == "shape":
                self.snapshot()
                fill = self.fill_color if self.fill_enabled.get() else None
                width = max(0.5, self.line_width_var.get())
                if self.shape_var.get() == "Circle":
                    annotation = page.add_circle_annot(rect)
                else:
                    annotation = page.add_rect_annot(rect)
                annotation.set_colors(stroke=self.edge_color, fill=fill)
                annotation.set_border(width=width)
                annotation.set_info(
                    title="PDFeditEasy",
                    subject="PDFeditEasy Object",
                    content=self.shape_var.get().lower(),
                )
                annotation.update()
                self.selected_annot_xref = annotation.xref
            elif self.tool == "text_box":
                text = simpledialog.askstring("Text box", "Text:", parent=self)
                if text:
                    size = simpledialog.askfloat(
                        "Text size", "Font size:", initialvalue=12, minvalue=4, maxvalue=72
                    )
                    if size:
                        self.snapshot()
                        annotation = page.add_freetext_annot(
                            rect,
                            text,
                            fontsize=size,
                            fontname="Helv",
                            text_color=(0, 0, 0),
                            fill_color=self.fill_color if self.fill_enabled.get() else None,
                        )
                        annotation.set_info(
                            title="PDFeditEasy",
                            subject="PDFeditEasy Text Object",
                        )
                        annotation.update()
                        self.selected_annot_xref = annotation.xref
            elif self.tool == "image":
                filename = filedialog.askopenfilename(
                    title="Insert image",
                    filetypes=[
                        ("Images", "*.png *.jpg *.jpeg *.bmp *.tif *.tiff *.webp"),
                        ("All files", "*.*"),
                    ],
                )
                if filename:
                    self.snapshot()
                    self.selected_annot_xref = add_image_annotation(
                        self.document,
                        self.current_page,
                        rect,
                        filename,
                    )
            if self.selected_annot_xref is not None:
                self.set_tool("select")
            self.render_current()
        except Exception as error:
            messagebox.showerror(APP_TITLE, str(error))

    @staticmethod
    def _equal_dimension_endpoint(
        start_x: float, start_y: float, end_x: float, end_y: float
    ) -> tuple[float, float]:
        size = max(abs(end_x - start_x), abs(end_y - start_y))
        return (
            start_x + size * (1 if end_x >= start_x else -1),
            start_y + size * (1 if end_y >= start_y else -1),
        )

    def _add_line_annotation(
        self, page: fitz.Page, start: fitz.Point, end: fitz.Point
    ) -> fitz.Annot:
        width = max(0.5, self.line_width_var.get())
        style = self.line_style_var.get()
        annotation = page.add_line_annot(start, end)
        annotation.set_colors(stroke=self.edge_color)
        if style == "Dotted":
            annotation.set_border(width=width, dashes=[1, 3])
        else:
            annotation.set_border(width=width)
        if style == "Arrow":
            annotation.set_line_ends(
                fitz.PDF_ANNOT_LE_NONE,
                fitz.PDF_ANNOT_LE_CLOSED_ARROW,
            )
        annotation.set_info(
            title="PDFeditEasy",
            subject="PDFeditEasy Object",
            content=f"line:{style.lower()}",
        )
        annotation.update()
        return annotation

    def add_blank_page(self) -> None:
        page_settings = self._ask_page_size()
        if page_settings is None:
            return
        width, height = page_settings
        if self.document is None:
            self.document = fitz.open()
            self.filename = None
            self.current_page = 0
            self.undo_stack.clear()
            self.selected_annot_xref = None
            self.document.new_page(width=width, height=height)
            status = "New document created with a blank page"
        else:
            self.snapshot()
            self.document.new_page(
                pno=self.current_page + 1,
                width=width,
                height=height,
            )
            self.current_page += 1
            self.selected_annot_xref = None
            status = "Blank page added"
        self._refresh_pages()
        self.status_var.set(status)

    def _ask_page_size(self) -> tuple[float, float] | None:
        dialog = tk.Toplevel(self)
        dialog.title("Blank page")
        dialog.configure(bg=COLORS["surface"])
        dialog.resizable(False, False)
        dialog.transient(self)
        dialog.grab_set()

        result: list[tuple[float, float]] = []
        size_var = tk.StringVar(value="A4")
        orientation_var = tk.StringVar(value="Portrait")

        header = tk.Frame(dialog, bg=COLORS["purple_dark"], padx=22, pady=16)
        header.pack(fill="x")
        tk.Label(
            header,
            text="Create a blank page",
            bg=COLORS["purple_dark"],
            fg=COLORS["white"],
            font=("Segoe UI Semibold", 15),
        ).pack(anchor="w")
        tk.Label(
            header,
            text="Choose the paper size and orientation.",
            bg=COLORS["purple_dark"],
            fg="#CFC0E7",
            font=("Segoe UI", 9),
        ).pack(anchor="w", pady=(2, 0))

        content = tk.Frame(dialog, bg=COLORS["surface"], padx=22, pady=20)
        content.pack(fill="both", expand=True)
        tk.Label(
            content, text="Page size", bg=COLORS["surface"],
            fg=COLORS["purple_dark"], font=("Segoe UI Semibold", 9),
        ).grid(row=0, column=0, sticky="w", pady=(0, 6))
        size_picker = ttk.Combobox(
            content,
            textvariable=size_var,
            values=tuple(PAGE_SIZES),
            state="readonly",
            width=20,
            style="Modern.TCombobox",
        )
        size_picker.grid(row=1, column=0, sticky="ew", padx=(0, 12))

        tk.Label(
            content, text="Orientation", bg=COLORS["surface"],
            fg=COLORS["purple_dark"], font=("Segoe UI Semibold", 9),
        ).grid(row=0, column=1, sticky="w", pady=(0, 6))
        orientation_picker = ttk.Combobox(
            content,
            textvariable=orientation_var,
            values=("Portrait", "Landscape"),
            state="readonly",
            width=20,
            style="Modern.TCombobox",
        )
        orientation_picker.grid(row=1, column=1, sticky="ew")

        buttons = tk.Frame(content, bg=COLORS["surface"])
        buttons.grid(row=2, column=0, columnspan=2, sticky="e", pady=(22, 0))

        def create_page() -> None:
            width, height = PAGE_SIZES[size_var.get()]
            if orientation_var.get() == "Landscape":
                width, height = height, width
            result.append((width, height))
            dialog.destroy()

        RoundedButton(
            buttons, "Cancel", dialog.destroy, bg=COLORS["purple_soft"],
            fg=COLORS["purple_dark"], hover="#DED0F4", width=88, height=36,
        ).pack(side="left", padx=(0, 8))
        RoundedButton(
            buttons, "Create page", create_page, bg=COLORS["pink"],
            fg=COLORS["white"], hover=COLORS["pink_dark"], width=112, height=36,
        ).pack(side="left")

        dialog.protocol("WM_DELETE_WINDOW", dialog.destroy)
        dialog.bind("<Escape>", lambda _event: dialog.destroy())
        dialog.bind("<Return>", lambda _event: create_page())
        dialog.update_idletasks()
        x = self.winfo_rootx() + (self.winfo_width() - dialog.winfo_width()) // 2
        y = self.winfo_rooty() + (self.winfo_height() - dialog.winfo_height()) // 2
        dialog.geometry(f"+{max(0, x)}+{max(0, y)}")
        size_picker.focus_set()
        self.wait_window(dialog)
        return result[0] if result else None

    def insert_pdf(self) -> None:
        if not self.require_document():
            return
        filename = filedialog.askopenfilename(
            title="Insert pages from PDF", filetypes=[("PDF files", "*.pdf")]
        )
        if not filename:
            return
        try:
            source = fitz.open(filename)
            self.snapshot()
            self.document.insert_pdf(source, start_at=self.current_page + 1)
            added = source.page_count
            source.close()
            self.current_page += 1
            self.selected_annot_xref = None
            self._refresh_pages()
            self.status_var.set(f"Inserted {added} page(s)")
        except Exception as error:
            messagebox.showerror(APP_TITLE, str(error))

    def delete_page(self) -> None:
        if not self.require_document():
            return
        if self.document.page_count == 1:
            messagebox.showinfo(APP_TITLE, "A PDF must contain at least one page.")
            return
        if not messagebox.askyesno(
            APP_TITLE, f"Delete page {self.current_page + 1}?", parent=self
        ):
            return
        self.snapshot()
        self.document.delete_page(self.current_page)
        self.current_page = min(self.current_page, self.document.page_count - 1)
        self.selected_annot_xref = None
        self._refresh_pages()
        self.status_var.set("Page deleted")

    def move_page(self, direction: int) -> None:
        if not self.require_document():
            return
        target = self.current_page + direction
        if target < 0 or target >= self.document.page_count:
            return
        self.snapshot()
        self.document.move_page(self.current_page, target)
        self.current_page = target
        self.selected_annot_xref = None
        self._refresh_pages()
        self.status_var.set("Page moved")

    def run_ocr(self) -> None:
        if not self.require_document() or self.busy:
            return
        value = simpledialog.askstring(
            "OCR opened PDF",
            (
                "This adds an invisible searchable text layer to the opened PDF.\n"
                "After OCR finishes, save the searchable PDF.\n\n"
                f"Pages (examples: 1,3-5 or all).\nCurrent page is {self.current_page + 1}:"
            ),
            initialvalue=str(self.current_page + 1),
            parent=self,
        )
        if value is None:
            return
        try:
            pages = parse_page_ranges(value, self.document.page_count)
            if not pages:
                pages = [self.current_page]
            configure_tesseract()
        except Exception as error:
            messagebox.showerror(APP_TITLE, str(error))
            return

        self.snapshot()
        self.busy = True
        self.progress.start(12)
        self.status_var.set(f"Running OCR on {len(pages)} page(s)...")

        def worker() -> None:
            try:
                total_words = 0
                for number, page_index in enumerate(pages, 1):
                    self.events.put(
                        ("status", f"OCR page {page_index + 1} ({number}/{len(pages)})...")
                    )
                    total_words += add_ocr_layer(self.document[page_index])
                self.events.put(("ocr_done", (len(pages), total_words)))
            except Exception:
                self.events.put(("error", traceback.format_exc()))

        threading.Thread(target=worker, daemon=True).start()

    def _poll_events(self) -> None:
        try:
            while True:
                kind, value = self.events.get_nowait()
                if kind == "status":
                    self.status_var.set(value)
                elif kind == "ocr_done":
                    self.busy = False
                    self.progress.stop()
                    pages, words = value
                    self.render_current()
                    if words:
                        self.status_var.set(
                            f"OCR added: {words} words on {pages} page(s). Save the searchable PDF."
                        )
                        if messagebox.askyesno(
                            APP_TITLE,
                            (
                                f"OCR added {words} searchable words on {pages} page(s).\n\n"
                                "The text layer is invisible, so the page may look the same.\n"
                                "Save a searchable PDF now?"
                            ),
                            parent=self,
                        ):
                            self.save_as()
                    else:
                        self.status_var.set(
                            f"OCR finished but found no readable words on {pages} page(s)"
                        )
                        messagebox.showinfo(
                            APP_TITLE,
                            (
                                "OCR finished, but Tesseract did not find readable words.\n\n"
                                "This can happen if the page is already text-based, the scan is blurry, "
                                "or the page language/contrast is poor."
                            ),
                            parent=self,
                        )
                elif kind == "ocr_status":
                    self.ocr_status_var.set(value)
                elif kind == "ocr_pages":
                    self.ocr_pages.extend(value)
                    self.ocr_refresh_page_list(select_last=True)
                elif kind == "ocr_text":
                    index, text = value
                    if 0 <= index < len(self.ocr_pages):
                        self.ocr_pages[index].text = text
                        if self.ocr_current_index == index:
                            self.ocr_load_text(text)
                elif kind == "ocr_done_generator":
                    self.ocr_set_busy(False, value)
                elif kind == "ocr_pdf_done":
                    self.ocr_set_busy(False, f"Searchable PDF saved: {value}")
                    if messagebox.askyesno(
                        APP_TITLE,
                        f"The searchable PDF was saved:\n{value}\n\nOpen it in the OpenPDF tab?",
                    ):
                        self.open_pdf_path(value)
                elif kind == "ocr_error":
                    self.ocr_set_busy(False, "OCR generator failed")
                    messagebox.showerror(APP_TITLE, value)
                elif kind == "error":
                    self.busy = False
                    self.progress.stop()
                    messagebox.showerror(APP_TITLE, value)
                    self.status_var.set("OCR failed")
        except queue.Empty:
            pass
        self.after(100, self._poll_events)


if __name__ == "__main__":
    PdfEditor().mainloop()
