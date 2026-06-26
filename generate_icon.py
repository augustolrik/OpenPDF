from pathlib import Path
import shutil

from PIL import Image, ImageDraw, ImageFont


SIZES = (16, 24, 32, 48, 64, 128, 256)
PURPLE = "#321B52"
PINK = "#ED5DA8"
YELLOW = "#FFD84D"
BRAND_ICON = Path(__file__).with_name("Cat logo.ico")
OUTPUT_ICON = Path(__file__).with_name("OpenPDF.ico")


if BRAND_ICON.exists():
    shutil.copyfile(BRAND_ICON, OUTPUT_ICON)
    print(f"Created {OUTPUT_ICON.name} from {BRAND_ICON.name}")
    raise SystemExit(0)


def font(size: int):
    for path in (
        "C:/Windows/Fonts/seguisb.ttf",
        "C:/Windows/Fonts/segoeuib.ttf",
        "C:/Windows/Fonts/arialbd.ttf",
    ):
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()


images = []
for size in SIZES:
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    margin = max(1, round(size * 0.11))
    radius = max(2, round(size * 0.12))
    draw.rounded_rectangle(
        (margin, round(size * 0.24), size - margin, size - margin),
        radius=radius,
        fill=YELLOW,
    )
    draw.polygon(
        [
            (round(size * 0.17), round(size * 0.28)),
            (round(size * 0.25), round(size * 0.10)),
            (round(size * 0.35), round(size * 0.28)),
        ],
        fill=YELLOW,
    )
    draw.polygon(
        [
            (round(size * 0.65), round(size * 0.28)),
            (round(size * 0.75), round(size * 0.10)),
            (round(size * 0.83), round(size * 0.28)),
        ],
        fill=YELLOW,
    )
    eye = max(1, round(size * 0.045))
    draw.ellipse(
        (
            round(size * 0.36) - eye,
            round(size * 0.48) - eye,
            round(size * 0.36) + eye,
            round(size * 0.48) + eye,
        ),
        fill=PURPLE,
    )
    draw.ellipse(
        (
            round(size * 0.64) - eye,
            round(size * 0.48) - eye,
            round(size * 0.64) + eye,
            round(size * 0.48) + eye,
        ),
        fill=PURPLE,
    )
    draw.polygon(
        [
            (round(size * 0.47), round(size * 0.61)),
            (round(size * 0.50), round(size * 0.66)),
            (round(size * 0.53), round(size * 0.61)),
        ],
        fill=PINK,
    )
    draw.line(
        [
            (round(size * 0.48), round(size * 0.69)),
            (round(size * 0.33), round(size * 0.76)),
        ],
        fill=PURPLE,
        width=max(1, round(size * 0.018)),
    )
    draw.line(
        [
            (round(size * 0.52), round(size * 0.69)),
            (round(size * 0.67), round(size * 0.76)),
        ],
        fill=PURPLE,
        width=max(1, round(size * 0.018)),
    )
    images.append(image)

images[-1].save(
    OUTPUT_ICON,
    format="ICO",
    sizes=[(size, size) for size in SIZES],
)
print(f"Created {OUTPUT_ICON.name}")
