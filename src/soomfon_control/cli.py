from __future__ import annotations

import argparse
import ctypes
import logging
import os
from pathlib import Path
import sys

from .config import ConfigError, load_config

_dll = None


def _driver():
    global _dll
    # Preload an explicitly supplied DLL or the project-local installation.
    default = Path(__file__).resolve().parents[2] / "native" / "hidapi.dll"
    dll_path = Path(os.environ.get("SOOMFON_HIDAPI_DLL", str(default)))
    if dll_path.is_file():
        _dll = ctypes.CDLL(str(dll_path.resolve()))
    try:
        from soomfon import Soomfon
    except ImportError as exc:
        raise RuntimeError("Cannot load SOOMFON/HIDAPI. Install this project and run "
                           "python tools/install_hidapi.py; see README.md.") from exc
    return Soomfon


def main(argv=None):
    parser = argparse.ArgumentParser(description="SOOMFON CN002 Windows controller")
    parser.add_argument("--config", type=Path, default=Path("config.json"))
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="Validate JSON and icons without hardware")
    mode.add_argument("--monitor", action="store_true", help="Print raw button/knob events without actions")
    mode.add_argument("--list-windows", action="store_true", help="List visible app processes and window titles")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    try:
        if args.check:
            config = load_config(args.config)
            print(f"Configuration OK: {len(config.buttons)} buttons; main knob {config.main_knob}")
            return 0
        if sys.platform != "win32":
            raise RuntimeError("Desktop actions currently support Windows only.")
        if args.list_windows:
            from .windows import windows
            for window in windows():
                print(f"{window.process}\t{window.title}")
            return 0
        config = None if args.monitor else load_config(args.config)
        driver = _driver()
        with driver() as deck:
            if args.monitor:
                deck.on_key(lambda key, pressed: print(f"key {key}: {'pressed' if pressed else 'released'}", flush=True))
                deck.on_encoder(lambda enc, delta: print(f"encoder {enc}: {delta:+d}", flush=True))
                print("Monitoring inputs. Ctrl+C to stop.", flush=True)
                deck.run_forever()
            else:
                from .controller import Controller
                from .windows import WindowsActions
                controller = Controller(config, WindowsActions())
                try:
                    controller.configure(deck)
                    logging.info("Controller ready. Ctrl+C to stop; restart after editing JSON.")
                    deck.run_forever()
                finally:
                    deck.stop()
                    controller.close()
        return 0
    except KeyboardInterrupt:
        return 0
    except (ConfigError, RuntimeError, OSError, StopIteration) as exc:
        logging.error("%s", exc or "Device found but its expected HID interface is missing")
        return 1

