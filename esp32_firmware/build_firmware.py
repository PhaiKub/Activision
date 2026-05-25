"""
build_firmware.py — Compile esp32s3_usb_hid.ino and merge to a single flashable .bin

Usage:
    python build_firmware.py

Outputs:
    esp32_firmware/esp32s3_usb_hid.bin   ← merged binary, flash at 0x0

Requirements:
    arduino-cli  in PATH  → https://arduino.github.io/arduino-cli/
    esptool      pip install esptool

Install ESP32 core (once):
    arduino-cli core install esp32:esp32

---- Manual alternative (Arduino IDE) ----
1. Sketch → Export Compiled Binary
2. Copy the 3 output files next to this script and run:
       python build_firmware.py --merge-only
"""

import os
import subprocess
import shutil
import sys
import argparse


# ── Config ────────────────────────────────────────────────────────────────────

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SKETCH_DIR = os.path.join(SCRIPT_DIR, "esp32s3_usb_hid")   # folder with .ino
BUILD_DIR  = os.path.join(SCRIPT_DIR, "build")
MERGED_BIN = os.path.join(SCRIPT_DIR, "esp32s3_usb_hid.bin")

# ESP32-S3 flash layout
BOOTLOADER_ADDR  = "0x0"
PARTITIONS_ADDR  = "0x8000"
APP_ADDR         = "0x10000"

# arduino-cli FQBN
#   USBMode=tinyusb  → USB-OTG (TinyUSB)   ← ใช้รัน HID bot
#   CDCOnBoot=cdc    → CDC on Boot Enabled  ← ใช้ Serial ping
FQBN = "esp32:esp32:esp32s3:USBMode=tinyusb,CDCOnBoot=cdc"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _find_arduino_cli() -> str:
    cli = shutil.which("arduino-cli")
    if cli:
        return cli
    candidates = [
        os.path.expanduser(r"~\AppData\Local\Arduino15\arduino-cli.exe"),
        r"C:\Program Files\Arduino CLI\arduino-cli.exe",
        os.path.expanduser("~/bin/arduino-cli"),
    ]
    for c in candidates:
        if os.path.isfile(c):
            return c
    raise FileNotFoundError(
        "arduino-cli not found.\n"
        "Install: https://arduino.github.io/arduino-cli/latest/installation/\n"
        "Then:    arduino-cli core install esp32:esp32"
    )


def _run(cmd: list, **kwargs):
    print(">", " ".join(str(c) for c in cmd))
    subprocess.run(cmd, check=True, **kwargs)


def _find_build_files(build_dir: str) -> tuple[str, str, str]:
    """
    Search for (bootloader, partitions, app) .bin files.
    Looks in:
      1. build_dir (our explicit output dir)
      2. Arduino IDE build cache: sketch_dir/build/<board>/
    """
    search_dirs = [build_dir]

    # Arduino IDE stores build output inside the sketch folder
    arduino_build = os.path.join(SKETCH_DIR, "build")
    if os.path.isdir(arduino_build):
        for sub in os.listdir(arduino_build):
            search_dirs.append(os.path.join(arduino_build, sub))

    bootloader = partitions = app = None

    for d in search_dirs:
        if not os.path.isdir(d):
            continue
        for name in os.listdir(d):
            full = os.path.join(d, name)
            if name.endswith(".bootloader.bin") and bootloader is None:
                bootloader = full
            elif name.endswith(".partitions.bin") and partitions is None:
                partitions = full
            elif name.endswith(".ino.bin") and app is None:
                app = full

    missing = {k: v for k, v in {"bootloader": bootloader, "partitions": partitions, "app": app}.items() if v is None}
    if missing:
        raise FileNotFoundError(
            f"Missing build file(s): {list(missing.keys())}\n"
            f"Searched in: {search_dirs}\n"
            "Export Compiled Binary from Arduino IDE first (Sketch → Export Compiled Binary)"
        )

    return bootloader, partitions, app


def merge_bin(bootloader: str, partitions: str, app: str, out: str):
    """Use esptool merge_bin to combine the 3 files into one flashable binary."""
    print(f"\n[build_firmware] Merging → {out}")
    _run([
        sys.executable, "-m", "esptool",
        "--chip", "esp32s3",
        "merge_bin",
        "--output", out,
        "--flash_mode", "dio",
        "--flash_freq", "80m",
        "--flash_size", "8MB",
        BOOTLOADER_ADDR, bootloader,
        PARTITIONS_ADDR, partitions,
        APP_ADDR, app,
    ])


# ── Main ──────────────────────────────────────────────────────────────────────

def compile_sketch():
    cli = _find_arduino_cli()
    print(f"[build_firmware] arduino-cli : {cli}")
    print(f"[build_firmware] Sketch      : {SKETCH_DIR}")
    print(f"[build_firmware] FQBN        : {FQBN}")
    print()

    os.makedirs(BUILD_DIR, exist_ok=True)
    _run([
        cli, "compile",
        "--fqbn", FQBN,
        "--output-dir", BUILD_DIR,
        "--verbose",
        SKETCH_DIR,
    ])


def build(merge_only=False):
    if not merge_only:
        compile_sketch()

    bootloader, partitions, app = _find_build_files(BUILD_DIR)

    print(f"\n[build_firmware] Found:")
    print(f"  bootloader : {bootloader}")
    print(f"  partitions : {partitions}")
    print(f"  app        : {app}")

    merge_bin(bootloader, partitions, app, MERGED_BIN)
    print(f"\n[build_firmware] ✅  Ready to flash: {MERGED_BIN}")
    return MERGED_BIN


def main():
    p = argparse.ArgumentParser()
    p.add_argument(
        "--merge-only", action="store_true",
        help="Skip compile — only merge existing files in build/ folder"
    )
    args = p.parse_args()
    build(merge_only=args.merge_only)


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as e:
        print(f"\n[build_firmware] ❌  Failed (exit {e.returncode})")
        sys.exit(e.returncode)
    except Exception as e:
        print(f"\n[build_firmware] ❌  {e}")
        sys.exit(1)
