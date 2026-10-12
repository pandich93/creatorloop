"""Contact sheet of out/stills/*.png with timestamps: python scripts/sheet.py [out.png] [cols]"""
import sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

root = Path(__file__).resolve().parents[1]
files = sorted((root / "out" / "stills").glob("f*.png"))
out = Path(sys.argv[1]) if len(sys.argv) > 1 else root / "out" / "sheet.png"
cols = int(sys.argv[2]) if len(sys.argv) > 2 else 6
w, h = 270, 480
rows = -(-len(files) // cols)
sheet = Image.new("RGB", (cols * w + (cols + 1) * 8, rows * (h + 34) + 8), "#0c0d10")
font = ImageFont.truetype(str(root / "public" / "fonts" / "DejaVuSansMono.ttf"), 20)
d = ImageDraw.Draw(sheet)
for i, f in enumerate(files):
    im = Image.open(f).convert("RGB").resize((w, h))
    x, y = 8 + (i % cols) * (w + 8), 8 + (i // cols) * (h + 34)
    sheet.paste(im, (x, y))
    # safe zones
    d.rectangle([x, y, x + w - 1, y + int(250 * h / 1920)], outline="#ff3b30")
    d.rectangle([x, y + h - int(350 * h / 1920), x + w - 1, y + h - 1], outline="#ff3b30")
    fr = int(f.stem[1:])
    d.text((x + 4, y + h + 6), f"{fr / 30:5.1f}s  f{fr}", fill="#c9c6c0", font=font)
sheet.save(out)
print(out, sheet.size)
