from __future__ import annotations

import io
import os
import re
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

import fitz
import pytesseract
from PIL import Image


@dataclass
class TextBlock:
    rect: fitz.Rect
    text: str
    font_size: float


def configure_tesseract() -> Path:
    executable_folder = Path(sys.executable).resolve().parent
    portable_folder = executable_folder / "tesseract"
    candidates = [
        portable_folder / "tesseract.exe",
        shutil.which("tesseract"),
        Path.home() / "AppData/Local/Programs/Tesseract-OCR/tesseract.exe",
        Path("C:/Program Files/Tesseract-OCR/tesseract.exe"),
        Path("C:/Program Files (x86)/Tesseract-OCR/tesseract.exe"),
    ]
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            pytesseract.pytesseract.tesseract_cmd = str(candidate)
            tessdata = Path(candidate).parent / "tessdata"
            if tessdata.is_dir():
                os.environ["TESSDATA_PREFIX"] = str(tessdata)
            return Path(candidate)
    raise RuntimeError(
        "Tesseract OCR was not found. Run Setup.bat or install Tesseract OCR."
    )


def available_ocr_language() -> str:
    configure_tesseract()
    languages = set(pytesseract.get_languages(config=""))
    if {"dan", "eng"} <= languages:
        return "dan+eng"
    if "dan" in languages:
        return "dan"
    return "eng"


def parse_page_ranges(value: str, page_count: int) -> list[int]:
    value = value.strip().lower()
    if value in {"", "current"}:
        return []
    if value in {"all", "*"}:
        return list(range(page_count))

    pages: set[int] = set()
    for part in value.split(","):
        part = part.strip()
        match = re.fullmatch(r"(\d+)(?:\s*-\s*(\d+))?", part)
        if not match:
            raise ValueError(f"Invalid page range: {part}")
        first = int(match.group(1))
        last = int(match.group(2) or first)
        if first > last:
            first, last = last, first
        if first < 1 or last > page_count:
            raise ValueError(f"Page range must be between 1 and {page_count}.")
        pages.update(range(first - 1, last))
    return sorted(pages)


def render_page(page: fitz.Page, zoom: float = 1.4) -> Image.Image:
    pixmap = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
    return Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)


def find_text_block(page: fitz.Page, point: fitz.Point) -> TextBlock | None:
    data = page.get_text("dict")
    for block in data.get("blocks", []):
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            rect = fitz.Rect(line["bbox"])
            if not rect.contains(point):
                continue
            spans = line.get("spans", [])
            text = "".join(span.get("text", "") for span in spans).strip()
            font_size = max((span.get("size", 11.0) for span in spans), default=11.0)
            if text:
                return TextBlock(rect=rect, text=text, font_size=font_size)
    return None


def replace_text(
    page: fitz.Page,
    block: TextBlock,
    new_text: str,
    color: tuple[float, float, float] = (0, 0, 0),
) -> None:
    margin = 1.5
    redaction = fitz.Rect(
        block.rect.x0 - margin,
        block.rect.y0 - margin,
        block.rect.x1 + margin,
        block.rect.y1 + margin,
    )
    page.add_redact_annot(redaction, fill=(1, 1, 1))
    page.apply_redactions()
    result = page.insert_textbox(
        block.rect,
        new_text,
        fontsize=max(4, block.font_size),
        fontname="helv",
        color=color,
        align=fitz.TEXT_ALIGN_LEFT,
        overlay=True,
    )
    if result < 0:
        expanded = fitz.Rect(
            block.rect.x0,
            block.rect.y0,
            page.rect.x1 - 8,
            block.rect.y1 + block.font_size * 1.5,
        )
        page.insert_textbox(
            expanded,
            new_text,
            fontsize=max(4, block.font_size * 0.92),
            fontname="helv",
            color=color,
            overlay=True,
        )


def insert_text_box(
    page: fitz.Page,
    rect: fitz.Rect,
    text: str,
    font_size: float,
    border: bool = True,
) -> None:
    if border:
        page.draw_rect(rect, color=(0, 0, 0), width=1, overlay=True)
    inner = fitz.Rect(rect.x0 + 4, rect.y0 + 4, rect.x1 - 4, rect.y1 - 4)
    page.insert_textbox(
        inner,
        text,
        fontsize=font_size,
        fontname="helv",
        color=(0, 0, 0),
        overlay=True,
    )


def add_image_annotation(
    document: fitz.Document,
    page_index: int,
    rect: fitz.Rect,
    filename: str | Path,
) -> int:
    """Create a movable image stamp with a custom PDF appearance stream."""
    page = document[page_index]
    annotation = page.add_stamp_annot(rect)
    annotation_xref = annotation.xref

    appearance_page = document.new_page(width=rect.width, height=rect.height)
    appearance_page.insert_image(
        appearance_page.rect,
        filename=str(filename),
        keep_proportion=True,
        overlay=True,
    )

    ap_value = document.xref_get_key(annotation_xref, "AP")[1]
    ap_match = re.search(r"/N\s+(\d+)\s+0\s+R", ap_value)
    contents_value = document.xref_get_key(appearance_page.xref, "Contents")[1]
    contents_match = re.search(r"(\d+)\s+0\s+R", contents_value)
    if not ap_match or not contents_match:
        document.delete_page(document.page_count - 1)
        raise RuntimeError("Could not create the editable image object.")

    appearance_xref = int(ap_match.group(1))
    contents_xref = int(contents_match.group(1))
    resources = document.xref_get_key(appearance_page.xref, "Resources")[1]
    stream = document.xref_stream(contents_xref)
    document.xref_set_key(appearance_xref, "Resources", resources)
    document.xref_set_key(
        appearance_xref, "BBox", f"[0 0 {rect.width:g} {rect.height:g}]"
    )
    document.update_stream(appearance_xref, stream)
    document.delete_page(document.page_count - 1)

    page = document[page_index]
    annotation = page.load_annot(annotation_xref)
    annotation.set_info(
        title="PDFeditEasy",
        subject="PDFeditEasy Object",
        content="image",
    )
    annotation.update()
    return annotation_xref


def add_ocr_layer(page: fitz.Page, dpi: int = 300) -> int:
    language = available_ocr_language()
    scale = dpi / 72
    pixmap = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
    image = Image.open(io.BytesIO(pixmap.tobytes("png"))).convert("RGB")
    data = pytesseract.image_to_data(
        image,
        lang=language,
        config="--oem 3 --psm 3",
        output_type=pytesseract.Output.DICT,
    )

    count = 0
    for index, raw_text in enumerate(data["text"]):
        text = raw_text.strip()
        confidence = float(data["conf"][index])
        if not text or confidence < 20:
            continue
        x = data["left"][index] / scale
        y = data["top"][index] / scale
        height = max(3.0, data["height"][index] / scale)
        page.insert_text(
            fitz.Point(x, y + height * 0.82),
            text,
            fontsize=height * 0.82,
            fontname="helv",
            color=(0, 0, 0),
            render_mode=3,
            overlay=True,
        )
        count += 1
    return count
