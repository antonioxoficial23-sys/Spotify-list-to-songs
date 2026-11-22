"""Genera assets/listacd.png y assets/listacd.ico (un CD con una nota musical)."""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

S = 1024
out = Path(__file__).resolve().parent.parent / "assets"
out.mkdir(exist_ok=True)

img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
# Disco con degradado violeta → rosa
grad = Image.new("RGBA", (S, S))
gd = ImageDraw.Draw(grad)
for y in range(S):
    t = y / S
    gd.line([(0, y), (S, y)], fill=(int(139 + 97 * t), int(92 - 20 * t), int(246 - 120 * t), 255))
mask = Image.new("L", (S, S), 0)
md = ImageDraw.Draw(mask)
md.ellipse([40, 40, S - 40, S - 40], fill=255)
md.ellipse([S / 2 - 70, S / 2 - 70, S / 2 + 70, S / 2 + 70], fill=0)
img.paste(grad, (0, 0), mask)
d = ImageDraw.Draw(img)
# Surcos del CD
for r in range(170, 470, 46):
    d.ellipse([S / 2 - r, S / 2 - r, S / 2 + r, S / 2 + r], outline=(255, 255, 255, 38), width=6)
# Brillo
shine = Image.new("RGBA", (S, S), (0, 0, 0, 0))
sd = ImageDraw.Draw(shine)
sd.pieslice([40, 40, S - 40, S - 40], 200, 250, fill=(255, 255, 255, 70))
shine = shine.filter(ImageFilter.GaussianBlur(18))
img = Image.alpha_composite(img, Image.composite(shine, Image.new("RGBA", (S, S)), mask))
d = ImageDraw.Draw(img)
d.ellipse([S / 2 - 130, S / 2 - 130, S / 2 + 130, S / 2 + 130], outline=(255, 255, 255, 120), width=14)
# Nota musical blanca abajo a la derecha
cx, cy = 690, 700
d.ellipse([cx - 95, cy - 70, cx + 95, cy + 70], fill="white")
d.rectangle([cx + 60, cy - 420, cx + 95, cy], fill="white")
d.polygon([(cx + 95, cy - 420), (cx + 250, cy - 330), (cx + 250, cy - 250), (cx + 95, cy - 330)], fill="white")

img.resize((256, 256), Image.LANCZOS).save(out / "listacd.png")
img.save(out / "listacd.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
print("ok")
