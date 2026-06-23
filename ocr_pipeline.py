from __future__ import annotations

import io
import os
import re
import shutil
import sys
from pathlib import Path

import cv2
import numpy as np
import pytesseract
from PIL import Image, ImageOps
from pypdf import PdfReader, PdfWriter


IMAGE_TYPES = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp", ".webp"}


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
        "Tesseract OCR blev ikke fundet. Kør Setup.bat, og start programmet igen."
    )


def available_ocr_language() -> str:
    configure_tesseract()
    languages = set(pytesseract.get_languages(config=""))
    return "dan+eng" if {"dan", "eng"} <= languages else "dan" if "dan" in languages else "eng"


def read_image(path: str | Path) -> np.ndarray:
    data = np.fromfile(str(path), dtype=np.uint8)
    image = cv2.imdecode(data, cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError(f"Kunne ikke læse billedet: {path}")
    return image


def bgr_to_pil(image: np.ndarray) -> Image.Image:
    rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    return Image.fromarray(rgb)


def order_points(points: np.ndarray) -> np.ndarray:
    points = points.astype("float32")
    sums = points.sum(axis=1)
    differences = np.diff(points, axis=1).reshape(-1)
    return np.array(
        [
            points[np.argmin(sums)],
            points[np.argmin(differences)],
            points[np.argmax(sums)],
            points[np.argmax(differences)],
        ],
        dtype="float32",
    )


def warp_quad(image: np.ndarray, points: np.ndarray) -> np.ndarray:
    top_left, top_right, bottom_right, bottom_left = order_points(points)
    width = int(
        max(
            np.linalg.norm(bottom_right - bottom_left),
            np.linalg.norm(top_right - top_left),
        )
    )
    height = int(
        max(
            np.linalg.norm(top_right - bottom_right),
            np.linalg.norm(top_left - bottom_left),
        )
    )
    if width < 100 or height < 100:
        return image
    target = np.array(
        [[0, 0], [width - 1, 0], [width - 1, height - 1], [0, height - 1]],
        dtype="float32",
    )
    matrix = cv2.getPerspectiveTransform(
        np.array([top_left, top_right, bottom_right, bottom_left]), target
    )
    return cv2.warpPerspective(image, matrix, (width, height))


def perspective_crop(image: np.ndarray, minimum_area: float = 0.22) -> np.ndarray:
    height, width = image.shape[:2]
    scale = 1000 / max(height, width) if max(height, width) > 1000 else 1.0
    small = cv2.resize(image, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
    gray = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(gray, 45, 135)
    edges = cv2.morphologyEx(
        edges, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_RECT, (9, 9))
    )
    contours, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    image_area = small.shape[0] * small.shape[1]
    for contour in sorted(contours, key=cv2.contourArea, reverse=True)[:20]:
        perimeter = cv2.arcLength(contour, True)
        polygon = cv2.approxPolyDP(contour, 0.025 * perimeter, True)
        if len(polygon) == 4 and cv2.contourArea(polygon) > minimum_area * image_area:
            points = polygon.reshape(4, 2) / scale
            return warp_quad(image, points)
    return image


def trim_border(image: np.ndarray, fraction: float = 0.015) -> np.ndarray:
    height, width = image.shape[:2]
    x = max(1, int(width * fraction))
    y = max(1, int(height * fraction))
    return image[y : height - y, x : width - x]


def isolate_dominant_page(image: np.ndarray) -> np.ndarray:
    """Remove a narrow opposite page and desk around a mostly white book page."""
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    white = ((hsv[:, :, 1] < 75) & (hsv[:, :, 2] > 110)).astype(np.uint8) * 255
    if np.count_nonzero(white) / white.size < 0.32:
        return image

    height, width = image.shape[:2]
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    column_mean = gray[int(0.20 * height) : int(0.83 * height)].mean(axis=0)
    narrow = cv2.GaussianBlur(column_mean.reshape(1, -1), (11, 1), 0).ravel()
    broad = cv2.GaussianBlur(column_mean.reshape(1, -1), (101, 1), 0).ravel()
    gutter_score = broad - narrow

    left_band = slice(int(0.08 * width), int(0.35 * width))
    right_band = slice(int(0.65 * width), int(0.92 * width))
    left_x = int(np.argmax(gutter_score[left_band]) + left_band.start)
    right_x = int(np.argmax(gutter_score[right_band]) + right_band.start)
    left_score = float(gutter_score[left_x])
    right_score = float(gutter_score[right_x])

    if max(left_score, right_score) >= 7.0:
        if left_score > right_score:
            image = image[:, max(0, left_x - 4) :]
            white = white[:, max(0, left_x - 4) :]
        else:
            image = image[:, : min(width, right_x + 4)]
            white = white[:, : min(width, right_x + 4)]

    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (51, 51))
    joined = cv2.morphologyEx(white, cv2.MORPH_CLOSE, kernel)
    contours, _ = cv2.findContours(joined, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return image
    contour = max(contours, key=cv2.contourArea)
    x, y, box_width, box_height = cv2.boundingRect(contour)
    if box_width * box_height < 0.35 * image.shape[0] * image.shape[1]:
        return image

    hull = cv2.convexHull(contour)
    perimeter = cv2.arcLength(hull, True)
    for epsilon in (0.015, 0.02, 0.025, 0.03, 0.04):
        polygon = cv2.approxPolyDP(hull, epsilon * perimeter, True)
        if len(polygon) == 4:
            corrected = warp_quad(image, polygon.reshape(4, 2))
            if corrected.shape[0] > corrected.shape[1]:
                return trim_border(corrected, fraction=0.008)

    # Conservative fallback: stay just inside the detected paper bounds.
    inset_x = max(2, int(box_width * 0.006))
    inset_y = max(2, int(box_height * 0.006))
    x1 = min(image.shape[1] - 1, x + inset_x)
    y1 = min(image.shape[0] - 1, y + inset_y)
    x2 = max(x1 + 1, min(image.shape[1], x + box_width - inset_x))
    y2 = max(y1 + 1, min(image.shape[0], y + box_height - inset_y))
    return image[y1:y2, x1:x2]


def improve_for_reading(image: np.ndarray) -> np.ndarray:
    lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB)
    lightness, a_channel, b_channel = cv2.split(lab)
    lightness = cv2.createCLAHE(clipLimit=1.25, tileGridSize=(8, 8)).apply(lightness)
    corrected = cv2.cvtColor(
        cv2.merge((lightness, a_channel, b_channel)), cv2.COLOR_LAB2BGR
    )
    return corrected


def orient_page(image: np.ndarray) -> np.ndarray:
    try:
        preview = image
        if max(image.shape[:2]) > 1400:
            scale = 1400 / max(image.shape[:2])
            preview = cv2.resize(image, None, fx=scale, fy=scale)
        output = pytesseract.image_to_osd(
            cv2.cvtColor(preview, cv2.COLOR_BGR2RGB), config="--psm 0"
        )
        match = re.search(r"Rotate:\s+(\d+)", output)
        rotation = int(match.group(1)) if match else 0
        if rotation == 90:
            return cv2.rotate(image, cv2.ROTATE_90_CLOCKWISE)
        if rotation == 180:
            return cv2.rotate(image, cv2.ROTATE_180)
        if rotation == 270:
            return cv2.rotate(image, cv2.ROTATE_90_COUNTERCLOCKWISE)
    except pytesseract.TesseractError:
        pass
    return image


def process_photo(
    path: str | Path,
    two_page_spread: bool = True,
    already_cropped: bool = False,
) -> list[Image.Image]:
    configure_tesseract()
    image = read_image(path)
    if already_cropped:
        return [bgr_to_pil(image)]

    if two_page_spread:
        if image.shape[0] > image.shape[1]:
            image = cv2.rotate(image, cv2.ROTATE_90_COUNTERCLOCKWISE)
        spread = perspective_crop(image, minimum_area=0.28)
        width = spread.shape[1]
        center = width // 2
        overlap = max(2, int(width * 0.006))
        page_images = [spread[:, : center + overlap], spread[:, center - overlap :]]
    else:
        isolated = isolate_dominant_page(image)
        corrected = perspective_crop(isolated, minimum_area=0.68)
        corrected_area = corrected.shape[0] * corrected.shape[1]
        isolated_area = isolated.shape[0] * isolated.shape[1]
        implausible_shape = corrected.shape[1] / corrected.shape[0] > 0.92
        lost_too_much = corrected_area < 0.58 * isolated_area
        page_images = [isolated if implausible_shape or lost_too_much else corrected]

    results: list[Image.Image] = []
    for page in page_images:
        if two_page_spread:
            page = perspective_crop(page, minimum_area=0.35)
            page = isolate_dominant_page(page)
        page = trim_border(page)
        if two_page_spread:
            page = orient_page(page)
        page = improve_for_reading(page)
        results.append(bgr_to_pil(page))
    return results


def ocr_text(image: Image.Image) -> str:
    language = available_ocr_language()
    prepared = ImageOps.exif_transpose(image).convert("RGB")
    return pytesseract.image_to_string(prepared, lang=language, config="--oem 3 --psm 3").strip()


def export_searchable_pdf(images: list[Image.Image], destination: str | Path) -> None:
    if not images:
        raise ValueError("Der er ingen sider at eksportere.")
    language = available_ocr_language()
    writer = PdfWriter()
    for image in images:
        rgb = ImageOps.exif_transpose(image).convert("RGB")
        pdf_bytes = pytesseract.image_to_pdf_or_hocr(
            rgb, extension="pdf", lang=language, config="--oem 3 --psm 3"
        )
        reader = PdfReader(io.BytesIO(pdf_bytes))
        writer.add_page(reader.pages[0])
    with Path(destination).open("wb") as output:
        writer.write(output)
