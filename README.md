<div align="center">
  <h1>Charge-Grinder — ESP32-S3 USB HID Edition</h1>
  <p><b>An advanced, hardware-emulated automation bot for Limbus Company.</b></p>
  <p><i>Forked and heavily modified from <a href="https://github.com/Walpth/Charge-Grinder">Walpth/Charge-Grinder</a></i></p>
</div>

---

## Pls Donate me
[https://ko-fi.com/phaikub](https://ko-fi.com/phaikub). OR [https://easydonate.app/phaikub_990l](https://easydonate.app/phaikub_990l)

---

## 🔌 ESP32-S3 — USB Port Guide

The ESP32-S3 has **two separate USB ports** used for different purposes:

| Port | Role | When to use |
|------|------|-------------|
| 🔵 **USB** (Native OTG) | Run the bot — sends HID mouse & keyboard | Every normal session |
| 🟡 **COM** (UART / CH340) | Flash firmware via esptool | First-time setup or firmware update |

> Always plug the **USB (Native OTG)** port when running the bot.  
> Only plug the **COM (CH340)** port when flashing firmware.

---

## ⚡ Firmware Setup

### Option A — Flash via the App (Recommended)

The firmware (`.bin`) is **already bundled inside `app.exe`** — no need to compile or download anything separately.

1. Plug in the **COM (CH340) port** of your ESP32-S3.
2. Launch `app.exe` — the scan dialog will appear automatically.
3. Enter the COM port number and click **⚡ Flash Firmware**.
4. Wait for flashing to complete (~30 s), then switch to the **USB (Native OTG) port** and click **Re-scan**.

### Option B — Flash via Arduino IDE

1. Plug in the **COM (CH340) port**.
2. Open [`esp32_firmware/esp32s3_usb_hid/esp32s3_usb_hid.ino`](esp32_firmware/esp32s3_usb_hid/esp32s3_usb_hid.ino) in Arduino IDE.
3. Set the following under **Tools**:

   | Setting | Value |
   |---------|-------|
   | Board | `ESP32S3 Dev Module` |
   | USB Mode | `USB-OTG (TinyUSB)` ⚠️ Critical |
   | USB CDC On Boot | `Enabled` ⚠️ Critical |

4. Click **Upload**.

### Option C — Compile & Flash via arduino-cli (for rebuilding firmware)

```powershell
# Install arduino-cli and ESP32 core (once)
winget install ArduinoSA.Arduino-CLI
arduino-cli core install esp32:esp32

# Compile + merge bootloader + partitions + app into one .bin
python esp32_firmware/build_firmware.py
# Output: esp32_firmware/esp32s3_usb_hid.bin
# Then rebuild the exe to bundle the new firmware:
.\run-build-windows.ps1
```

### LED Status Indicators

The onboard WS2812 RGB LED shows the current device state:

| Color | Meaning |
|-------|---------|
| 🟡 Blinking Yellow | Booting / initializing USB |
| 🟣 Solid Purple | Ready — waiting for host connection |
| 🔵 Solid Blue | Active — receiving mouse/keyboard commands |
| 🟢 Blinking Green | Idle — host disconnected or session ended |
| 🔴 Flashing Red | Error — invalid command received |

---

## 🚀 Running the Bot

### For Users
1. Download the latest release from the [Releases](https://github.com/PhaiKub/Activision/releases) page.
2. Plug in your ESP32-S3 via the **USB (Native OTG)** 🔵 port.
3. Keep **Limbus Company** running in the foreground — English language, `1920×1080`, windowed or fullscreen.
4. Launch `app.exe` (no console) or `app_debug.exe` (with console output).
5. The app scans for the ESP32-S3 automatically.
   - **Found:** connects and proceeds to the main UI.
   - **Not found:** enter the USB port manually, or use **⚡ Flash Firmware** (via COM port) if the board has no firmware yet.
6. Configure your team and click **Start**.

### For Developers
```powershell
git clone https://github.com/PhaiKub/Activision.git
cd Activision
pip install -r requirements.txt
python App.py
```

To build standalone executables:
```powershell
# Build app.exe + app_debug.exe via Nuitka
# (esp32s3_usb_hid.bin is already in esp32_firmware/ and gets bundled automatically)
.\run-build-windows.ps1
```


## 📜 License & Credits

This project is licensed under the **GNU General Public License v3.0**. See `LICENSE` for details.

- **Modifications & ESP32 Bridge:** Developed by PhaiKub & Colors (2026). Replaced the Ghub DLL backend with ESP32-S3 USB HID emulation, added built-in firmware flasher, version checker, and human-like input profiles.
- **Original Framework:** Built upon [Walpth/Charge-Grinder](https://github.com/Walpth/Charge-Grinder).
