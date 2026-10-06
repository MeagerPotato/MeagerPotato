"""
Prepare the dp (a flat illustration) for clean ASCII conversion:
  1. remove the background (rembg) so the subject is isolated
  2. bilateral-smooth away the paper texture (otherwise skin turns to `::::`
     noise and the eyes drown in it) while keeping the drawn lines sharp
  3. stretch tones so skin lands near white and hair/lines stay dark
  4. darken the line work (difference-of-gaussians ridges) -- eyelids, pupils,
     glasses frame and smile are thin dark strokes that plain luminance
     averaging washes out at ascii resolution
  5. composite onto white and crop square around the subject

Output: source-prepped.png (grayscale), consumed by make_ascii_svg.py.

    python scripts/prep_photo.py <input.png> [output.png]

PHOTO=1 switches to photo mode, for a real photograph instead of a drawing:
local contrast (CLAHE), a light smooth, a soft vignette that fades the corners
out, and the tones INVERTED, so that on the dark terminal bright fur prints as
dense characters and dark eyes stay empty (a drawing wants the opposite: its
dark lines are what should print).

    PHOTO=1 python scripts/prep_photo.py <photo.png> [output.png]
"""
import os
import sys

import cv2
import numpy as np
from PIL import Image
try:
    from rembg import remove
except ImportError:      # no rembg -> keep the whole frame (fine for a tight crop)
    remove = None

HERE = os.path.dirname(os.path.abspath(__file__))
INP = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "..", "source-photo.png")
OUT = sys.argv[2] if len(sys.argv) > 2 else os.path.join(HERE, "..", "source-prepped.png")

LINE_WEIGHT = 0.6     # how hard drawn lines are pushed toward black

if os.environ.get("PHOTO"):
    gray = np.array(Image.open(INP).convert("L"))
    side = min(gray.shape)
    y0, x0 = (gray.shape[0] - side) // 2, (gray.shape[1] - side) // 2
    gray = gray[y0:y0 + side, x0:x0 + side]
    gray = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8)).apply(gray)
    gray = cv2.bilateralFilter(gray, 9, 35, 9)
    lo, hi = np.percentile(gray, [3, 99])
    tone = np.clip((gray.astype(np.float32) - lo) / (hi - lo), 0, 1) ** 1.25
    yy, xx = np.mgrid[0:side, 0:side].astype(np.float32)
    r = np.hypot(xx - side / 2, yy - side / 2) / (side / 2)
    tone *= np.clip((1.28 - r) / 0.30, 0, 1)      # full inside r=0.98, gone by 1.28
    Image.fromarray(((1.0 - tone) * 255).astype(np.uint8), mode="L").save(OUT)
    print("wrote", OUT, (side, side), "(photo mode)")
    sys.exit(0)

# 1. cut out the subject
cut = Image.open(INP).convert("RGBA")
if remove is not None:
    cut = remove(cut)
rgb = np.array(cut.convert("RGB"))
alpha = np.array(cut.split()[-1])                 # 0 = background
gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)

# 2. smooth texture, keep edges
smooth = gray
for _ in range(3):
    smooth = cv2.bilateralFilter(smooth, 9, 40, 9)

# 3. tone stretch over the subject only
lo, hi = np.percentile(smooth[alpha > 128], [2, 92])
tone = np.clip((smooth.astype(np.float32) - lo) / (hi - lo), 0, 1)

# 4. dark-on-light ridges -> darken
fine = cv2.GaussianBlur(smooth, (0, 0), 1.5).astype(np.float32)
coarse = cv2.GaussianBlur(smooth, (0, 0), 6).astype(np.float32)
lines = np.clip((coarse - fine) / 40.0, 0, 1)
out = np.clip(tone - LINE_WEIGHT * lines, 0, 1) * 255

# 5. paste onto white (feathered a hair to avoid a halo), square crop
mask = cv2.GaussianBlur(alpha.astype(np.float32) / 255.0, (0, 0), 1.0)
out = out * mask + 255.0 * (1.0 - mask)

ys, xs = np.where(alpha > 20)
side = max(xs.max() - xs.min(), ys.max() - ys.min()) + 60
cx, cy = (xs.min() + xs.max()) // 2, (ys.min() + ys.max()) // 2
canvas = np.full((side, side), 255, np.uint8)
x0, y0 = cx - side // 2, cy - side // 2
sx0, sy0 = max(x0, 0), max(y0, 0)
sx1, sy1 = min(x0 + side, out.shape[1]), min(y0 + side, out.shape[0])
canvas[sy0 - y0:sy1 - y0, sx0 - x0:sx1 - x0] = out[sy0:sy1, sx0:sx1].astype(np.uint8)

Image.fromarray(canvas, mode="L").save(OUT)
print("wrote", OUT, canvas.shape)
