"""Single display worker: animate while idle, cancel stale frames on activity."""
from __future__ import annotations

import logging
from collections import deque
import random
import threading
import time

from PIL import Image, ImageOps

from .config import ScreensaverConfig

log = logging.getLogger(__name__)


def fade_frames(old_face, new_face):
    """Twelve tiny frames: old face to black, then black to the new face."""
    black = Image.new("RGB", (60, 60), "black")
    return ([Image.blend(old_face, black, step / 6) for step in range(1, 7)]
            + [Image.blend(black, new_face, step / 6) for step in range(1, 7)])


class Screensaver:
    def __init__(self, deck, config: ScreensaverConfig, icons, *, clock=time.monotonic):
        self.deck = deck
        self.config = config
        self.icons = icons
        self.clock = clock
        self.faces = []
        for path in config.images:
            with Image.open(path) as source:
                face = Image.new("RGB", (60, 60), "#172337")
                fitted = ImageOps.contain(source.convert("RGBA"), (60, 60))
                face.paste(fitted, ((60 - fitted.width) // 2, (60 - fitted.height) // 2), fitted)
                self.faces.append(face)
        self._lock = threading.Lock()
        self._changed = threading.Event()
        self._stop = threading.Event()
        self._thread = None
        self._last_activity = clock()
        self._next_frame = [0.0] * 6
        self._next_change = 0.0
        self._current_faces = [None] * 6
        self._fade_frames = [deque() for _ in range(6)]
        self._next_fade = [0.0] * 6
        self._fade_seconds = 0.08
        self._generation = 0
        self._restore = False
        self.active = False
        self._bag = []
        self._weather = None
        self._cards = None
        if config.mode == "cards":
            from .weather import WeatherService
            from .cards import CardsRenderer
            self._weather = WeatherService(config.weather)
            self._cards = CardsRenderer(config.local_timezone, self._weather)

    def start(self):
        if self._weather:
            self._weather.start()
        self._last_activity = self.clock()
        self._thread = threading.Thread(target=self._run, name="screensaver", daemon=True)
        self._thread.start()

    def activity(self, *, wake=True):
        """Return whether this event woke the screensaver (used to swallow wake presses)."""
        with self._lock:
            self._last_activity = self.clock()
            was_active = self.active and wake
            if was_active:
                self.active = False
                self._restore = True
                self._fade_frames = [deque() for _ in range(6)]
                self._generation += 1
        self._changed.set()
        if was_active:
            log.info("Screensaver stopped; restoring app icons")
        return was_active

    def _next_face(self, key):
        # Prefer unseen faces and avoid all currently displayed faces, including this key's.
        excluded = set(self._current_faces)
        available = [i for i in self._bag if i not in excluded]
        if not available:
            available = [i for i in range(len(self.faces)) if i not in excluded]
            if not available:
                # A custom set of exactly six faces needs a duplicate to change one at a time.
                available = [i for i in range(len(self.faces)) if i != self._current_faces[key]]
            self._bag = available.copy()
        selected = random.choice(available)
        self._bag.remove(selected)
        self._current_faces[key] = selected
        return self.faces[selected]

    def set_icons(self, icons):
        """Switch pages, cancel any in-flight frame, and wake directly into the new page."""
        with self._lock:
            self.icons = icons
            self.active = False
            self._last_activity = self.clock()
            self._restore = True
            self._fade_frames = [deque() for _ in range(6)]
            self._generation += 1
        self._changed.set()

    def _delay(self):
        return random.uniform(self.config.frame_seconds * 0.5, self.config.frame_seconds * 1.5)

    def tick(self):
        """One display update, also callable deterministically by tests."""
        with self._lock:
            now = self.clock()
            if self._restore:
                self._restore = False
                frames = list(enumerate(self.icons))
            elif self.active or now - self._last_activity >= self.config.idle_seconds:
                entering = not self.active
                if entering:
                    self.active = True
                    self._next_frame = [0.0] * 6
                    self._next_change = 0.0
                    self._current_faces = [None] * 6
                    self._fade_frames = [deque() for _ in range(6)]
                    log.info("Screensaver started after %ss idle", self.config.idle_seconds)
                if self._cards:
                    frames = self._cards.render(force=entering)
                else:
                    frames = []
                    due = [key for key in range(6)
                           if self._current_faces[key] is not None
                           and not self._fade_frames[key]
                           and now >= self._next_frame[key]]
                    # Only the longest-waiting button may change after the shared cooldown.
                    change_key = (min(due, key=lambda key: self._next_frame[key])
                                  if due and now >= self._next_change else None)
                    for key in range(6):
                        if self._fade_frames[key]:
                            if now >= self._next_fade[key]:
                                frames.append((key, self._fade_frames[key].popleft()))
                                self._next_fade[key] = now + self._fade_seconds
                        elif self._current_faces[key] is None or key == change_key:
                            changing = self._current_faces[key] is not None
                            old_face = self.faces[self._current_faces[key]] if changing else None
                            new_face = self._next_face(key)
                            if changing:
                                self._fade_frames[key] = deque(fade_frames(old_face, new_face))
                                frames.append((key, self._fade_frames[key].popleft()))
                                self._next_fade[key] = now + self._fade_seconds
                            else:
                                frames.append((key, new_face))
                            self._next_frame[key] = now + self._delay()
                            if changing:
                                self._next_change = now + 10
                                for other in range(6):
                                    if other != key:
                                        self._next_frame[other] = max(now, self._next_frame[other]) + 10
            else:
                return
            generation = self._generation
        for key, image in frames:
            with self._lock:
                if generation != self._generation or self._stop.is_set():
                    return
            # Only this worker writes images; activity never waits for a USB upload.
            self.deck.set_key_image(key, image)

    def _run(self):
        try:
            while not self._stop.is_set():
                self._changed.wait(0.05)
                self._changed.clear()
                if not self._stop.is_set():
                    self.tick()
        except Exception:
            log.exception("Screensaver display update failed; disabling animation until restart")
            with self._lock:
                self.active = False
            try:
                for key, image in enumerate(self.icons):
                    self.deck.set_key_image(key, image)
            except Exception:
                log.exception("Could not restore icons after display failure")

    def close(self, *, restore_icons=True):
        self._stop.set()
        self._changed.set()
        if self._weather:
            self._weather.close()
        if self._thread:
            self._thread.join()
        # Leave app icons on the hardware when quitting, not a frozen screensaver.
        if restore_icons:
            for key, image in enumerate(self.icons):
                self.deck.set_key_image(key, image)
        self.active = False
