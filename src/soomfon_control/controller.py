from __future__ import annotations

import logging
import threading
from concurrent.futures import ThreadPoolExecutor

from PIL import Image, ImageDraw, ImageFont, ImageOps

from .config import Config

log = logging.getLogger(__name__)


def button_image(button):
    image = Image.new("RGB", (60, 60), "#172337")
    if button.icon:
        with Image.open(button.icon) as source:
            # Reserve one background pixel on all four edges of the 60x60 LCD.
            fitted = ImageOps.contain(source.convert("RGBA"), (58, 58))
            image.paste(fitted, ((60 - fitted.width) // 2, (60 - fitted.height) // 2), fitted)
    else:
        draw = ImageDraw.Draw(image)
        font = ImageFont.load_default()
        # Short text fallbacks mean the sample works without external icon files.
        lines = [button.label[i:i + 8] for i in range(0, min(len(button.label), 24), 8)]
        draw.multiline_text((30, 30), "\n".join(lines), fill="white", font=font,
                            anchor="mm", align="center", spacing=3)
    return image


class Controller:
    def __init__(self, config: Config, actions):
        self.config = config
        self.actions = actions
        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="app-launcher")
        self._pending = set()
        self._lock = threading.Lock()
        self._screensaver = None
        self._deck = None
        self._closed = False

    def configure(self, deck):
        self._deck = deck
        deck.set_brightness(self.config.brightness)
        icons = []
        for key in range(6):
            button = self.config.buttons.get(key)
            if button:
                image = button_image(button)
                deck.set_key_image(key, image)
            else:
                image = Image.new("RGB", (60, 60), "black")
                deck.clear_key(key)
            icons.append(image)
        deck.on_key(self.on_key)
        deck.on_encoder(self.on_encoder)
        if self.config.screensaver:
            from .screensaver import Screensaver
            self._screensaver = Screensaver(deck, self.config.screensaver, icons)
            self._screensaver.start()

    def on_key(self, key, pressed):
        if self._closed:
            return
        state = "pressed" if pressed else "released"
        if 9 <= key <= 11:
            log.info("Input: knob %s %s (key %s)", key - 9, state, key)
        else:
            log.info("Input: button %s %s", key, state)
        if self._screensaver and self._screensaver.activity(wake=pressed):
            return
        if not pressed:
            return
        try:
            if key == 9 + self.config.main_knob:
                self.actions.play_pause()
                return
            button = self.config.buttons.get(key)
            if not button or not button.app:
                return
            # Coalesce repeated presses while an app is still starting.
            with self._lock:
                if button.app in self._pending:
                    return
                self._pending.add(button.app)
            self._pool.submit(self._activate, button.app)
        except Exception:
            log.exception("Button %s failed", key)

    def _activate(self, app):
        try:
            self.actions.activate(app)
        except Exception:
            log.exception("App action failed for %s", app.process)
        finally:
            with self._lock:
                self._pending.discard(app)

    def on_encoder(self, encoder, delta):
        if self._closed:
            return
        log.info("Input: knob %s turn delta=%+d", encoder, delta)
        if self._screensaver:
            self._screensaver.activity()
        if encoder == self.config.main_knob:
            try:
                self.actions.volume(delta * self.config.volume_steps)
            except Exception:
                log.exception("Volume adjustment failed")

    def close(self):
        if self._closed:
            return
        self._closed = True
        try:
            if self._screensaver:
                self._screensaver.close(restore_icons=False)
            if self._deck:
                from .offline import offline_images
                for key, image in enumerate(offline_images()):
                    self._deck.set_key_image(key, image)
                log.info("Controller stopped; offline artwork displayed")
        finally:
            self._pool.shutdown(wait=True, cancel_futures=True)
