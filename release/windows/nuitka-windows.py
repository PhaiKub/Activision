import os
import subprocess
import sys


ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
ENTRY = os.path.join(ROOT_DIR, "App.py")


def _cmd(output_name: str, console_mode: str):
    return [
        sys.executable,
        "-m",
        "nuitka",
        "--onefile",
        "--enable-plugin=pyside6",
        "--assume-yes-for-downloads",
        f"--output-dir={os.path.join(ROOT_DIR, 'build')}",
        f"--output-filename={output_name}",
        f"--windows-console-mode={console_mode}",
        f"--windows-icon-from-ico={os.path.join(ROOT_DIR, 'app_icon.ico')}",
        f"--include-data-dir={os.path.join(ROOT_DIR, 'ImageAssets', 'UI')}=ImageAssets/UI",
        f"--include-data-dir={os.path.join(ROOT_DIR, 'ImageAssets', 'AppUI')}=ImageAssets/AppUI",
        f"--include-data-files={os.path.join(ROOT_DIR, 'app_icon.ico')}=app_icon.ico",
        f"--include-data-files={os.path.join(ROOT_DIR, 'source', 'utils', 'bridge', 'bridge.dll')}=bridge_assets/bridge.dll",
        ENTRY,
    ]


def build_one(output_name: str, console_mode: str):
    cmd = _cmd(output_name, console_mode)
    print("Building with:", " ".join(cmd))
    subprocess.run(cmd, check=True, cwd=ROOT_DIR)


def main():
    # app.exe: windowed, app_debug.exe: console
    build_one("app", "disable")
    build_one("app_debug", "force")


if __name__ == "__main__":
    main()
