"""
ESP32Bridge — Python side of the ESP32-S3 USB HID bridge.

Communicates with the ESP32-S3 over USB Serial (CDC) using the text protocol
defined in esp32s3_usb_hid.ino:

    M dx dy   — relative mouse move
    C btn     — click  (1=left, 2=right, 3=middle)
    D btn     — mouse button down
    U btn     — mouse button up
    S wheel   — scroll
    K code    — key press  (Arduino USBHIDKeyboard value)
    R code    — key release
    A         — release all keys
    P         — ping  → PONG
    Q         — query USB HID status → USB:1 / USB:0
"""

import serial
import serial.tools.list_ports
import sys
import threading
import time
import logging

from source.utils.bridge.bridge import BridgeError


# ── Constants ────────────────────────────────────────────────────────────────

DEFAULT_BAUD     = 115200
PING_TIMEOUT     = 1.5      # seconds to wait for PONG
SCAN_TIMEOUT     = 1.2      # seconds per port while scanning
CMD_TIMEOUT      = 2.0      # seconds to wait for OK/ERR after command
BOOT_DELAY       = 1.5      # seconds to wait after opening (ESP32 resets on DTR)

# Arduino Mouse.move() takes signed 8-bit deltas; larger moves must be split.
HID_MOVE_MAX     = 127

# Minimum time between reconnect attempts. Opening the port resets the board
# (DTR), and a full boot + ping + handshake takes a few seconds — retrying
# faster than that just keeps knocking the board over (see _reconnect).
RECONNECT_COOLDOWN = 3.0


# ── Key code table for Arduino USBHIDKeyboard ─────────────────────────────────
#
# Arduino USBHIDKeyboard.press(uint8_t k) accepts:
#   • Printable ASCII (0x20–0x7E)  → send the ASCII value directly
#   • Special keys defined as KEY_* constants (0x80+) from USBHIDKeyboard.h
#
# These are DIFFERENT from HID usage codes used by the Ghub bridge.dll.

# Arduino USBHIDKeyboard.h special-key constants
_KEY_RETURN      = 0xB0
_KEY_ESC         = 0xB1
_KEY_BACKSPACE   = 0xB2
_KEY_TAB         = 0xB3
_KEY_UP          = 0xDA
_KEY_DOWN        = 0xD9
_KEY_LEFT        = 0xD8
_KEY_RIGHT       = 0xD7
_KEY_INSERT      = 0xD1
_KEY_DELETE      = 0xD4
_KEY_HOME        = 0xD2
_KEY_END         = 0xD5
_KEY_PAGE_UP     = 0xD3
_KEY_PAGE_DOWN   = 0xD6
_KEY_CAPS_LOCK   = 0xC1
_KEY_LEFT_CTRL   = 0x80
_KEY_LEFT_SHIFT  = 0x81
_KEY_LEFT_ALT    = 0x82
_KEY_LEFT_GUI    = 0x83
_KEY_RIGHT_CTRL  = 0x84
_KEY_RIGHT_SHIFT = 0x85
_KEY_RIGHT_ALT   = 0x86
_KEY_RIGHT_GUI   = 0x87
_KEY_F1          = 0xC2
_KEY_F2          = 0xC3
_KEY_F3          = 0xC4
_KEY_F4          = 0xC5
_KEY_F5          = 0xC6
_KEY_F6          = 0xC7
_KEY_F7          = 0xC8
_KEY_F8          = 0xC9
_KEY_F9          = 0xCA
_KEY_F10         = 0xCB
_KEY_F11         = 0xCC
_KEY_F12         = 0xCD

ESP32_KEY_CODES = {
    # ── Letters (ASCII lowercase — Keyboard lib handles shift internally) ──
    **{ch: ord(ch) for ch in "abcdefghijklmnopqrstuvwxyz"},
    # ── Digits ──
    **{str(d): ord(str(d)) for d in range(10)},
    # ── Printable punctuation / symbols (ASCII) ──
    "space":   0x20,
    "-":       ord("-"),
    "equal":   ord("="),
    "[": ord("["), "]": ord("]"),
    "\\": ord("\\"),
    ";": ord(";"),
    "quote":   ord("'"),
    "`":       ord("`"),
    ",":       ord(","),
    ".":       ord("."),
    "/":       ord("/"),
    # ── Special keys ──
    "enter":      _KEY_RETURN,
    "return":     _KEY_RETURN,
    "esc":        _KEY_ESC,
    "escape":     _KEY_ESC,
    "backspace":  _KEY_BACKSPACE,
    "tab":        _KEY_TAB,
    "up":         _KEY_UP,
    "down":       _KEY_DOWN,
    "left":       _KEY_LEFT,
    "right":      _KEY_RIGHT,
    "insert":     _KEY_INSERT,
    "delete":     _KEY_DELETE,
    "del":        _KEY_DELETE,
    "home":       _KEY_HOME,
    "end":        _KEY_END,
    "pageup":     _KEY_PAGE_UP,
    "pgup":       _KEY_PAGE_UP,
    "pagedown":   _KEY_PAGE_DOWN,
    "pgdn":       _KEY_PAGE_DOWN,
    "capslock":   _KEY_CAPS_LOCK,
    # ── Modifiers ──
    "ctrl":       _KEY_LEFT_CTRL,
    "lctrl":      _KEY_LEFT_CTRL,
    "shift":      _KEY_LEFT_SHIFT,
    "lshift":     _KEY_LEFT_SHIFT,
    "alt":        _KEY_LEFT_ALT,
    "lalt":       _KEY_LEFT_ALT,
    "win":        _KEY_LEFT_GUI,
    "lwin":       _KEY_LEFT_GUI,
    "rctrl":      _KEY_RIGHT_CTRL,
    "rshift":     _KEY_RIGHT_SHIFT,
    "ralt":       _KEY_RIGHT_ALT,
    "rwin":       _KEY_RIGHT_GUI,
    # ── Function keys ──
    "f1":  _KEY_F1,  "f2":  _KEY_F2,  "f3":  _KEY_F3,
    "f4":  _KEY_F4,  "f5":  _KEY_F5,  "f6":  _KEY_F6,
    "f7":  _KEY_F7,  "f8":  _KEY_F8,  "f9":  _KEY_F9,
    "f10": _KEY_F10, "f11": _KEY_F11, "f12": _KEY_F12,
}


# ── ESP32Bridge ───────────────────────────────────────────────────────────────

class ESP32Bridge:
    """
    Drop-in replacement for Bridge (Ghub) that routes all HID events through an
    ESP32-S3 connected via USB Serial.

    Usage
    -----
    bridge = ESP32Bridge()          # auto-detect port
    bridge = ESP32Bridge(port="COM5")  # explicit port
    """

    def __init__(self, port=None, baud=DEFAULT_BAUD, auto_open=True):
        self._port   = port     # None → auto-detect on open()
        self._baud   = baud
        self._ser: serial.Serial | None = None
        self._lock   = threading.RLock()
        self._opened = False

        if auto_open:
            self.open()

    # ── Connection ────────────────────────────────────────────────────────────

    def open(self, progress_callback=None):
        """
        Open the serial connection.  If no port was specified at construction,
        scan all available COM ports for a device that replies PONG to P.

        Parameters
        ----------
        progress_callback : callable(str) | None
            Called with status messages during scanning so the UI can display them.
        """
        with self._lock:
            if self._opened:
                return

            if self._port:
                self._connect(self._port)
            else:
                self._auto_detect(progress_callback)

            self._opened = True

    def _connect(self, port):
        try:
            ser = serial.Serial(
                port=port,
                baudrate=self._baud,
                timeout=PING_TIMEOUT,
            )
            time.sleep(BOOT_DELAY)   # ESP32 resets on DTR; give it time to boot
            ser.reset_input_buffer()
            alive = self._ping_serial(ser)
            # A hard-locked board (auth timed out in some earlier session)
            # ignores P but still accepts H, so let the handshake double as
            # the liveness probe instead of failing on the silent ping.
            if not self._handshake_serial(ser):
                ser.close()
                if alive:
                    raise BridgeError(
                        f"Firmware version mismatch on {port}. "
                        "Please flash the updated firmware."
                    )
                raise BridgeError(f"Device on {port} did not respond to PING")
            self._ser  = ser
            self._port = port
            logging.info(f"[ESP32Bridge] Connected on {port}")
        except serial.SerialException as exc:
            raise BridgeError(f"Cannot open {port}: {exc}") from exc

    def _auto_detect(self, progress_callback=None):
        ports = [p.device for p in serial.tools.list_ports.comports()]
        if not ports:
            raise BridgeError("No COM ports found. Is the ESP32-S3 connected?")

        def _cb(msg):
            logging.info(f"[ESP32Bridge] {msg}")
            if progress_callback:
                progress_callback(msg)

        _cb(f"Scanning {len(ports)} port(s): {', '.join(ports)}")

        for port in ports:
            _cb(f"Trying {port}…")
            try:
                ser = serial.Serial(port=port, baudrate=self._baud, timeout=SCAN_TIMEOUT)
                time.sleep(BOOT_DELAY)
                ser.reset_input_buffer()
                if self._ping_serial(ser):
                    if not self._handshake_serial(ser):
                        ser.close()
                        _cb(f"Firmware mismatch on {port} — skipping")
                        raise BridgeError(
                            f"Firmware version mismatch on {port}. "
                            "Please flash the updated firmware."
                        )
                    self._ser  = ser
                    self._port = port
                    _cb(f"Found ESP32-S3 on {port} ✓")
                    return
                ser.close()
            except BridgeError:
                raise
            except (serial.SerialException, OSError):
                pass

        raise BridgeError(
            f"ESP32-S3 not found on any COM port ({', '.join(ports)}). "
            "Check the USB cable and try again."
        )

    @staticmethod
    def _ping_serial(ser: serial.Serial) -> bool:
        try:
            ser.write(b"P\n")
            ser.flush()
            deadline = time.monotonic() + PING_TIMEOUT
            while time.monotonic() < deadline:
                line = ser.readline().decode("ascii", errors="ignore").strip()
                if line == "PONG":
                    return True
            return False
        except Exception:
            return False

    @staticmethod
    def _handshake_serial(ser: serial.Serial) -> bool:
        """Send 'H <FIRMWARE_VERSION>' version handshake and verify AUTH:OK.

        This is a firmware/host version gate, NOT a security check — the
        firmware only unlocks its command set once the versions match so an
        outdated host cannot drive incompatible firmware. Returns True on
        AUTH:OK, False on AUTH:FAIL (firmware enters LED_LOCKED) or timeout.
        """
        try:
            from source.utils.paths import FIRMWARE_VERSION
            cmd = f"H {FIRMWARE_VERSION}\n".encode("ascii")
            ser.write(cmd)
            ser.flush()
            deadline = time.monotonic() + PING_TIMEOUT
            while time.monotonic() < deadline:
                line = ser.readline().decode("ascii", errors="ignore").strip()
                if line == "AUTH:OK":
                    logging.info(f"[ESP32Bridge] Firmware v{FIRMWARE_VERSION} handshake OK")
                    return True
                if line == "AUTH:FAIL":
                    logging.warning("[ESP32Bridge] Firmware version mismatch — AUTH:FAIL")
                    return False
            return False
        except Exception as exc:
            logging.debug(f"[ESP32Bridge] _handshake_serial error: {exc}")
            return False

    def close(self):
        with self._lock:
            if self._ser and self._ser.is_open:
                try:
                    self._ser.close()
                except Exception:
                    pass
            self._opened = False
            self._ser    = None

    def is_open(self) -> bool:
        with self._lock:
            return self._opened and self._ser is not None and self._ser.is_open

    def get_port(self) -> str | None:
        return self._port

    # ── Reconnect ─────────────────────────────────────────────────────────────

    def _reconnect(self) -> bool:
        """Try to re-open the last known port after a transient USB drop.

        Caller must hold self._lock. Returns True if the link is live again.

        Rate-limited: opening the port toggles DTR, which RESETS the board.
        Without a cooldown, an error-recovery loop (e.g. handle_fuckup
        clicking away at a dead link) hammers the board with reset cycles —
        heard as rapid USB connect/disconnect sounds — and it never gets the
        few seconds it needs to boot back up.
        """
        if not self._port:
            return False
        now = time.monotonic()
        if now - getattr(self, "_last_reconnect", 0.0) < RECONNECT_COOLDOWN:
            return False
        self._last_reconnect = now
        # Drop the stale handle before retrying the same port.
        if self._ser is not None:
            try:
                self._ser.close()
            except Exception:
                pass
            self._ser = None
        try:
            logging.info(f"[ESP32Bridge] Attempting reconnect on {self._port}…")
            self._connect(self._port)   # re-pings + re-handshakes
            self._opened = True
            # The board rebooted on reconnect, so its HID state is fresh; make
            # sure no mouse button or key is left latched from the old link.
            try:
                self._write("U 1")
                self._write("U 2")
                self._write("A")
                self._ser.reset_input_buffer()   # discard their OK/LOCKED replies
            except Exception:
                pass
            return True
        except BridgeError as exc:
            logging.warning(f"[ESP32Bridge] Reconnect failed: {exc}")
            return False

    # ── Internal send / receive ───────────────────────────────────────────────

    def _write(self, cmd: str):
        """Write a command line, reconnecting once on a transient serial error."""
        raw = (cmd.strip() + "\n").encode("ascii")
        try:
            self._ser.write(raw)
            self._ser.flush()
        except (serial.SerialException, OSError) as exc:
            logging.warning(f"[ESP32Bridge] Write failed ({exc}); trying reconnect")
            self._opened = False
            if not self._reconnect():
                raise BridgeError(f"Serial link lost while sending {cmd!r}") from exc
            self._ser.write(raw)
            self._ser.flush()

    def _send(self, cmd: str):
        """Send a command line and wait for OK / ERR (auto-reconnect once).

        One retry on delivery problems, because a command line can be lost or
        mangled by CDC RX-overflow framing corruption right after a long move
        stream:
        - ERR reply: D/U/K/R/A/C can never legitimately ERR (the firmware
          only ERRs on an unknown command type), so ERR proves our line was
          corrupted and did NOT execute — safe to resend anything.
        - ACK timeout: the command may or may not have executed, so only
          commands that are safe to repeat are resent: press/release
          (D/U/K/R/A) are idempotent, and a doubled move/scroll step (M/S)
          is corrected by the host's closed-loop positioning. 'C' is not
          retried — a lost-reply-but-executed click would double-click, and
          the bot's own verify logic already handles an unregistered click.
        """
        idempotent = cmd[:1] in ("D", "U", "K", "R", "A", "M", "S")
        with self._lock:
            if not self.is_open() and not self._reconnect():
                raise BridgeError("ESP32Bridge is not connected")
            try:
                for attempt in range(2):
                    self._write(cmd)

                    got_err = False
                    deadline = time.monotonic() + CMD_TIMEOUT
                    while time.monotonic() < deadline:
                        line = self._ser.readline().decode("ascii", errors="ignore").strip()
                        if line == "OK":
                            return
                        if line == "ERR":
                            got_err = True
                            break
                        if line:   # unexpected but non-empty — ignore and keep reading
                            logging.debug(f"[ESP32Bridge] unexpected: {line!r}")
                    # Purge any late/partial reply so it can't be mis-read as
                    # the ACK for the next command (protocol resync).
                    try:
                        self._ser.reset_input_buffer()
                    except Exception:
                        pass
                    if attempt == 0 and (got_err or idempotent):
                        logging.warning(
                            f"[ESP32Bridge] {'ERR for' if got_err else 'No ACK to'} {cmd!r}; retrying once")
                        continue
                    if got_err:
                        raise BridgeError(f"ESP32 returned ERR for command: {cmd!r}")
                    raise BridgeError(f"Timed out waiting for ACK to command: {cmd!r}")
            except BridgeError:
                raise
            except Exception as exc:
                raise BridgeError(f"Serial error sending {cmd!r}: {exc}") from exc

    # ── Key / button helpers ──────────────────────────────────────────────────

    @staticmethod
    def _key_code(key: str) -> int:
        lowered = key.lower()
        if lowered not in ESP32_KEY_CODES:
            raise BridgeError(f"Unsupported key: {key!r}")
        return ESP32_KEY_CODES[lowered]

    @staticmethod
    def _button_code(button: str) -> int:
        lowered = button.lower()
        if lowered == "left":   return 1
        if lowered == "right":  return 2
        if lowered == "middle": return 3
        raise BridgeError(f"Unsupported mouse button: {button!r}")

    # ── Public API (mirrors Bridge) ───────────────────────────────────────────

    def ping(self) -> bool:
        with self._lock:
            if not self.is_open():
                return False
            return self._ping_serial(self._ser)

    def get_firmware_version(self) -> str | None:
        """Query the firmware version via 'V' command.

        Returns the version string (e.g. '3.4.0') or None if the device
        does not respond or the response cannot be parsed.
        """
        with self._lock:
            if not self.is_open():
                return None
            try:
                self._ser.write(b"V\n")
                self._ser.flush()
                deadline = time.monotonic() + PING_TIMEOUT
                while time.monotonic() < deadline:
                    line = self._ser.readline().decode("ascii", errors="ignore").strip()
                    if line.startswith("VER:"):
                        return line[4:]
            except Exception as exc:
                logging.debug(f"[ESP32Bridge] get_firmware_version error: {exc}")
            return None

    def mouse_move_relative(self, dx: int, dy: int):
        # Arduino Mouse.move() deltas are signed 8-bit; split larger moves into
        # multiple steps so big jumps don't overflow/wrap on the firmware side.
        # ACK'd (firmware 3.5.1): the OK round-trip self-clocks the stream so
        # the host can never run ahead of the firmware's tiny RX buffer.
        dx, dy = int(dx), int(dy)
        while dx or dy:
            step_x = max(-HID_MOVE_MAX, min(HID_MOVE_MAX, dx))
            step_y = max(-HID_MOVE_MAX, min(HID_MOVE_MAX, dy))
            self._send(f"M {step_x} {step_y}")
            dx -= step_x
            dy -= step_y

    def mouse_press(self, button="left"):
        self._send(f"D {self._button_code(button)}")

    def mouse_release(self, button="left"):
        self._send(f"U {self._button_code(button)}")

    def mouse_click(self, button="left", delay_ms=30):
        self._send(f"C {self._button_code(button)}")

    def mouse_scroll(self, wheel: int):
        self._send(f"S {int(wheel)}")

    def key_press(self, key: str):
        self._send(f"K {self._key_code(key)}")

    def key_release(self, key: str):
        self._send(f"R {self._key_code(key)}")

    def key_release_all(self):
        self._send("A")

    def key_tap(self, key: str, delay_ms=35):
        code = self._key_code(key)
        self._send(f"K {code}")
        time.sleep(delay_ms / 1000.0)
        self._send(f"R {code}")

    def key_multi_press(self, keys):
        for key in keys:
            self._send(f"K {self._key_code(key)}")
        for key in reversed(keys):
            self._send(f"R {self._key_code(key)}")

    # ── No-ops (Ghub-only features) ───────────────────────────────────────────

    def mouse_settings_apply(self):
        """Disable Windows pointer acceleration for the run (1:1 raw deltas).

        The ESP32 enumerates as a real HID mouse, so its relative deltas DO go
        through Windows "Enhance pointer precision" like any physical mouse —
        the Ghub DLL disabled this in its settings_apply and this backend must
        too. With acceleration left on, the pointer-gain model keeps chasing
        the speed-dependent accel curve, repeating each trajectory many times
        and flooding the serial link with correction traffic. Settings are
        restored by mouse_settings_restore() (called on pause/stop).
        """
        if sys.platform != "win32" or getattr(self, "_saved_mouse", None) is not None:
            return
        import ctypes
        u32 = ctypes.windll.user32
        mouse = (ctypes.c_int * 3)()
        speed = ctypes.c_int()
        if not u32.SystemParametersInfoW(0x0003, 0, ctypes.byref(mouse), 0):    # SPI_GETMOUSE
            return
        u32.SystemParametersInfoW(0x0070, 0, ctypes.byref(speed), 0)            # SPI_GETMOUSESPEED
        self._saved_mouse = (list(mouse), speed.value)
        flat = (ctypes.c_int * 3)(0, 0, 0)                                      # accel off
        u32.SystemParametersInfoW(0x0004, 0, ctypes.byref(flat), 0)             # SPI_SETMOUSE
        u32.SystemParametersInfoW(0x0071, 0, 10, 0)                             # SPI_SETMOUSESPEED → 1:1

    def mouse_settings_restore(self):
        """Restore the Windows pointer settings saved by mouse_settings_apply()."""
        saved = getattr(self, "_saved_mouse", None)
        if saved is None:
            return
        import ctypes
        u32 = ctypes.windll.user32
        mouse_vals, speed_val = saved
        buf = (ctypes.c_int * 3)(*mouse_vals)
        u32.SystemParametersInfoW(0x0004, 0, ctypes.byref(buf), 0)              # SPI_SETMOUSE
        u32.SystemParametersInfoW(0x0071, 0, speed_val, 0)                      # SPI_SETMOUSESPEED
        self._saved_mouse = None

    def shutdown(self, force=False):
        self.close()

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass
