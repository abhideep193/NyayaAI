"""Cut the sphere out of assets/sphere.png (image made with ChatGPT) for the chat page.

The original has a black background. We keep only the round sphere and turn the
black around and inside its edges transparent, so it glows on the dark page.
Writes assets/sphere_cut.png (large, for the start screen) and
assets/sphere_avatar.png (small, the icon next to each answer).

Run once from the project root:
    python -m scripts.make_sphere_assets
"""

from pathlib import Path

import numpy as np
from PIL import Image

ASSETS = Path("assets")


def cut_out_sphere(image: Image.Image) -> Image.Image:
    rgba = np.asarray(image.convert("RGBA")).astype(np.float32)
    rgb = rgba[..., :3]

    # Find the sphere: every pixel that is clearly brighter than the black background.
    brightness = rgb.max(axis=2)
    ys, xs = np.nonzero(brightness > 40)
    top, bottom, left, right = ys.min(), ys.max(), xs.min(), xs.max()

    # Square crop around the sphere, with a small margin for the glow.
    centre_y, centre_x = (top + bottom) / 2, (left + right) / 2
    radius = max(bottom - top, right - left) / 2
    half = int(radius * 1.15)
    box = (int(centre_x) - half, int(centre_y) - half, int(centre_x) + half, int(centre_y) + half)

    # Transparency: dark pixels become see-through, bright ones stay solid ("luminance key"),
    # and everything outside the circle fades out.
    alpha = np.clip(brightness / 90.0, 0, 1)
    yy, xx = np.mgrid[0 : rgb.shape[0], 0 : rgb.shape[1]]
    distance = np.hypot(yy - centre_y, xx - centre_x) / radius
    alpha *= np.clip((1.08 - distance) / 0.06, 0, 1)

    out = np.dstack([rgb, alpha * 255]).astype(np.uint8)
    return Image.fromarray(out, "RGBA").crop(box)


def line_art_for_dark_page(image: Image.Image, colour=(230, 233, 242)) -> Image.Image:
    """Black lines on white -> light lines on a transparent background (for the dark top bar)."""
    rgba = np.asarray(image.convert("RGBA")).astype(np.float32)
    darkness = 1.0 - rgba[..., :3].mean(axis=2) / 255.0       # black line = 1, white paper = 0
    alpha = np.clip((darkness - 0.08) / 0.6, 0, 1) * (rgba[..., 3] / 255.0)
    out = np.zeros_like(rgba)
    out[..., :3] = colour
    out[..., 3] = alpha * 255
    icon = Image.fromarray(out.astype(np.uint8), "RGBA")
    return icon.crop(icon.getbbox())


def main() -> None:
    sphere = cut_out_sphere(Image.open(ASSETS / "sphere.png"))
    sphere.resize((480, 480), Image.LANCZOS).save(ASSETS / "sphere_cut.png", optimize=True)
    sphere.resize((96, 96), Image.LANCZOS).save(ASSETS / "sphere_avatar.png", optimize=True)
    print("wrote assets/sphere_cut.png and assets/sphere_avatar.png")

    lady = line_art_for_dark_page(Image.open(ASSETS / "lady_justice.png"))
    height = 120  # shown at ~44 px high; extra pixels keep it sharp on high-resolution screens
    lady.resize((round(lady.width * height / lady.height), height), Image.LANCZOS).save(
        ASSETS / "lady_justice_icon.png", optimize=True)
    print("wrote assets/lady_justice_icon.png")


if __name__ == "__main__":
    main()
