from .utils import *
import os
import platform

LEGACY_DRIVER_PATHS = [
    r"C:\Windows\System32\drivers\keyboard.sys",
    r"C:\Windows\System32\drivers\mouse.sys",
]


DISCORD_URL = os.environ.get("CHARGEGRINDER_DISCORD_URL", "https://discord.gg/zQ9AnUkf")
CONTACT = "@walpth"


def _get_existing_legacy_driver_paths():
    return [path for path in LEGACY_DRIVER_PATHS if os.path.exists(path)]


def ensure_interception_driver(app_parent=None):
    existing = _get_existing_legacy_driver_paths()
    if not existing:
        return True

    driver_download_url = "https://github.com/AlexWalp/Mirror-Dungeon-Bot/releases/tag/delete-interception"

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
    msg.setWindowTitle("ESP32 Connection Required")
    msg.setText("ESP32 hardware was not detected or failed to connect.")
    msg.setInformativeText(
        "Please ensure your ESP32 is flashed correctly, powered on, and paired via Bluetooth (or WiFi host is set).\n\n"
        "If you need help, please check out the Discord server. "
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


def check_windows(app_parent=None):
    if platform.system() != "Windows":
        return True
    
    if not ensure_interception_driver(app_parent=app_parent):
        return False
    
    if RAISE_ERROR:
        prompt_third_party_software(app_parent=app_parent)
        return False
    return True