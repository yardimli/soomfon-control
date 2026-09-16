"""Install a verified official HIDAPI Windows DLL into this checkout only."""
import hashlib
import io
from pathlib import Path
import platform
import struct
import sys
import urllib.request
import zipfile

URL = "https://github.com/libusb/hidapi/releases/download/hidapi-0.15.0/hidapi-win.zip"
SHA256 = "d18c43ec9506a2f6d7faa9c7e0a342c4b64fbae521b71b5d4ac0777fd24dda93"


def main():
    if sys.platform != "win32" or platform.machine().lower() not in {"amd64", "x86_64", "x86", "i386", "i686"}:
        raise SystemExit("This helper supports x86/x64 Windows Python. Install HIDAPI manually for other architectures.")
    arch = "x64" if struct.calcsize("P") == 8 else "x86"
    destination = Path(__file__).resolve().parents[1] / "native" / "hidapi.dll"
    print(f"Downloading official HIDAPI 0.15.0 ({arch})...", flush=True)
    with urllib.request.urlopen(URL, timeout=180) as response:
        archive = response.read()
    if hashlib.sha256(archive).hexdigest() != SHA256:
        raise SystemExit("HIDAPI archive checksum mismatch; no DLL written.")
    with zipfile.ZipFile(io.BytesIO(archive)) as bundle:
        dll = bundle.read(f"{arch}/hidapi.dll")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(dll)
    print(f"Installed {destination}")


if __name__ == "__main__":
    main()

