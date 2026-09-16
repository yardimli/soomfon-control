"""Crop the generated 8x8 sprite sheet into 64 native-size display assets."""
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]


def main():
    destination = ROOT / "assets" / "faces"
    destination.mkdir(parents=True, exist_ok=True)
    with Image.open(ROOT / "assets" / "faces-sheet.png") as sheet:
        width, height = sheet.size
        for row in range(8):
            for column in range(8):
                box = (round(column * width / 8), round(row * height / 8),
                       round((column + 1) * width / 8), round((row + 1) * height / 8))
                face = sheet.crop(box).convert("RGB").resize((60, 60), Image.Resampling.LANCZOS)
                face.save(destination / f"face-{row * 8 + column + 1:02d}.png")
    print("Saved 64 faces at 60x60 pixels.")


if __name__ == "__main__":
    main()
