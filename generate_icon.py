from PIL import Image, ImageDraw, ImageFont


SIZES = (16, 24, 32, 48, 64, 128, 256)
PURPLE = "#321B52"
PINK = "#ED5DA8"
YELLOW = "#FFD84D"


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
    image = Image.new("RGBA", (size, size), PURPLE)
    draw = ImageDraw.Draw(image)
    margin = max(1, round(size * 0.10))
    radius = max(2, round(size * 0.23))
    draw.rounded_rectangle(
        (margin, margin, size - margin, size - margin),
        radius=radius,
        fill=YELLOW,
    )
    head = (
        round(size * 0.20),
        round(size * 0.30),
        round(size * 0.80),
        round(size * 0.82),
    )
    draw.rounded_rectangle(head, radius=max(2, round(size * 0.18)), fill=PURPLE)
    draw.polygon(
        [
            (round(size * 0.24), round(size * 0.36)),
            (round(size * 0.33), round(size * 0.13)),
            (round(size * 0.43), round(size * 0.38)),
        ],
        fill=PURPLE,
    )
    draw.polygon(
        [
            (round(size * 0.57), round(size * 0.38)),
            (round(size * 0.67), round(size * 0.13)),
            (round(size * 0.76), round(size * 0.36)),
        ],
        fill=PURPLE,
    )
    eye = max(1, round(size * 0.035))
    draw.ellipse(
        (
            round(size * 0.36) - eye,
            round(size * 0.52) - eye,
            round(size * 0.36) + eye,
            round(size * 0.52) + eye,
        ),
        fill=YELLOW,
    )
    draw.ellipse(
        (
            round(size * 0.64) - eye,
            round(size * 0.52) - eye,
            round(size * 0.64) + eye,
            round(size * 0.52) + eye,
        ),
        fill=YELLOW,
    )
    draw.polygon(
        [
            (round(size * 0.47), round(size * 0.62)),
            (round(size * 0.50), round(size * 0.67)),
            (round(size * 0.53), round(size * 0.62)),
        ],
        fill=PINK,
    )
    draw.line(
        [
            (round(size * 0.49), round(size * 0.70)),
            (round(size * 0.38), round(size * 0.75)),
        ],
        fill=YELLOW,
        width=max(1, round(size * 0.015)),
    )
    draw.line(
        [
            (round(size * 0.51), round(size * 0.70)),
            (round(size * 0.62), round(size * 0.75)),
        ],
        fill=YELLOW,
        width=max(1, round(size * 0.015)),
    )
    images.append(image)

images[-1].save(
    "OpenPDF.ico",
    format="ICO",
    sizes=[(size, size) for size in SIZES],
)
print("Created OpenPDF.ico")
