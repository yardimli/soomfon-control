"""One tiny 180x120 shutdown panorama, split across the six LCD buttons."""
from importlib.resources import files

from PIL import Image


def offline_images():
    resource = files("soomfon_control").joinpath("assets/offline.png")
    with resource.open("rb") as stream, Image.open(stream) as image:
        sheet = image.convert("RGB")
        if sheet.size != (180, 120):
            raise ValueError("Offline panorama must be 180x120 pixels")
        return [sheet.crop((column * 60, row * 60, (column + 1) * 60, (row + 1) * 60))
                for row in range(2) for column in range(3)]
