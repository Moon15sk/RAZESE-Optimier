import os
from PIL import Image, ImageDraw, ImageFont

os.makedirs("bcg", exist_ok=True)
S = 512
img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
d = ImageDraw.Draw(img)
d.rounded_rectangle((8, 8, S - 8, S - 8), radius=110, fill=(10, 10, 14, 255), outline=(212, 175, 55, 255), width=14)
d.rounded_rectangle((38, 38, S - 38, S - 38), radius=84, outline=(243, 215, 122, 120), width=3)

font = None
for name in ("segoeuib.ttf", "arialbd.ttf", "DejaVuSans-Bold.ttf"):
    try:
        font = ImageFont.truetype(name, 330)
        break
    except Exception:
        pass
font = font or ImageFont.load_default()
d.text((S / 2, S / 2 + 6), "R", font=font, fill=(212, 175, 55, 255), anchor="mm")

img.save("bcg/icon.ico", sizes=[(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)])
print("bcg/icon.ico created")
