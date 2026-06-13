from .utils import *
import os
import platform
import threading

import source.utils.params as p
from source.utils.paths import APP_VERSION, FIRMWARE_VERSION

LEGACY_DRIVER_PATHS = [
    r"C:\Windows\System32\drivers\keyboard.sys",
    r"C:\Windows\System32\drivers\mouse.sys",
]


DISCORD_URL = os.environ.get("Sorry, I don't have a Discord server.",)
CONTACT = "@phai_kub"


def _get_existing_legacy_driver_paths():
    return [path for path in LEGACY_DRIVER_PATHS if os.path.exists(path)]


def ensure_interception_driver(app_parent=None):
    existing = _get_existing_legacy_driver_paths()
    if not existing:
        return True

    driver_download_url = "https://github.com/Walpth/Charge-Grinder/releases/tag/delete-interception"

    msg = QMessageBox(app_parent)
    msg.setIcon(QMessageBox.Icon.Warning)
    msg.setWindowTitle("Interception Driver Installed")
    msg.setText("Interception driver files were detected. PM will flag your account as suspicious, so Interception must be uninstalled before launching.")
    msg.setInformativeText("Open the Interception releases page (contains uninstaller)?")
    msg.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)

    if msg.exec() == QMessageBox.StandardButton.Yes:
        QMessageBox.information(
            app_parent,
            "Uninstall Interception",
            "A browser page will open. Use the uninstaller, reboot your PC, then relaunch ChargeGrinder."
        )

        try:
            webbrowser.open(driver_download_url)
        except Exception:
            QMessageBox.warning(
                app_parent,
                "Open Browser Failed",
                f"Could not open the browser automatically. Please visit:\n{driver_download_url}"
            )

    return False


def prompt_third_party_software(app_parent=None):
    msg = QMessageBox(app_parent)
    msg.setIcon(QMessageBox.Icon.Critical)
    msg.setWindowTitle("3rd Party Software Required")
    msg.setText("Required 3rd party software was not detected or failed to initialize.")
    msg.setInformativeText(
        "Please check out my Discord server. "
        "If the invite link is expired, contact me directly.\n\n"
        f"Discord: {DISCORD_URL}\n"
        f"Contact: {CONTACT}\n\n"
        "Open the Discord link now?"
    )
    msg.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)

    if msg.exec() == QMessageBox.StandardButton.Yes:
        try:
            webbrowser.open(DISCORD_URL)
        except Exception:
            QMessageBox.warning(
                app_parent,
                "Open Browser Failed",
                "Could not open the Discord link automatically.\n\n"
                f"Please open it manually: {DISCORD_URL}\n"
                f"If expired, contact: {CONTACT}",
            )


# ─────────────────────────────────────────────────────────────
#  ESP32 Scan Dialog
# ─────────────────────────────────────────────────────────────

class ESP32ScanDialog(QWidget):
    """
    Modal-style widget that scans COM ports for the ESP32-S3.

    States
    ------
    scanning  → spinner + live log
    found     → success message, auto-closes after 1 s
    not_found → error + manual COM port entry
    """

    # Signals emitted from the background thread to the main thread
    _sig_log        = pyqtSignal(str)
    _sig_found      = pyqtSignal(str)   # port name
    _sig_failed     = pyqtSignal(str)   # error message
    _sig_flash_log  = pyqtSignal(str)   # flash progress line
    _sig_flash_done = pyqtSignal(bool, str)  # (success, message)
    _sig_version    = pyqtSignal(str)   # "OK:<ver>" or "MISMATCH:<fw>:<app>"

    def __init__(self, parent=None):
        super().__init__(parent, Qt.WindowType.Dialog)
        self.setWindowModality(Qt.WindowModality.ApplicationModal)
        self.setWindowTitle("ESP32-S3 — Connecting")
        self.setFixedSize(460, 420)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)

        self._success = False
        self._build_ui()

        self._sig_log.connect(self._on_log)
        self._sig_found.connect(self._on_found)
        self._sig_failed.connect(self._on_failed)
        self._sig_flash_log.connect(self._on_flash_log)
        self._sig_flash_done.connect(self._on_flash_done)
        self._sig_version.connect(self._on_version_result)

    # ── UI ────────────────────────────────────────────────────

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 16)
        layout.setSpacing(10)

        self._title = QLabel("🔍  Scanning for ESP32-S3…")
        self._title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        font = self._title.font()
        font.setPointSize(11)
        font.setBold(True)
        self._title.setFont(font)
        layout.addWidget(self._title)

        self._log = QLabel("Starting scan…")
        self._log.setWordWrap(True)
        self._log.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self._log.setStyleSheet("color: #aaaaaa; padding: 6px; background: #1a1a1a; border-radius: 4px;")
        self._log.setFixedHeight(72)
        layout.addWidget(self._log)

        # Persistent port-guide hint
        hint = QLabel(
            "<b>ESP32-S3 has 2 USB ports:</b><br>"
            "&nbsp;&nbsp;🔵 <b>USB</b> (Native OTG) &nbsp;&rarr; Connect for running the bot<br>"
            "&nbsp;&nbsp;🟡 <b>COM</b> (UART/CH340) &rarr; Connect for flashing firmware"
        )
        hint.setWordWrap(True)
        hint.setTextFormat(Qt.TextFormat.RichText)
        hint.setStyleSheet(
            "color: #cccccc; font-size: 10px; padding: 6px 8px;"
            "background: #1e1e2e; border: 1px solid #444; border-radius: 4px;"
        )
        layout.addWidget(hint)

        # Manual connect row — USB (Native OTG) port for running the bot
        self._manual_row = QWidget()
        row_layout = QHBoxLayout(self._manual_row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(8)

        row_layout.addWidget(QLabel("🔵 USB port:"))

        self._port_combo = QComboBox()
        self._port_combo.setFixedWidth(110)
        self._port_combo.setEditable(True)
        self._port_combo.lineEdit().setPlaceholderText("Select port")
        row_layout.addWidget(self._port_combo)

        _refresh_usb_btn = QPushButton("🔄")
        _refresh_usb_btn.setFixedWidth(28)
        _refresh_usb_btn.setToolTip("Refresh port list")
        _refresh_usb_btn.clicked.connect(self._refresh_ports)
        row_layout.addWidget(_refresh_usb_btn)

        self._retry_btn = QPushButton("Connect")
        self._retry_btn.setFixedWidth(80)
        self._retry_btn.clicked.connect(self._on_manual_connect)
        row_layout.addWidget(self._retry_btn)

        self._rescan_btn = QPushButton("Re-scan")
        self._rescan_btn.setFixedWidth(80)
        self._rescan_btn.clicked.connect(self._start_scan)
        row_layout.addWidget(self._rescan_btn)

        row_layout.addStretch()
        layout.addWidget(self._manual_row)
        self._manual_row.hide()

        # Flash firmware row (shown when scan fails)
        self._flash_row = QWidget()
        flash_layout = QHBoxLayout(self._flash_row)
        flash_layout.setContentsMargins(0, 0, 0, 0)
        flash_layout.setSpacing(8)

        flash_layout.addWidget(QLabel("🟡 COM port:"))
        self._flash_port_combo = QComboBox()
        self._flash_port_combo.setFixedWidth(110)
        self._flash_port_combo.setEditable(True)
        self._flash_port_combo.lineEdit().setPlaceholderText("Select port")
        flash_layout.addWidget(self._flash_port_combo)

        _refresh_com_btn = QPushButton("🔄")
        _refresh_com_btn.setFixedWidth(28)
        _refresh_com_btn.setToolTip("Refresh port list")
        _refresh_com_btn.clicked.connect(self._refresh_ports)
        flash_layout.addWidget(_refresh_com_btn)

        self._flash_btn = QPushButton("⚡ Flash Firmware")
        self._flash_btn.setFixedWidth(130)
        self._flash_btn.setStyleSheet("color: #ffe066; font-weight: bold;")
        self._flash_btn.clicked.connect(self._on_flash_btn)
        flash_layout.addWidget(self._flash_btn)
        flash_layout.addStretch()

        layout.addWidget(self._flash_row)
        self._flash_row.hide()

        self._status = QLabel("")
        self._status.setWordWrap(True)
        self._status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._status.setStyleSheet("color: #cccccc; font-size: 10px;")
        layout.addWidget(self._status)

    # ── Port helpers ───────────────────────────────────────

    def _refresh_ports(self):
        """Populate both COM-port comboboxes from the current system port list."""
        try:
            from serial.tools.list_ports import comports
            ports = sorted(p.device for p in comports())
        except Exception:
            ports = []

        for combo in (self._port_combo, self._flash_port_combo):
            current = combo.currentText()
            combo.blockSignals(True)
            combo.clear()
            combo.addItems(ports)
            # restore previous selection if still valid
            if current in ports:
                combo.setCurrentText(current)
            elif ports:
                combo.setCurrentIndex(0)
            combo.blockSignals(False)

    # ── Scan logic ────────────────────────────────────────────

    def start(self):
        """Begin scanning. Call show() first."""
        self._start_scan()

    def _start_scan(self):
        self._title.setText("🔍  Scanning for ESP32-S3…")
        self._log.setText("Starting scan…")
        self._log.setStyleSheet("color: #aaaaaa; padding: 6px; background: #1a1a1a; border-radius: 4px;")
        self._status.setText("")
        self._manual_row.hide()
        self._flash_row.hide()
        self._success = False

        t = threading.Thread(target=self._scan_worker, daemon=True)
        t.start()

    def _scan_worker(self):
        from source.utils.bridge.esp32_bridge import ESP32Bridge
        from source.utils.bridge.bridge import BridgeError

        def cb(msg):
            self._sig_log.emit(msg)

        try:
            bridge = ESP32Bridge(port=None, auto_open=False)
            bridge.open(progress_callback=cb)
            # Store the discovered port and the live bridge instance
            p.ESP32_PORT = bridge.get_port()
            from source.utils import os_windows_backend as _be
            with _be._bridge_lock:
                _be._bridge = bridge
            self._sig_found.emit(bridge.get_port())
        except Exception as exc:
            self._sig_failed.emit(str(exc))

    # ── Manual connect ────────────────────────────────────────

    def _on_manual_connect(self):
        port = self._port_combo.currentText().strip()
        if not port:
            self._status.setText("⚠  Enter a COM port first.")
            return
        self._title.setText(f"🔌  Trying {port}…")
        self._log.setText(f"Connecting to {port}…")
        self._log.setStyleSheet("color: #aaaaaa; padding: 6px; background: #1a1a1a; border-radius: 4px;")
        self._manual_row.hide()
        self._success = False

        def worker():
            from source.utils.bridge.esp32_bridge import ESP32Bridge
            from source.utils.bridge.bridge import BridgeError
            try:
                bridge = ESP32Bridge(port=port, auto_open=True)
                p.ESP32_PORT = port
                from source.utils import os_windows_backend as _be
                with _be._bridge_lock:
                    _be._bridge = bridge
                self._sig_found.emit(port)
            except Exception as exc:
                self._sig_failed.emit(str(exc))

        threading.Thread(target=worker, daemon=True).start()

    # ── Signal handlers (main thread) ────────────────────────

    @pyqtSlot(str)
    def _on_log(self, msg):
        self._log.setText(msg)

    @pyqtSlot(str)
    def _on_found(self, port):
        """ESP32 responded to PING — now verify firmware version before closing."""
        self._title.setText(f"🔍  Checking firmware version on {port}…")
        self._log.setText("Querying firmware version…")
        self._log.setStyleSheet("color: #aaaaaa; padding: 6px; background: #1a1a1a; border-radius: 4px;")
        self._status.setText("")
        threading.Thread(target=self._check_firmware_version, daemon=True).start()

    def _check_firmware_version(self):
        """Background: query 'V' from the connected bridge and emit result."""
        try:
            from source.utils import os_windows_backend as _be
            with _be._bridge_lock:
                bridge = _be._bridge
            if bridge is None:
                self._sig_version.emit(f"OK:{FIRMWARE_VERSION}")
                return
            fw_ver = bridge.get_firmware_version()
            if fw_ver is None or fw_ver == FIRMWARE_VERSION:
                self._sig_version.emit(f"OK:{fw_ver or FIRMWARE_VERSION}")
            else:
                self._sig_version.emit(f"MISMATCH:{fw_ver}:{FIRMWARE_VERSION}")
        except Exception as exc:
            # On any error, allow connection to proceed
            import logging
            logging.debug(f"[FirmwareCheck] {exc}")
            self._sig_version.emit(f"OK:{FIRMWARE_VERSION}")

    @pyqtSlot(str)
    def _on_version_result(self, result):
        """Handle firmware version check result on main thread."""
        if result.startswith("OK:"):
            ver = result[3:]
            self._success = True
            self._title.setText(f"✅  Connected — firmware v{ver}")
            self._log.setText(f"ESP32-S3 ready. Firmware version matches.")
            self._log.setStyleSheet("color: #7fffb0; padding: 6px; background: #0d1f14; border-radius: 4px;")
            self._status.setText("Closing automatically…")
            QTimer.singleShot(1000, self.close)
        else:
            # MISMATCH:<fw_ver>:<app_ver>
            parts = result.split(":", 2)
            fw_ver  = parts[1] if len(parts) > 1 else "?"
            app_ver = parts[2] if len(parts) > 2 else "?"
            self._success = False
            self._title.setText("⚠  Firmware Version Mismatch")
            self._log.setText(
                f"Firmware: v{fw_ver}  →  Required: v{app_ver}\n"
                "Please flash the updated firmware before using the bot."
            )
            self._log.setStyleSheet("color: #ffe066; padding: 6px; background: #1a1800; border-radius: 4px;")
            self._refresh_ports()
            self._flash_row.show()
            self._status.setText(
                "Connect the COM (CH340) port and click ⚡ Flash Firmware to update."
            )

    @pyqtSlot(str)
    def _on_failed(self, error):
        self._success = False
        self._title.setText("❌  ESP32-S3 Not Found")
        self._log.setText(error)
        self._log.setStyleSheet("color: #ff7070; padding: 6px; background: #1f0d0d; border-radius: 4px;")
        self._refresh_ports()   # populate dropdowns before showing rows
        self._manual_row.show()
        self._flash_row.show()
        self._status.setText(
            "Plug in USB (Native OTG) and click Re-scan to connect the bot.\n"
            "No firmware yet? Plug in COM (CH340) and click ⚡ Flash Firmware."
        )

    # ── Flash firmware ────────────────────────────────────────

    def _on_flash_btn(self):
        port = self._flash_port_combo.currentText().strip()
        if not port:
            self._status.setText("⚠  Enter the COM port for flashing first.")
            return

        import os, sys
        if getattr(sys, "__compiled__", False):
            base = os.path.dirname(sys.executable)
        else:
            base = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        bin_path = os.path.join(base, "esp32_firmware", "esp32s3_usb_hid.bin")

        if not os.path.isfile(bin_path):
            self._status.setText(
                "❌  Firmware file (.bin) not found.\n"
                "Run: python esp32_firmware/build_firmware.py --merge-only"
            )
            return

        self._flash_btn.setEnabled(False)
        self._title.setText(f"⚡  Flashing firmware to {port}…")
        self._log.setText("Starting esptool…")
        self._log.setStyleSheet("color: #ffe066; padding: 6px; background: #1a1800; border-radius: 4px;")
        self._flash_row.hide()
        self._manual_row.hide()

        t = threading.Thread(target=self._flash_worker, args=(port, bin_path), daemon=True)
        t.start()

    def _flash_worker(self, port: str, bin_path: str):
        import sys, os

        # ── Live-output stream that forwards lines to the UI signal ──────────
        class _Emitter:
            def __init__(self, sig):
                self._sig = sig
                self._buf = ""
            def write(self, text):
                self._buf += text
                while "\n" in self._buf:
                    line, self._buf = self._buf.split("\n", 1)
                    line = line.rstrip("\r")
                    if line:
                        self._sig.emit(line)
            def flush(self):
                pass

        emitter = _Emitter(self._sig_flash_log)
        old_out, old_err = sys.stdout, sys.stderr
        sys.stdout = emitter
        sys.stderr = emitter

        try:
            import esptool  # bundled via --include-package=esptool in nuitka
            self._sig_flash_log.emit(
                f"Flashing {os.path.basename(bin_path)} → {port} (baud 921600)"
            )
            esptool.main([
                "--chip",       "esp32s3",
                "--port",       port,
                "--baud",       "921600",
                "write_flash",
                "--flash_mode", "dio",
                "--flash_freq", "80m",
                "--flash_size", "detect",
                "0x0",          bin_path,
            ])
            # esptool.main() calls sys.exit(0) on success — caught below
            sys.stdout, sys.stderr = old_out, old_err
            self._sig_flash_done.emit(True, port)

        except SystemExit as e:
            sys.stdout, sys.stderr = old_out, old_err
            if e.code == 0 or e.code is None:
                self._sig_flash_done.emit(True, port)
            else:
                self._sig_flash_done.emit(False, f"esptool exited with code {e.code}")

        except ImportError:
            sys.stdout, sys.stderr = old_out, old_err
            self._sig_flash_done.emit(False,
                "esptool module not found.\n"
                "Run:  pip install esptool  then rebuild the app.")

        except Exception as exc:
            sys.stdout, sys.stderr = old_out, old_err
            self._sig_flash_done.emit(False, str(exc))


    @pyqtSlot(str)
    def _on_flash_log(self, line: str):
        self._log.setText(line)

    @pyqtSlot(bool, str)
    def _on_flash_done(self, ok: bool, info: str):
        self._flash_btn.setEnabled(True)
        if ok:
            self._title.setText("✅  Flash complete — rescanning…")
            self._log.setText("Firmware flashed successfully. Waiting for ESP32 to reboot…")
            self._log.setStyleSheet("color: #7fffb0; padding: 6px; background: #0d1f14; border-radius: 4px;")
            # Give ESP32 time to reboot, then rescan
            QTimer.singleShot(3000, self._start_scan)
        else:
            self._title.setText("❌  Flash Failed")
            self._log.setText(info)
            self._log.setStyleSheet("color: #ff7070; padding: 6px; background: #1f0d0d; border-radius: 4px;")
            self._flash_row.show()
            self._status.setText("Check the COM port and try again.")

    def was_successful(self) -> bool:
        return self._success


# ─────────────────────────────────────────────────────────────

def prompt_esp32_scan(app_parent=None) -> bool:
    """
    Show the ESP32 scan dialog and spin the Qt event loop until done.
    Returns True if a device was connected successfully.
    """
    from PySide6.QtWidgets import QApplication

    dialog = ESP32ScanDialog(app_parent)
    dialog.show()
    dialog.start()

    # Spin until dialog closes
    while dialog.isVisible():
        QApplication.processEvents()

    return dialog.was_successful()


def check_windows(app_parent=None):
    if platform.system() != "Windows":
        return True

    if not ensure_interception_driver(app_parent=app_parent):
        return False

    # ESP32 backend: scan for device before anything else
    if p.INPUT_BACKEND == "esp32":
        if not prompt_esp32_scan(app_parent):
            return False
        return True

    if RAISE_ERROR:
        prompt_third_party_software(app_parent=app_parent)
        return False
    return True