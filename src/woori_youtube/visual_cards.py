"""Original, editable news graphics; labels must be checked against research."""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps


def _font(size: int, bold: bool = False):
    try:
        return ImageFont.truetype("arialbd.ttf" if bold else "arial.ttf", size)
    except OSError:
        return ImageFont.load_default(size=size)


def create_vertical_card(output: Path, *, headline: str, subtitle: str, label: str,
                         source: str, style: str, background: Path | None = None,
                         highlighted_days: tuple[int, ...] = (23, 24, 25, 26)) -> Path:
    width, height = 1080, 1920
    if background:
        with Image.open(background) as original:
            image = ImageOps.fit(original.convert("RGB"), (width, height)).convert("RGBA")
        image = Image.alpha_composite(image, Image.new("RGBA", (width, height), (3, 13, 30, 90)))
    else:
        image = Image.new("RGBA", (width, height), "#081a31")
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, width, 22), fill="#ffe500")
    draw.rounded_rectangle((60, 100, 380, 168), radius=18, fill="#ffe500")
    draw.text((85, 113), "NOW TRENDS", font=_font(33, True), fill="#062034")
    draw.text((65, 220), label.upper(), font=_font(37, True), fill="#ffe500", stroke_width=1, stroke_fill="#07182b")
    draw.multiline_text((65, 280), headline, font=_font(88, True), fill="white", spacing=8,
                        stroke_width=1, stroke_fill="#081a31")
    draw.multiline_text((65, 500), subtitle, font=_font(40), fill="#e1f6f8", spacing=10,
                        stroke_width=1, stroke_fill="#081a31")
    if style == "calendar":
        draw.rounded_rectangle((65, 800, 1015, 1210), radius=35, fill="#102d49", outline="#42c9d0", width=3)
        draw.text((100, 840), "NOVEMBER 2026", font=_font(45, True), fill="#b3f5f0")
        for i, day in enumerate((23, 24, 25, 26)):
            x = 104 + i * 215
            draw.rounded_rectangle((x, 945, x + 180, 1125), radius=22,
                                   fill="#17667a" if day in highlighted_days else "#283d4c")
            draw.text((x + 43, 970), str(day), font=_font(74, True), fill="white")
    elif style == "orbit":
        draw.ellipse((360, 800, 720, 1160), fill="#116b9a", outline="#72ddf2", width=6)
        draw.ellipse((400, 850, 550, 970), fill="#42bfab")
        draw.ellipse((815, 710, 955, 850), fill="#dedee1")
        draw.ellipse((85, 710, 245, 870), fill="#f0bd4f")
        draw.line((270, 790, 330, 860), fill="#d9f7f8", width=6)
        draw.line((750, 860, 800, 800), fill="#d9f7f8", width=6)
        draw.text((100, 885), "SUN", font=_font(30, True), fill="white")
        draw.text((790, 885), "MOON", font=_font(30, True), fill="white")
        draw.text((460, 1180), "EARTH", font=_font(30, True), fill="white")
    elif style == "risk":
        draw.rounded_rectangle((65, 900, 1015, 1180), radius=35, fill="#163850", outline="#f5c65a", width=4)
        draw.text((100, 940), "LOW-LYING AREAS", font=_font(55, True), fill="#ffe294")
        draw.text((100, 1040), "Flooding possible", font=_font(42), fill="white")
    else:
        raise ValueError("Unsupported visual card style")
    draw.rounded_rectangle((55, 1600, 1025, 1740), radius=24, fill=(5, 20, 37, 225))
    draw.text((85, 1620), "ILLUSTRATION  •  SOURCE", font=_font(27, True), fill="#7edbd7")
    draw.text((85, 1665), source, font=_font(32), fill="white")
    output.parent.mkdir(parents=True, exist_ok=True)
    image.convert("RGB").save(output)
    return output


def create_news_thumbnail(output: Path, *, background: Path, headline: str, badge: str) -> Path:
    with Image.open(background) as original:
        image = ImageOps.fit(original.convert("RGB"), (1280, 720)).convert("RGBA")
    shade = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(shade)
    draw.rectangle((0, 0, 820, 720), fill=(4, 15, 31, 175))
    image = Image.alpha_composite(image, shade)
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((55, 55, 440, 130), radius=14, fill="#ffe500")
    draw.text((80, 68), badge, font=_font(38, True), fill="#07182b")
    words = headline.replace("\n", " ").split()
    if not words:
        raise ValueError("Thumbnail headline is empty")
    for size in range(100, 39, -5):
        font = _font(size, True)
        lines = []
        for word in words:
            candidate = (lines[-1] + " " + word) if lines else word
            if lines and draw.textlength(candidate, font=font) > 1000:
                lines.append(word)
            elif lines:
                lines[-1] = candidate
            else:
                lines.append(word)
        text = "\n".join(lines)
        box = draw.multiline_textbbox((55, 180), text, font=font, spacing=5, stroke_width=4)
        if box[2] <= 1200 and box[3] <= 610:
            break
    else:
        raise ValueError("Thumbnail headline is too long")
    draw.multiline_text((55, 180), text, font=font, fill="white", spacing=5,
                        stroke_width=4, stroke_fill="#07182b")
    draw.text((60, 655), "ILLUSTRATION", font=_font(24, True), fill="white", stroke_width=2, stroke_fill="#07182b")
    output.parent.mkdir(parents=True, exist_ok=True)
    image.convert("RGB").save(output, "JPEG", quality=90)
    return output
