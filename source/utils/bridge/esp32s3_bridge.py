"""
ESP32-S3 USB HID Bridge — USB Serial (CDC)
───────────────────────────────────────────
Connects to ESP32-S3 via USB CDC Serial (COM port).
The ESP32-S3 outputs USB HID mouse + keyboard events.

Custom VID/PID: appears as "Microsoft USB Keyboard" in Device Manager.

Commands (same protocol as ESP32 BLE version):
  M dx dy     — relative mouse move
  C btn       — click (1=left, 2=right, 3=middle)
  D btn       — mouse button down
  U btn       — mouse button up
  S wheel     — scroll
  K code      — key press (Arduino Keyboard code)
  R code      — key release
  A           — release all keys
  P           — ping (returns PONG)
  Q           — query USB HID status
"""

import time
import threading
import os
import json

try:
    import serial
    import serial.tools.list_ports
    HAS_SERIAL = True
except ImportError:
    HAS_SERIAL = False


# ─── Key name → Arduino Keyboard code ────────────────

KEY_CODES = {
    "a": ord("a"), "b": ord("b"), "c": ord("c"), "d": ord("d"),
    "e": ord("e"), "f": ord("f"), "g": ord("g"), "h": ord("h"),
    "i": ord("i"), "j": ord("j"), "k": ord("k"), "l": ord("l"),
    "m": ord("m"), "n": ord("n"), "o": ord("o"), "p": ord("p"),
    "q": ord("q"), "r": ord("r"), "s": ord("s"), "t": ord("t"),
    "u": ord("u"), "v": ord("v"), "w": ord("w"), "x": ord("x"),
    "y": ord("y"), "z": ord("z"),
    "1": ord("1"), "2": ord("2"), "3": ord("3"), "4": ord("4"),
    "5": ord("5"), "6": ord("6"), "7": ord("7"), "8": ord("8"),
    "9": ord("9"), "0": ord("0"),
    " ": ord(" "),
    "-": ord("-"), "=": ord("="),
    "[": ord("["), "]": ord("]"), "\\": ord("\\"),
    ";": ord(";"), "'": ord("'"), "`": ord("`"),
    ",": ord(","), ".": ord("."), "/": ord("/"),
    "enter": 0xB0, "return": 0xB0,
    "esc": 0xB1, "escape": 0xB1,
    "backspace": 0xB2,
    "tab": 0xB3,
    "space": ord(" "),
    "insert": 0xD1, "home": 0xD2,
    "pageup": 0xD3, "pgup": 0xD3,
    "delete": 0xD4, "del": 0xD4,
    "end": 0xD5,
    "pagedown": 0xD6, "pgdn": 0xD6,
    "right": 0xD7, "left": 0xD8, "down": 0xD9, "up": 0xDA,
    "f1": 0xC2, "f2": 0xC3, "f3": 0xC4, "f4": 0xC5,
    "f5": 0xC6, "f6": 0xC7, "f7": 0xC8, "f8": 0xC9,
    "f9": 0xCA, "f10": 0xCB, "f11": 0xCC, "f12": 0xCD,
    "ctrl": 0x80, "lctrl": 0x80,
    "shift": 0x81, "lshift": 0x81,
    "alt": 0x82, "lalt": 0x82,
    "win": 0x83, "lwin": 0x83,
    "rctrl": 0x84, "rshift": 0x85, "ralt": 0x86, "rwin": 0x87,
}

MOUSE_BUTTONS = {"left": 1, "right": 2, "middle": 3}

# ─── USB IDs (match firmware) ────────────────────────

CUSTOM_VID = 0x045E  # Microsoft
CUSTOM_PID = 0x07A5  # Custom keyboard PID
ESPRESSIF_VID = 0x303A  # Fallback: Espressif VID


# ─── Config helpers ──────────────────────────────────

def _config_path():
    if "__compiled__" in globals():
        import sys
        base = os.path.dirname(os.path.abspath(sys.executable))
    else:
        base = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
    return os.path.join(base, "esp32_config.json")


def _load_config_port():
    path = _config_path()
    if os.path.exists(path):
        try:
            with open(path, "r") as f:
                data = json.load(f)
            return data.get("ESP32S3_PORT") or None
        except Exception:
            pass
    return None


def save_config_port(port):
    path = _config_path()
    data = {}
    if os.path.exists(path):
        try:
            with open(path, "r") as f:
                data = json.load(f)
        except Exception:
            pass
    data["ESP32S3_PORT"] = port
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


# ─── Exceptions ──────────────────────────────────────

class ESP32S3BridgeError(RuntimeError):
    pass


# ─── Bridge Class ────────────────────────────────────

class ESP32S3Bridge:
    """ESP32-S3 USB HID Bridge — USB Serial (CDC) mode.

    Connects to ESP32-S3 via USB CDC Serial (COM port).
    The ESP32-S3 outputs USB HID mouse + keyboard events.
    """

    BAUD_RATE = 115200

    def __init__(self, port=None, auto_open=True, **kwargs):
        self._serial = None
        self._port = (port
                      or os.environ.get("ESP32S3_PORT")
                      or _load_config_port())
        self._lock = threading.Lock()
        self._opened = False

        if auto_open:
            self.open()

    # ─── Connection ───────────────────────────────────

    def open(self):
        if self._opened:
            return

        if not HAS_SERIAL:
            raise ESP32S3BridgeError(
                "pyserial not installed.\nInstall with: pip install pyserial"
            )

        if not self._port:
            self._port = self._find_esp32s3_port()
            if not self._port:
                raise ESP32S3BridgeError(
                    "ESP32-S3 USB device not found!\n"
                    "Make sure ESP32-S3 is connected via USB cable.\n"
                    "Set ESP32S3_PORT=COMx if auto-detect fails."
                )

        self._open_serial()

    def _open_serial(self):
        s = self._try_open_serial(self._port, self.BAUD_RATE, timeout_sec=5)
        if s is None:
            raise ESP32S3BridgeError(
                f"Cannot open {self._port} (timeout or permission error)"
            )
        self._serial = s

        time.sleep(1)
        self._serial.reset_input_buffer()

        resp = ""
        for _attempt in range(5):
            self._send_raw("P")
            time.sleep(0.3)
            resp = (self._serial.readline()
                    .decode("utf-8", errors="replace").strip())
            if "PONG" in resp:
                break
            self._serial.reset_input_buffer()
            time.sleep(0.5)
        else:
            self._serial.close()
            raise ESP32S3BridgeError(
                f"ESP32-S3 on {self._port} did not respond (got: '{resp}')"
            )

        self._opened = True
        save_config_port(self._port)
        print(f"[ESP32S3Bridge] Connected via USB Serial on {self._port}")

    @staticmethod
    def _try_open_serial(port, baud, timeout_sec=4):
        result = {"serial": None, "error": None}
        def _open():
            try:
                result["serial"] = serial.Serial(port, baud, timeout=2)
            except Exception as e:
                result["error"] = e
        t = threading.Thread(target=_open, daemon=True)
        t.start()
        t.join(timeout=timeout_sec)
        if t.is_alive():
            return None
        if result["error"]:
            return None
        return result["serial"]

    @staticmethod
    def _find_esp32s3_port():
        if not HAS_SERIAL:
            return None

        for p in serial.tools.list_ports.comports():
            vid = getattr(p, 'vid', None)
            pid = getattr(p, 'pid', None)
            desc = (p.description or "").lower()
            mfr = (getattr(p, 'manufacturer', '') or "").lower()

            is_target = (
                vid == ESPRESSIF_VID
                or (vid == CUSTOM_VID and pid == CUSTOM_PID)
                or "esp32" in desc
                or "espressif" in mfr
            )
            if not is_target:
                continue

            s = ESP32S3Bridge._try_open_serial(p.device, 115200, timeout_sec=3)
            if s is None:
                continue
            try:
                time.sleep(1)
                s.reset_input_buffer()
                s.write(b"P\n")
                s.flush()
                time.sleep(0.5)
                resp = (s.readline()
                        .decode("utf-8", errors="replace").strip())
                s.close()
                if "PONG" in resp:
                    return p.device
            except Exception:
                try:
                    s.close()
                except Exception:
                    pass
        return None

    # ─── Lifecycle ────────────────────────────────────

    def close(self):
        if self._serial and self._serial.is_open:
            try:
                self._serial.close()
            except Exception:
                pass
            self._serial = None
        self._opened = False

    def is_open(self):
        return self._opened and self._serial is not None and self._serial.is_open

    def shutdown(self, force=False):
        self.close()

    # ─── Internal I/O ─────────────────────────────────

    MAX_RECONNECT = 3

    def _reconnect(self):
        print(f"[ESP32S3Bridge] Reconnecting to {self._port}...")
        try:
            if self._serial:
                self._serial.close()
        except Exception:
            pass
        self._serial = None
        self._opened = False

        for attempt in range(self.MAX_RECONNECT):
            time.sleep(0.5 * (attempt + 1))
            try:
                s = serial.Serial(self._port, self.BAUD_RATE, timeout=2)
                time.sleep(0.3)
                s.reset_input_buffer()
                s.write(b"P\n")
                s.flush()
                time.sleep(0.3)
                resp = s.readline().decode("utf-8", errors="replace").strip()
                if "PONG" in resp:
                    self._serial = s
                    self._opened = True
                    print(f"[ESP32S3Bridge] Reconnected (attempt {attempt + 1})")
                    return True
                s.close()
            except Exception as e:
                print(f"[ESP32S3Bridge] Reconnect attempt {attempt + 1} failed: {e}")
        print("[ESP32S3Bridge] All reconnect attempts failed")
        return False

    def _send_raw(self, cmd):
        data = f"{cmd}\n".encode("utf-8")
        if not self._serial or not self._serial.is_open:
            return
        try:
            self._serial.write(data)
            self._serial.flush()
        except (serial.SerialException, PermissionError, OSError):
            if self._reconnect():
                try:
                    self._serial.write(data)
                    self._serial.flush()
                except Exception:
                    pass

    def _read_response(self, timeout=0.5):
        if not self._serial or not self._serial.is_open:
            return ""
        old_timeout = self._serial.timeout
        self._serial.timeout = timeout
        try:
            return (self._serial.readline()
                    .decode("utf-8", errors="replace").strip())
        except (serial.SerialException, PermissionError, OSError):
            if self._reconnect():
                return ""
            return ""
        except Exception:
            return ""
        finally:
            try:
                if self._serial:
                    self._serial.timeout = old_timeout
            except Exception:
                pass

    def _send(self, cmd, wait_ack=False):
        with self._lock:
            self._send_raw(cmd)
            if wait_ack:
                self._read_response(timeout=0.5)

    @staticmethod
    def _key_code(key):
        lowered = key.lower()
        if lowered not in KEY_CODES:
            raise ESP32S3BridgeError(f"Unsupported key: {key}")
        return KEY_CODES[lowered]

    @staticmethod
    def _button_code(button):
        lowered = button.lower()
        if lowered not in MOUSE_BUTTONS:
            raise ESP32S3BridgeError(f"Unsupported mouse button: {button}")
        return MOUSE_BUTTONS[lowered]

    # ─── Mouse ────────────────────────────────────────

    def mouse_move_relative(self, dx, dy):
        dx, dy = int(dx), int(dy)
        while dx != 0 or dy != 0:
            sx = max(-127, min(127, dx))
            sy = max(-127, min(127, dy))
            self._send(f"M {sx} {sy}", wait_ack=False)
            dx -= sx
            dy -= sy
            time.sleep(0.005)

    def mouse_press(self, button="left"):
        self._send(f"D {self._button_code(button)}", wait_ack=False)

    def mouse_release(self, button="left"):
        self._send(f"U {self._button_code(button)}", wait_ack=False)

    def mouse_click(self, button="left", delay_ms=30):
        self._send(f"C {self._button_code(button)}", wait_ack=False)

    def mouse_scroll(self, wheel):
        self._send(f"S {int(wheel)}", wait_ack=False)

    # ─── Keyboard ─────────────────────────────────────

    def key_press(self, key):
        self._send(f"K {self._key_code(key)}", wait_ack=False)

    def key_release_all(self):
        self._send("A", wait_ack=False)

    def key_tap(self, key, delay_ms=35):
        self.key_press(key)
        time.sleep(delay_ms / 1000.0)
        self.key_release_all()

    def key_multi_press(self, keys):
        for key in keys:
            self.key_press(key)
        time.sleep(0.02)
        self.key_release_all()
