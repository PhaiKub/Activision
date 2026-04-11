# Mirror Dungeon Bot — ESP32 BLE HID Edition

> **Fork of [AlexWalp/Mirror-Dungeon-Bot](https://github.com/AlexWalp/Mirror-Dungeon-Bot)**  
> Modified to use **ESP32 BLE HID** for hardware-level mouse & keyboard input

A Limbus Company bot that grinds Mirror Dungeon automatically.  
This fork replaces software-emulated input with real Bluetooth HID input via an **ESP32 WROOM-32U**, making actions appear as genuine hardware input.

---

## What's Different from Original?

| | Original | This Fork |
|---|---|---|
| **Input Method** | Interception driver / software emulation | ESP32 BLE HID (hardware) |
| **Mouse Movement** | Relative mouse moves via DLL | `SetCursorPos` + BLE HID clicks |
| **Keyboard** | Software key injection | BLE HID keyboard |
| **Connection** | USB / Driver | Bluetooth SPP or WiFi TCP |

---

## Hardware Required

- **ESP32 WROOM-32U** (recommended — tested and fully working)
- USB Micro-B cable (for firmware upload)
- PC with Bluetooth & Windows 10/11

### Supported ESP32 Models

| Model | BLE HID | Bluetooth SPP | WiFi | Option 1 | Option 2 | Status |
|---|---|---|---|---|---|---|
| **ESP32 WROOM-32/32U** | ✅ | ✅ | ✅ | ✅ | ✅ | **Tested ✅** |
| **ESP32 WROVER** | ✅ | ✅ | ✅ | ✅ | ✅ | Should work |
| **ESP32-S3** | ✅ | ❌ | ✅ | ❌ | ⚠️ | Untested |
| **ESP32-C3** | ✅ | ❌ | ✅ | ❌ | ⚠️ | Untested |
| **ESP32-S2** | ❌ | ❌ | ✅ | ❌ | ❌ | **Not supported** |
| **ESP32-H2** | ✅ | ❌ | ❌ | ❌ | ❌ | **Not supported** |

> ⚠️ ESP32-S3/C3 have BLE + WiFi but the `ESP32-BLE-Combo` library may need modifications.  
> **Recommended:** Use **ESP32 WROOM-32U** for guaranteed compatibility.

---

## Software & Libraries

### Python (PC side)
| Package | Purpose |
|---|---|
| `opencv-python-headless` | Image detection / screenshot analysis |
| `numpy` | Image processing |
| `PySide6` | GUI interface |
| `pathgenerator` | Mouse path generation |
| `pyserial` | Bluetooth SPP serial communication |

### Arduino (ESP32 firmware)
| Library | Purpose |
|---|---|
| [ESP32-BLE-Combo](https://github.com/blackketter/ESP32-BLE-Combo) | Unified BLE Mouse + Keyboard HID |
| `WiFi.h` | WiFi TCP server (built-in) |

---

## Installation

### Step 1: Install Python Dependencies

```
pip install -r requirements.txt
```

### Step 2: Install Arduino IDE & Library

1. Install [Arduino IDE](https://www.arduino.cc/en/software)
2. Add ESP32 board support: `File → Preferences → Additional Board URLs`:
   ```
   https://raw.githubusercontent.com/espressif/arduino-esp32/gh-pages/package_esp32_index.json
   ```
3. Install **ESP32-BLE-Combo** library:
   - Download from [GitHub](https://github.com/blackketter/ESP32-BLE-Combo)
   - `Sketch → Include Library → Add .ZIP Library`

### Step 3: Flash ESP32 Firmware

1. Open `esp32_firmware/esp32_bt_hid.ino` in Arduino IDE
2. **If using WiFi (Option 2):** edit WiFi credentials:
   ```cpp
   const char* WIFI_SSID = "YOUR_WIFI_SSID";
   const char* WIFI_PASS = "YOUR_WIFI_PASSWORD";
   ```
3. Arduino IDE settings:
   - Board: **ESP32 Dev Module**
   - Partition Scheme: **Huge APP (3MB No OTA / 1MB SPIFFS)**
   - Upload Speed: **921600**
4. Connect ESP32 via USB and click **Upload**

### Step 4: Pair BLE HID with Windows

1. After flashing, the ESP32 appears as **"Activision"** in Windows Bluetooth settings
2. Go to `Settings → Bluetooth & devices → Add device`
3. Pair as a Bluetooth HID device (mouse + keyboard)

---

## Usage

### 📡 Option 1: Bluetooth SPP (Simple — no WiFi needed)

Uses Bluetooth Serial to communicate. No WiFi setup required.

**Firmware:** `esp32_firmware/esp32_bt_hid_bluetooth.ino.bak` (rename to `.ino` and flash)

```powershell
$env:ESP32_PORT='COM8'; python App.py
```

> **Latency:** ~10-50ms  
> Find COM port in `Device Manager → Ports (COM & LPT)`  
> Look for "Standard Serial over Bluetooth link" or similar

---

### ⚡ Option 2: WiFi TCP (Faster — requires same network) ← **Recommended**

Uses WiFi TCP for lower latency. ESP32 and PC must be on the same network.

**Firmware:** `esp32_firmware/esp32_bt_hid.ino` (default, already included)

After flashing with WiFi credentials, check Arduino **Serial Monitor** for:
```
[WiFi] IP: 192.168.x.x
```

```powershell
$env:ESP32_HOST='192.168.x.x'; python App.py
```

> **Latency:** ~10-15ms

---

## Environment Variables

| Variable | Mode | Description | Example |
|---|---|---|---|
| `ESP32_PORT` | Bluetooth | COM port for SPP connection | `COM8` |
| `ESP32_HOST` | WiFi | ESP32's IP address | `192.168.1.100` |
| `ESP32_TCP_PORT` | WiFi | TCP port (default: 8266) | `8266` |

---

## Testing & Diagnostics

```powershell
# Continuous ping test (Bluetooth)
$env:ESP32_PORT='COM8'; python testping_esp32.py

# Continuous ping test (WiFi)
$env:ESP32_HOST='192.168.x.x'; python testping_esp32.py

# Keyboard & mouse test
$env:ESP32_PORT='COM8'; python test_esp32.py
```

---

## Architecture

```
┌──────────┐   WiFi TCP / BT SPP   ┌──────────┐   BLE HID    ┌─────────┐
│  Python  │ ────────────────────►  │  ESP32   │ ──────────►  │ Windows │
│  (Bot)   │     commands           │ (Bridge) │  mouse/kbd   │ (Game)  │
└──────────┘                        └──────────┘              └─────────┘
```

- **Cursor movement:** `SetCursorPos` (Windows API) — pixel-perfect precision
- **Mouse clicks:** ESP32 BLE HID `Mouse.press()` / `Mouse.release()`
- **Keyboard:** ESP32 BLE HID `Keyboard.press()` — uses Arduino ASCII keycodes

---

## File Structure

```
Mirror-Dungeon-Bot/
├── App.py                          # Main entry point
├── esp32_firmware/
│   └── esp32_bt_hid.ino            # ESP32 firmware (WiFi + BLE HID)
├── source/utils/
│   ├── bridge/
│   │   └── esp32_bridge.py         # Python ↔ ESP32 bridge (WiFi TCP & Bluetooth SPP)
│   └── os_windows_backend.py       # Mouse/keyboard input using ESP32
├── testping_esp32.py               # Ping latency test
├── test_esp32.py                   # Keyboard/mouse test
└── requirements.txt                # Python dependencies
```

---

## Game Settings

- **Language:** English
- **Resolution:** 16:9 ratio (1920×1080 recommended, 1280×720 also works)
- **HDR:** Disabled
- **No mods** (e.g. speech bubbles)
- **Window must be fully visible** — do not minimize or cover

---

## Troubleshooting

| Problem | Solution |
|---|---|
| `Cannot open COM8` | Close other apps using the port, re-pair Bluetooth |
| `ESP32 not found` | Check `ESP32_PORT` or `ESP32_HOST` env var |
| `NOCONN` in logs | BLE HID not paired — re-pair in Windows Bluetooth settings |
| Bot clicks wrong spot | Verify 1920×1080 resolution, ensure window is not scaled |
| Keys not registering | Ensure BLE device is paired as HID (not just Bluetooth audio) |

---

## Credits

- **Original bot:** [AlexWalp/Mirror-Dungeon-Bot](https://github.com/AlexWalp/Mirror-Dungeon-Bot)
- **BLE HID library:** [ESP32-BLE-Combo](https://github.com/blackketter/ESP32-BLE-Combo) by blackketter
- **ESP32 HID integration:** This fork

---

> My English isn't great, so I used AI to help me translate. Sorry if there are any issues!  
> There may still be some bugs — I plan to fix them in the future and add support for other ESP32 models.
