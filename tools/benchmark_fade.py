"""Measure encoding CPU time and HID report bytes, without opening the device."""
from pathlib import Path
import statistics
import threading
import time

from PIL import Image

from soomfon_control.cli import _driver
from soomfon_control.screensaver import fade_frames


class CountingTransport:
    def __init__(self):
        self.bytes = 0

    def write(self, data):
        self.bytes += len(data)


def main():
    driver = _driver()
    # Use upstream's real encoder and packet framing with a counting-only transport.
    deck = object.__new__(driver)
    deck._lock = threading.Lock()
    deck._dev = CountingTransport()
    images = []
    for path in sorted((Path(__file__).resolve().parents[1] / "assets/faces").glob("*.png")):
        with Image.open(path) as image:
            images.append(image.convert("RGB"))
    durations, sizes = [], []
    for index, old in enumerate(images):
        before = deck._dev.bytes
        start = time.process_time()
        for frame in fade_frames(old, images[(index + 1) % len(images)]):
            deck.set_key_image(0, frame)
        durations.append(time.process_time() - start)
        sizes.append(deck._dev.bytes - before)
    print(f"Transitions sampled: {len(images)} (12 uploads each)")
    print(f"HID report bytes per transition: mean={statistics.mean(sizes):.0f}, max={max(sizes)}")
    print(f"Mean blending + JPEG + packet framing CPU: {statistics.mean(durations) * 1000:.2f} ms/transition")
    print(f"At 6 transitions/minute: {statistics.mean(sizes) / 10 / 1024:.2f} KiB/s average")
    print("Excludes actual USB I/O, OS scheduling and USB bus framing; device was not opened.")


if __name__ == "__main__":
    main()
