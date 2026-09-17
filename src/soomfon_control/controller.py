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
        self._brightness = config.brightness
        self._page = min(config.pages) if config.pages else None
        self._buttons = config.pages[self._page].buttons if config.pages else config.buttons
        self._page_icons = {}
        self._page_keys = sorted(config.pages) if config.pages else [None]
        self._ordered_buttons = [
            (config.pages[page].buttons if page is not None else config.buttons).get(key)
            for page in self._page_keys for key in range(6)
        ]
        self._runtime_pages = {}
        self._icon_cache = {}

    def configure(self, deck):
        self._deck = deck
        deck.set_brightness(self.config.brightness)
        self._rebuild_pages()
        icons = []
        for key in range(6):
            button = self._buttons.get(key)
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

    def _rebuild_pages(self):
        for offset, page in enumerate(self._page_keys):
            slots = self._ordered_buttons[offset * 6:(offset + 1) * 6]
            self._runtime_pages[page] = {i: button for i, button in enumerate(slots) if button is not None}
            if page is None:
                self._runtime_pages[page].update({key: button for key, button in self.config.buttons.items() if key >= 6})
            images = []
            for button in slots:
                if button is None:
                    images.append(Image.new("RGB", (60, 60), "black"))
                else:
                    if id(button) not in self._icon_cache:
                        self._icon_cache[id(button)] = button_image(button)
                    images.append(self._icon_cache[id(button)])
            self._page_icons[page] = images

    def _switch_page(self, key):
        icons = self._page_icons[key]
        if self._screensaver:
            self._screensaver.set_icons(icons)
        elif self._deck is not None:
            for index, image in enumerate(icons):
                self._deck.set_key_image(index, image)
        self._page = key
        self._buttons = self._runtime_pages[key]
        log.info("App page %s selected", self._page_keys.index(key) + 1)

    def _promote(self, key):
        if not 0 <= key < 6:
            return
        index = self._page_keys.index(self._page) * 6 + key
        button = self._ordered_buttons.pop(index)
        self._ordered_buttons.insert(0, button)
        self._rebuild_pages()
        self._switch_page(self._page_keys[0])
        log.info("Most recent app: %s", button.label)

    def _wake_display(self):
        try:
            self.actions.wake_display()
        except Exception:
            log.exception("Windows display wake failed")

    def on_key(self, key, pressed):
        if self._closed:
            return
        state = "pressed" if pressed else "released"
        if 9 <= key <= 11:
            log.info("Input: knob %s %s (key %s)", key - 9, state, key)
        else:
            log.info("Input: button %s %s", key, state)
        if pressed:
            self._wake_display()
        if pressed and key in self.config.pages:
            try:
                self._switch_page(key)
            except Exception:
                log.exception("Could not select page with button %s", key)
            return
        if self._screensaver and self._screensaver.activity(wake=pressed):
            return
        if not pressed:
            return
        try:
            if key == 9 + self.config.main_knob:
                self.actions.play_pause()
                return
            small_knobs = [encoder for encoder in range(3) if encoder != self.config.main_knob]
            if key == 9 + small_knobs[0]:
                self.actions.previous_track()
                return
            if key == 9 + small_knobs[1]:
                self.actions.next_track()
                return
            button = self._buttons.get(key)
            if not button or not button.app:
                return
            # Capture the action before changing the layout beneath this physical key.
            try:
                self._promote(key)
            except Exception:
                log.exception("Could not refresh recent-app order")
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
        if delta:
            self._wake_display()
        if self._screensaver:
            self._screensaver.activity()
        if encoder == self.config.brightness_knob and self._deck is not None:
            try:
                brightness = max(0, min(100, self._brightness + delta * self.config.brightness_step))
                if brightness != self._brightness:
                    self._deck.set_brightness(brightness)
                    self._brightness = brightness
                    log.info("Device brightness: %s%%", brightness)
            except Exception:
                log.exception("Device brightness adjustment failed")
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
