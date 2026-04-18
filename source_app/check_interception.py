from .utils import *
from . import run_bridge as _run_bridge
from .run_bridge import retry_bridge
import source.utils.params as p
import os
import platform


def _get_esp32_config_imports():
    """Lazy import of ESP32 config helpers — only needed for ESP32 BLE mode."""
    from source.utils.bridge.esp32_bridge import save_config_host, _load_config_host
    return save_config_host, _load_config_host




LEGACY_DRIVER_PATHS = [
    r"C:\Windows\System32\drivers\keyboard.sys",
    r"C:\Windows\System32\drivers\mouse.sys",
]


def _get_existing_legacy_driver_paths():
    return [path for path in LEGACY_DRIVER_PATHS if os.path.exists(path)]


def ensure_interception_driver(app_parent=None):
    existing = _get_existing_legacy_driver_paths()
    if not existing:
        return True

    driver_download_url = "https://github.com/PhaiKub/Activision/releases/tag/delete-interception"

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


def prompt_esp32_host(app_parent=None):
    """Show a dialog asking for ESP32 IP address, try to connect, and save on success.
    Returns True if connected successfully, False if user cancelled.
    """
    save_config_host, _load_config_host = _get_esp32_config_imports()
    saved_host = os.environ.get("ESP32_HOST") or _load_config_host() or ""

    while True:
        from PySide6.QtWidgets import QInputDialog

        ip, ok = QInputDialog.getText(
            app_parent,
            "ESP32 WiFi Connection",
            "ESP32 not found via Bluetooth.\n\n"
            "Enter ESP32 IP Address to connect via WiFi:",
            text=saved_host,
        )

        if not ok:
            return False

        ip = ip.strip()
        if not ip:
            QMessageBox.warning(
                app_parent,
                "Invalid Input",
                "Please enter a valid IP address.",
            )
            continue

        msg = QMessageBox(app_parent)
        msg.setIcon(QMessageBox.Icon.Information)
        msg.setWindowTitle("Connecting...")
        msg.setText(f"Trying to connect to {ip}...")
        msg.setStandardButtons(QMessageBox.StandardButton.NoButton)
        msg.show()
        QApplication.processEvents()

        success = retry_bridge(host=ip)
        msg.close()

        if success:
            save_config_host(ip)
            return True
        else:
            ret = QMessageBox.warning(
                app_parent,
                "Connection Failed",
                f"Could not connect to ESP32 at {ip}.\n\n"
                "Please check:\n"
                "• ESP32 is powered on\n"
                "• ESP32 is on the same WiFi network\n"
                "• IP address is correct\n\n"
                "Try again?",
                QMessageBox.StandardButton.Retry | QMessageBox.StandardButton.Cancel,
            )
            if ret == QMessageBox.StandardButton.Cancel:
                return False
            saved_host = ip


def prompt_esp32s3_port(app_parent=None):
    """Show a dialog asking for ESP32-S3 COM port, try to connect, and save on success.
    Returns True if connected successfully, False if user cancelled.
    """
    from source.utils.bridge.esp32s3_bridge import save_config_port, _load_config_port
    saved_port = os.environ.get("ESP32S3_PORT") or _load_config_port() or ""

    while True:
        from PySide6.QtWidgets import QInputDialog

        port, ok = QInputDialog.getText(
            app_parent,
            "ESP32-S3 USB Connection",
            "ESP32-S3 USB device not found automatically.\n\n"
            "Enter COM port (e.g. COM3, COM12):",
            text=saved_port,
        )

        if not ok:
            return False

        port = port.strip().upper()
        if not port:
            QMessageBox.warning(
                app_parent,
                "Invalid Input",
                "Please enter a valid COM port (e.g. COM3).",
            )
            continue

        msg = QMessageBox(app_parent)
        msg.setIcon(QMessageBox.Icon.Information)
        msg.setWindowTitle("Connecting...")
        msg.setText(f"Trying to connect to ESP32-S3 on {port}...")
        msg.setStandardButtons(QMessageBox.StandardButton.NoButton)
        msg.show()
        QApplication.processEvents()

        success = retry_bridge(port=port)
        msg.close()

        if success:
            save_config_port(port)
            return True
        else:
            ret = QMessageBox.warning(
                app_parent,
                "Connection Failed",
                f"Could not connect to ESP32-S3 on {port}.\n\n"
                "Please check:\n"
                "- ESP32-S3 is connected via USB cable\n"
                "- Correct COM port number\n\n"
                "Try again?",
                QMessageBox.StandardButton.Retry | QMessageBox.StandardButton.Cancel,
            )
            if ret == QMessageBox.StandardButton.Cancel:
                return False
            saved_port = port


def check_windows(app_parent=None):
    if platform.system() != "Windows":
        return True
    
    if not ensure_interception_driver(app_parent=app_parent):
        return False
    
    if _run_bridge.RAISE_ERROR:
        if p.BRIDGE_MODE == "esp32s3":
            if not prompt_esp32s3_port(app_parent=app_parent):
                return False
        else:
            if not prompt_esp32_host(app_parent=app_parent):
                return False
    return True