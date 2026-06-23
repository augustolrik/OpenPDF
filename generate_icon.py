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
    draw.rounded_rectangle(
        (
            round(size * 0.56),
            round(size * 0.56),
            round(size * 0.90),
            round(size * 0.90),
        ),
        radius=max(1, round(size * 0.10)),
        fill=PINK,
    )
    label_font = font(max(7, round(size * 0.28)))
    draw.text(
        (size * 0.23, size * 0.20),
        "PDF",
        fill=PURPLE,
        font=label_font,
        anchor="la",
    )
    images.append(image)

images[-1].save(
    "PDFeditEasy.ico",
    format="ICO",
    sizes=[(size, size) for size in SIZES],
)
print("Created PDFeditEasy.ico")
