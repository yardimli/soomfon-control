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
            fitted = ImageOps.contain(source.convert("RGBA"), (60, 60))
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

    def configure(self, deck):
        deck.set_brightness(self.config.brightness)
        for key in range(6):
            button = self.config.buttons.get(key)
            if button:
                deck.set_key_image(key, button_image(button))
            else:
                deck.clear_key(key)
        deck.on_key(self.on_key)
        deck.on_encoder(self.on_encoder)

    def on_key(self, key, pressed):
        state = "pressed" if pressed else "released"
        if 9 <= key <= 11:
            log.info("Input: knob %s %s (key %s)", key - 9, state, key)
        else:
            log.info("Input: button %s %s", key, state)
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
        log.info("Input: knob %s turn delta=%+d", encoder, delta)
        if encoder == self.config.main_knob:
            try:
                self.actions.volume(delta * self.config.volume_steps)
            except Exception:
                log.exception("Volume adjustment failed")

    def close(self):
        self._pool.shutdown(wait=True, cancel_futures=True)
