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

## ESP32 Setup (Required for all users)

### Step 1: Install Arduino IDE & Library

1. Install [Arduino IDE](https://www.arduino.cc/en/software)
2. Add ESP32 board support: `File → Preferences → Additional Board URLs`:
   ```
   https://raw.githubusercontent.com/espressif/arduino-esp32/gh-pages/package_esp32_index.json
   ```
3. Install **ESP32-BLE-Combo** library:
   - Download from [GitHub](https://github.com/blackketter/ESP32-BLE-Combo)
   - `Sketch → Include Library → Add .ZIP Library`

### Step 2: Flash ESP32 Firmware

Choose the firmware based on your connection mode:

| Mode | Firmware File | Notes |
|---|---|---|
| **Bluetooth SPP** (Option 1) | `esp32_firmware/esp32_bt_hid_bluetooth.ino` | No WiFi config needed |
| **WiFi TCP** (Option 2) ← Recommended | `esp32_firmware/esp32_bt_hid.ino` | Edit WiFi credentials first |

**If using WiFi (Option 2),** edit WiFi credentials before flashing:
```cpp
const char* WIFI_SSID = "YOUR_WIFI_SSID";
const char* WIFI_PASS = "YOUR_WIFI_PASSWORD";
```

Arduino IDE settings:
- Board: **ESP32 Dev Module**
- Partition Scheme: **Huge APP (3MB No OTA / 1MB SPIFFS)**
- Upload Speed: **921600**

Connect ESP32 via USB and click **Upload**.

**If using WiFi,** check Arduino **Serial Monitor** for the IP address:
```
[WiFi] IP: 192.168.x.x
```
> Note this IP — you'll need it when running the app.

### Step 3: Pair BLE HID with Windows

1. After flashing, the ESP32 appears as **"Activision"** in Windows Bluetooth settings
2. Go to `Settings → Bluetooth & devices → Add device`
3. Pair as a Bluetooth HID device (mouse + keyboard)

---

## Usage (.exe)

Download the `.exe` from [Releases](https://github.com/PhaiKub/Activision/releases/latest).  
Make sure you have completed [ESP32 Setup](#esp32-setup-required-for-all-users) first.

### Option 1: Bluetooth SPP (Simple — no WiFi needed)

1. **Run `App.exe`** — the app will auto-detect ESP32 via Bluetooth
2. If ESP32 is found → the app launches immediately ✅

> No extra configuration needed. Just pair Bluetooth and run the .exe.

### Option 2: WiFi TCP (Faster — requires same network) ← **Recommended**

1. **Run `App.exe`** — if Bluetooth is not found, an IP input dialog will appear
2. Enter the ESP32's IP address (from Serial Monitor) → click OK → connected ✅
3. The IP is saved to `esp32_config.json` — **no need to re-enter next time**

> 💡 To change the IP later, edit `esp32_config.json` next to the .exe:
> ```json
> {
>   "ESP32_HOST": "192.168.1.241"
> }
> ```

### Connection Flow

```
Run App.exe
  │
  ├─ ESP32 found via Bluetooth? ──► YES ──► App launches ✅
  │
  └─ NO
      │
      ├─ esp32_config.json exists? ──► Pre-fills saved IP in input field
      │
      └─ IP Address input dialog appears
           │
           ├─ Enter IP → OK → Connected ──► Save IP + App launches ✅
           ├─ Connection failed ──► Retry / Cancel
           └─ Cancel ──► App closes
```

---

## Usage (Python — for developers)

### Install Python Dependencies

```
pip install -r requirements.txt
```

### Option 1: Bluetooth SPP

```powershell
python App.py
```

> Auto-detects Bluetooth COM port automatically.  
> **Latency:** ~10-50ms

Or specify COM port manually:
```powershell
$env:ESP32_PORT='COM8'; python App.py
```

### Option 2: WiFi TCP ← **Recommended**

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

> 💡 For the .exe version, you don't need to set environment variables — the app will prompt for the IP via GUI or read from `esp32_config.json` automatically. --I think this function still has some problems.

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
├── esp32_config.json               # Saved ESP32 IP (auto-generated, user-specific)
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
| ESP32 not found (Bluetooth) | Ensure ESP32 is paired, try re-pairing |
| ESP32 not found (WiFi) | Verify IP address, ensure ESP32 is on, same WiFi network |
| Connection Failed dialog | Check IP is correct, ESP32 is powered on, try Retry |
| `NOCONN` in logs | BLE HID not paired — re-pair in Windows Bluetooth settings |
| Bot clicks wrong spot | Verify 1920×1080 resolution, ensure window is not scaled |
| Keys not registering | Ensure BLE device is paired as HID (not just Bluetooth audio) |

## License

This project is licensed under the **GNU General Public License v3.0** — see the [LICENSE](LICENSE) file for details.

```
Original work: Copyright (C) AlexWalp
Modified work: Copyright (C) 2026 Colors

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.
```

### Modifications from Original

This is a modified version of [AlexWalp/Mirror-Dungeon-Bot](https://github.com/AlexWalp/Mirror-Dungeon-Bot).  
The following changes were made (2026):

- Replaced software-emulated input (Interception driver / Logitech DLL) with **ESP32 BLE HID**
- Added ESP32 firmware (`esp32_firmware/esp32_bt_hid.ino`) for BLE HID mouse + keyboard
- Added WiFi TCP communication bridge (`esp32_bridge.py`)
- Added GUI WiFi IP input dialog for .exe distribution
- Replaced mouse movement from relative DLL moves to `SetCursorPos` (Windows API)
- Removed Linux/X11 support (Windows-only fork)
- Removed Logitech bridge dependency

---

## Credits

- **Original bot:** [AlexWalp/Mirror-Dungeon-Bot](https://github.com/AlexWalp/Mirror-Dungeon-Bot)
- **BLE HID library:** [ESP32-BLE-Combo](https://github.com/blackketter/ESP32-BLE-Combo) by blackketter
- **ESP32 HID integration:** This fork

---

> My English isn't great, so I used AI to help me translate. Sorry if there are any issues!  
> There may still be some bugs — I plan to fix them in the future and add support for other ESP32 models.
