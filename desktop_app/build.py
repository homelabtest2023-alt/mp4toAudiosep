"""
build.py - Packages the AudioSep Desktop Client into a standalone .exe
Usage: python build.py

Requires PyInstaller: pip install pyinstaller
"""
import subprocess
import sys
import os

APP_NAME = "AudioSepClient"
ENTRY_POINT = "main.py"

def main():
    print(f"Building {APP_NAME}.exe ...")

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",           # Overwrite output without asking
        "--onedir",              # Single folder (faster startup than --onefile)
        "--windowed",            # No terminal/console window on launch
        "--name", APP_NAME,
        # Include the application sub-packages so PyInstaller finds them
        "--add-data", f"core{os.pathsep}core",
        "--add-data", f"gui{os.pathsep}gui",
        # Hidden imports needed by PySide6 multimedia
        "--hidden-import", "PySide6.QtMultimedia",
        "--hidden-import", "PySide6.QtNetwork",
        ENTRY_POINT,
    ]

    print("Running:", " ".join(cmd))
    result = subprocess.run(cmd, check=False)

    if result.returncode == 0:
        dist_path = os.path.join("dist", APP_NAME, f"{APP_NAME}.exe")
        print("\n" + "="*60)
        print(f"✅  Build succeeded!")
        print(f"    Executable: {os.path.abspath(dist_path)}")
        print("="*60)
    else:
        print("\n" + "="*60)
        print("❌  Build FAILED. See the output above for details.")
        print("="*60)
        sys.exit(1)

if __name__ == "__main__":
    main()
