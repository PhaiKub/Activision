"""
ESP32 BLE HID Bridge — Dual Mode (WiFi TCP / Bluetooth SPP)
────────────────────────────────────────────────────────────
Supports both connection modes:
  - WiFi TCP  (set ESP32_HOST)  → ~1-5ms latency
  - Bluetooth SPP (set ESP32_PORT) → ~10-50ms latency

Auto-detect: if ESP32_HOST is set → WiFi, else try Bluetooth SPP

Commands:
  M dx dy     — relative mouse move
  C btn       — click (1=left, 2=right, 3=middle)
  D btn       — mouse button down
  U btn       — mouse button up
  S wheel     — scroll
  K code      — key press (Arduino ASCII/special code)
  R code      — key release
  A           — release all keys
  P           — ping (returns PONG)
  Q           — query BLE status
"""

import socket
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


def _config_path():
    """Path to esp32_config.json next to the executable / project root."""
    if "__compiled__" in globals():
        import sys
        base = os.path.dirname(os.path.abspath(sys.executable))
    else:
        base = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
    return os.path.join(base, "esp32_config.json")


def _load_config_host():
    """Load saved ESP32_HOST from esp32_config.json (returns None if not found)."""
    path = _config_path()
    if os.path.exists(path):
        try:
            with open(path, "r") as f:
                data = json.load(f)
            return data.get("ESP32_HOST") or None
        except Exception:
            pass
    return None


def save_config_host(host):
    """Save ESP32_HOST to esp32_config.json next to the executable."""
    path = _config_path()
    data = {}
    if os.path.exists(path):
        try:
            with open(path, "r") as f:
                data = json.load(f)
        except Exception:
            pass
    data["ESP32_HOST"] = host
    with open(path, "w") as f:
        json.dump(data, f, indent=2)

# ─── Key name → Arduino Keyboard code ────────────────

# Arduino Keyboard library: printable keys use ASCII, special keys use 0x80+ constants
KEY_CODES = {
    # Printable — ASCII values
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
    # Special keys — Arduino Keyboard library constants
    "enter": 0xB0, "return": 0xB0,
    "esc": 0xB1, "escape": 0xB1,
    "backspace": 0xB2,
    "tab": 0xB3,
    "space": ord(" "),  # ASCII space = 32
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


class ESP32BridgeError(RuntimeError):
    pass


class ESP32Bridge:
    """
    ESP32 BLE HID Bridge — Dual Mode.
    - WiFi TCP: set ESP32_HOST env var
    - Bluetooth SPP: set ESP32_PORT env var (e.g. COM8)
    """

    BAUD_RATE = 115200
    DEFAULT_TCP_PORT = 8266

    def __init__(self, port=None, host=None, auto_open=True, **kwargs):
        self._socket = None    # WiFi TCP
        self._serial = None    # Bluetooth SPP
        self._mode = None      # "wifi" or "bluetooth"
        self._host = host or os.environ.get("ESP32_HOST", None) or _load_config_host()
        self._port = port or os.environ.get("ESP32_PORT", None)
        self._tcp_port = int(os.environ.get("ESP32_TCP_PORT", self.DEFAULT_TCP_PORT))
        self._lock = threading.Lock()
        self._opened = False
        self._recv_buf = b""
        if auto_open:
            self.open()

    # ─── Connection ───────────────────────────────────

    def open(self):
        if self._opened:
            return

        # Priority: WiFi > Bluetooth
        if self._host:
            self._open_wifi()
        elif self._port:
            self._open_bluetooth()
        else:
            # Auto-detect: try Bluetooth first (find COM port)
            if HAS_SERIAL:
                port = self._find_bt_port()
                if port:
                    self._port = port
                    self._open_bluetooth()
                    return
            raise ESP32BridgeError(
                "ESP32 not found!\n"
                "Set ESP32_HOST=<ip> for WiFi or ESP32_PORT=<COM> for Bluetooth"
            )

    def _open_wifi(self):
        """Connect via WiFi TCP."""
        sock = self._try_connect(self._host, self._tcp_port)
        if sock is None:
            raise ESP32BridgeError(f"Cannot connect to {self._host}:{self._tcp_port}")
        self._socket = sock

        time.sleep(1)
        self._recv_buf = b""
        self._mode = "wifi"  # set mode before _send/_read

        for attempt in range(5):
            self._send_raw("P")
            time.sleep(0.3)
            resp = self._read_response(timeout=2.0)
            if "PONG" in resp:
                break
            time.sleep(0.5)
        else:
            self._mode = None
            self._socket.close()
            raise ESP32BridgeError(f"ESP32 at {self._host}:{self._tcp_port} did not respond")

        self._mode = "wifi"
        self._opened = True
        print(f"[ESP32Bridge] Connected via WiFi TCP to {self._host}:{self._tcp_port}")

    def _open_bluetooth(self):
        """Connect via Bluetooth SPP (Serial)."""
        if not HAS_SERIAL:
            raise ESP32BridgeError("pyserial not installed — cannot use Bluetooth SPP")

        s = self._try_open_serial(self._port, self.BAUD_RATE, timeout_sec=5)
        if s is None:
            raise ESP32BridgeError(f"Cannot open {self._port} (timeout or permission error)")
        self._serial = s

        time.sleep(3)  # ESP32 resets on serial open
        self._serial.reset_input_buffer()

        for attempt in range(3):
            self._send_raw("P")
            time.sleep(0.3)
            resp = self._serial.readline().decode("utf-8", errors="replace").strip()
            if "PONG" in resp:
                break
            self._serial.reset_input_buffer()
            time.sleep(0.5)
        else:
            self._serial.close()
            raise ESP32BridgeError(f"ESP32 on {self._port} did not respond (got: '{resp}')")

        self._mode = "bluetooth"
        self._opened = True
        print(f"[ESP32Bridge] Connected via Bluetooth SPP on {self._port}")

    @staticmethod
    def _try_connect(host, port, timeout=3):
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(timeout)
            sock.connect((host, port))
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            return sock
        except Exception:
            return None

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
    def _find_bt_port():
        """Auto-detect ESP32 Bluetooth COM port."""
        if not HAS_SERIAL:
            return None
        for p in serial.tools.list_ports.comports():
            desc = (p.description or "").lower()
            hwid = (p.hwid or "").upper()
            if "bluetooth" in desc or "BTHENUM" in hwid:
                s = ESP32Bridge._try_open_serial(p.device, 115200, timeout_sec=5)
                if s is None:
                    continue
                try:
                    time.sleep(2)
                    s.reset_input_buffer()
                    s.write(b"P\n")
                    s.flush()
                    time.sleep(0.5)
                    resp = s.readline().decode("utf-8", errors="replace").strip()
                    s.close()
                    if "PONG" in resp:
                        return p.device
                except Exception:
                    try: s.close()
                    except: pass
        return None

    def close(self):
        if self._socket:
            try: self._socket.close()
            except: pass
            self._socket = None
        if self._serial and self._serial.is_open:
            try: self._serial.close()
            except: pass
            self._serial = None
        self._opened = False

    def is_open(self):
        if self._mode == "wifi":
            return self._opened and self._socket is not None
        else:
            return self._opened and self._serial is not None and self._serial.is_open

    def shutdown(self, force=False):
        self.close()

    # ─── Internal ─────────────────────────────────────

    def _send_raw(self, cmd):
        data = f"{cmd}\n".encode("utf-8")
        if self._mode == "wifi" and self._socket:
            try: self._socket.sendall(data)
            except: pass
        elif self._mode == "bluetooth" and self._serial and self._serial.is_open:
            self._serial.write(data)
            self._serial.flush()

    def _read_response(self, timeout=0.5):
        if self._mode == "wifi":
            return self._read_wifi(timeout)
        else:
            return self._read_serial(timeout)

    def _read_wifi(self, timeout=0.5):
        if not self._socket:
            return ""
        old_timeout = self._socket.gettimeout()
        self._socket.settimeout(timeout)
        try:
            while True:
                idx = self._recv_buf.find(b"\n")
                if idx >= 0:
                    line = self._recv_buf[:idx].decode("utf-8", errors="replace").strip()
                    self._recv_buf = self._recv_buf[idx+1:]
                    return line
                chunk = self._socket.recv(256)
                if not chunk:
                    return ""
                self._recv_buf += chunk
        except socket.timeout:
            return ""
        except Exception:
            return ""
        finally:
            self._socket.settimeout(old_timeout)

    def _read_serial(self, timeout=0.5):
        if not self._serial or not self._serial.is_open:
            return ""
        old_timeout = self._serial.timeout
        self._serial.timeout = timeout
        try:
            return self._serial.readline().decode("utf-8", errors="replace").strip()
        except Exception:
            return ""
        finally:
            self._serial.timeout = old_timeout

    def _send(self, cmd, wait_ack=True):
        with self._lock:
            self._send_raw(cmd)
            if wait_ack:
                self._read_response(timeout=0.5)

    @staticmethod
    def _key_code(key):
        lowered = key.lower()
        if lowered not in KEY_CODES:
            raise ESP32BridgeError(f"Unsupported key: {key}")
        return KEY_CODES[lowered]

    @staticmethod
    def _button_code(button):
        lowered = button.lower()
        if lowered not in MOUSE_BUTTONS:
            raise ESP32BridgeError(f"Unsupported mouse button: {button}")
        return MOUSE_BUTTONS[lowered]

    # ─── Mouse (via ESP32 BLE HID) ───────────────────

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
        self._send(f"D {self._button_code(button)}")

    def mouse_release(self, button="left"):
        self._send(f"U {self._button_code(button)}")

    def mouse_click(self, button="left", delay_ms=30):
        self._send(f"C {self._button_code(button)}")

    def mouse_scroll(self, wheel):
        self._send(f"S {int(wheel)}")

    # ─── Keyboard (via ESP32 BLE HID) ────────────────

    def key_press(self, key):
        self._send(f"K {self._key_code(key)}")

    def key_release_all(self):
        self._send("A")

    def key_tap(self, key, delay_ms=35):
        self.key_press(key)
        time.sleep(delay_ms / 1000.0)
        self.key_release_all()

    def key_multi_press(self, keys):
        for key in keys:
            self.key_press(key)
        time.sleep(0.02)
        self.key_release_all()
