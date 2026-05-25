from .utils import *
import os
import platform
import threading

import source.utils.params as p

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
    _sig_log    = pyqtSignal(str)
    _sig_found  = pyqtSignal(str)   # port name
    _sig_failed = pyqtSignal(str)   # error message

    def __init__(self, parent=None):
        super().__init__(parent, Qt.WindowType.Dialog)
        self.setWindowModality(Qt.WindowModality.ApplicationModal)
        self.setWindowTitle("ESP32-S3 — Connecting")
        self.setFixedSize(440, 290)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)

        self._success = False
        self._build_ui()

        self._sig_log.connect(self._on_log)
        self._sig_found.connect(self._on_found)
        self._sig_failed.connect(self._on_failed)

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
        self._log.setFixedHeight(90)
        layout.addWidget(self._log)

        # Manual port row (hidden while scanning)
        self._manual_row = QWidget()
        row_layout = QHBoxLayout(self._manual_row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(8)

        row_layout.addWidget(QLabel("COM port:"))

        self._port_input = QLineEdit()
        self._port_input.setPlaceholderText("e.g. COM5")
        self._port_input.setFixedWidth(90)
        row_layout.addWidget(self._port_input)

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

        self._status = QLabel("")
        self._status.setWordWrap(True)
        self._status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._status.setStyleSheet("color: #cccccc; font-size: 10px;")
        layout.addWidget(self._status)

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
        port = self._port_input.text().strip()
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
        self._success = True
        self._title.setText(f"✅  Connected on {port}")
        self._log.setText(f"ESP32-S3 found and ready on {port}.")
        self._log.setStyleSheet("color: #7fffb0; padding: 6px; background: #0d1f14; border-radius: 4px;")
        self._status.setText("Closing automatically…")
        QTimer.singleShot(1000, self.close)

    @pyqtSlot(str)
    def _on_failed(self, error):
        self._success = False
        self._title.setText("❌  ESP32-S3 Not Found")
        self._log.setText(error)
        self._log.setStyleSheet("color: #ff7070; padding: 6px; background: #1f0d0d; border-radius: 4px;")
        self._manual_row.show()
        self._status.setText("Plug in the ESP32-S3 and click Re-scan,\nor enter the COM port manually.")

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