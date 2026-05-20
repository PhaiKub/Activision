<div align="center">
  <h1>Charge-Grinder — ESP32-S3 USB HID Edition</h1>
  <p><b>An advanced, hardware-emulated automation bot for Limbus Company.</b></p>
  <p><i>Forked and heavily modified from <a href="https://github.com/Walpth/Charge-Grinder">Walpth/Charge-Grinder</a></i></p>
</div>

---

## 🛠️ Bot Features (Software & Hardware)

- **Complete Automation:** Fully autonomous Mirror Dungeon Normal/Hard modes and Luxcavation farming.
- **Hardware-Level Input Emulation:** Emulates actual mouse and keyboard signals using an **ESP32-S3** board. Bypasses software-level anti-cheat detection entirely.
- **Dynamic Team Composition:** Configure custom team synergies, affinity priorities, and win-rates using a built-in manager.
- **Human-Like Behavior Profiles:** Integrated cursor movement curves, coordinate jittering, and rhythm variance ([source/utils/profiles.py](file:///C:/Users/Colors/Documents/GitHub/Activision/source/utils/profiles.py)) to avoid robotic input signatures.
- **Modern GUI Interface:** Built using PySide6 ([App.py](file:///C:/Users/Colors/Documents/GitHub/Activision/App.py)) for an intuitive setup, configurations editor, and log viewing.
- **Auto-Recovery:** Detects disconnections or game errors, automatically restarts or recovers processes, and safely shuts down if out of Enkephalin.

---

## 🥇 Setup ESP32-S3 (USB HID Combo)

*This project requires an ESP32-S3 board. A single USB cable handles power, serial commands, and emulation signals.*

### 1. Flash the Firmware
1. Open [esp32s3_usb_hid.ino](file:///C:/Users/Colors/Documents/GitHub/Activision/esp32_firmware/esp32s3_usb_hid.ino) in Arduino IDE.
2. Configure the following board settings under the **Tools** menu:
   - **Board:** `ESP32-S3 Dev Module`
   - **USB Mode:** `USB-OTG (TinyUSB)` *(Critical)*
   - **USB CDC On Boot:** `Enabled` *(Critical for COM port communication)*
3. Click **Upload** to flash the firmware.

### 2. LED Status Indicators
The onboard WS2812 RGB LED (typically Pin 48) displays status codes:
* 🟡 **Blinking Yellow:** Device booting or initializing USB drivers.
* 🟣 **Solid Purple:** Ready (waiting for the Python host script to connect).
* 🔵 **Solid Blue:** Active (actively receiving and executing mouse/keyboard commands).
* 🟢 **Blinking Green:** Idle (Python script disconnected or grind finished).
* 🔴 **Flashing Red:** Communication error (received an invalid command block).

---

## 🚀 Running the Bot

### For Users
1. Download the compiled release executable from the releases section, or compile it yourself.
2. Connect your flashed ESP32-S3 board to your PC via USB.
3. Keep **Limbus Company** running in the foreground (English language, 16:9 ratio, windowed/fullscreen `1920x1080` strongly recommended).
4. Launch `app.exe` (standard windowed application) or `app_debug.exe` (windowed with console output).
5. The application will auto-detect the board's COM port. If detection fails, select it manually (saved to `esp32_config.json`).
6. Select your farming configuration and click **Start**.

### For Developers
1. Clone the repository and install requirements:
   ```powershell
   git clone https://github.com/PhaiKub/Activision.git
   cd Activision
   pip install -r requirements.txt
   ```
2. Run the application GUI directly:
   ```powershell
   python App.py
   ```

---

## 🛠️ Diagnostics, Utilities & Build Tools

### Diagnostic Scripts
* **[test_esp32s3.py](file:///C:/Users/Colors/Documents/GitHub/Activision/test_esp32s3.py)**: Direct command-line utility to test serial communication with the ESP32-S3. Validates ping response, queries USB status, and tests mouse/keyboard inputs.
* **[debug_hid.py](file:///C:/Users/Colors/Documents/GitHub/Activision/debug_hid.py)**: Low-level diagnostic utility to troubleshoot raw HID Vendor report communication using the `hidapi` library.

### Analytics Tool
* **[stats.py](file:///C:/Users/Colors/Documents/GitHub/Activision/stats.py)**: Analytical script that parses `game.log` (generated during bot runs) and compiles performance statistics into `game.csv`. Calculates average/median completion times per floor, battle duration breakdowns, and team composition efficiency.

### Build Pipelines
* **[run-build-windows.ps1](file:///C:/Users/Colors/Documents/GitHub/Activision/run-build-windows.ps1)**: A PowerShell helper script that invokes the Nuitka compiler through [release/windows/nuitka-windows.py](file:///C:/Users/Colors/Documents/GitHub/Activision/release/windows/nuitka-windows.py) to compile stand-alone binaries:
  * `app.exe` — Clean standalone executable with console mode disabled.
  * `app_debug.exe` — Debug executable with console logging visible.

---

## ⚠️ Requirements & Best Practices

* **Do Not Minimize the Game:** The bot grabs pixels from the active window to navigate (implemented in [os_windows_backend.py](file:///C:/Users/Colors/Documents/GitHub/Activision/source/utils/os_windows_backend.py)). Keeping the window visible and un-obscured is necessary.
* **Play in English, 1920x1080:** Coordinate mapping and image-matching models are mathematically calibrated for the default 16:9 English UI layout. Other resolutions or text modifications might lead to misclicks.
* **Disable Game UI Mods:** Mods modifying game speech bubbles, interfaces, or text localization alter the expected screen pixels and will cause OCR/pixel verification failures.

---

## 📜 License & Credits

This project operates under the **GNU General Public License v3.0**. See the `LICENSE` file for details.

* **Modifications & Bridge Integration:** Developed by PhaiKub & Colors (2026). Transitioned to ESP32-S3 physical USB HID emulation, modernized the GUI layouts, and introduced human-like movement profiles.
* **Original Groundwork:** Built upon the automation framework created by [Walpth/Charge-Grinder](https://github.com/Walpth/Charge-Grinder).
