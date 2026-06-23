# Generates AXIOM Edge PWA icons: the QED tombstone (filled rounded square) in
# signal gold on the near-black brand surface. Run: python web/scripts/gen_icons.py
from PIL import Image, ImageDraw
import os

BG = (10, 11, 13, 255)        # #0A0B0D
GOLD = (233, 178, 74, 255)    # #E9B24A
HERE = os.path.dirname(os.path.abspath(__file__))
WEB = os.path.dirname(HERE)
ICONS = os.path.join(WEB, "public", "icons")
os.makedirs(ICONS, exist_ok=True)


def make(size: int, frac: float, transparent: bool = False) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0) if transparent else BG)
    d = ImageDraw.Draw(img)
    side = int(size * frac)
    x0 = (size - side) // 2
    y0 = (size - side) // 2
    r = int(side * 0.16)
    d.rounded_rectangle([x0, y0, x0 + side, y0 + side], radius=r, fill=GOLD)
    return img


# Standard icons (mark ~52% of canvas).
make(192, 0.52).save(os.path.join(ICONS, "icon-192.png"))
make(512, 0.52).save(os.path.join(ICONS, "icon-512.png"))
# Maskable: ~40% so the mark survives the platform safe-zone crop.
make(192, 0.40).save(os.path.join(ICONS, "maskable-192.png"))
make(512, 0.40).save(os.path.join(ICONS, "maskable-512.png"))
# Apple touch (opaque, no transparency).
make(180, 0.52).save(os.path.join(ICONS, "apple-touch-180.png"))
# Next.js app-dir conventions (auto favicon + apple-touch).
make(512, 0.52).save(os.path.join(WEB, "app", "icon.png"))
make(180, 0.52).save(os.path.join(WEB, "app", "apple-icon.png"))
print(f"icons written to {ICONS} and web/app/")
