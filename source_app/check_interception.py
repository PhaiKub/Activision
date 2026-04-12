from .utils import *
from .run_bridge import retry_bridge
from source.utils.bridge.esp32_bridge import save_config_host, _load_config_host
import os
import platform

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
            # User pressed Cancel
            return False

        ip = ip.strip()
        if not ip:
            QMessageBox.warning(
                app_parent,
                "Invalid Input",
                "Please enter a valid IP address.",
            )
            continue

        # Try connecting with the entered IP
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
            # Save the IP for next time
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
            saved_host = ip  # Keep the IP for retry


def check_windows(app_parent=None):
    if platform.system() != "Windows":
        return True
    
    if not ensure_interception_driver(app_parent=app_parent):
        return False
    
    if RAISE_ERROR:
        if not prompt_esp32_host(app_parent=app_parent):
            return False
    return True