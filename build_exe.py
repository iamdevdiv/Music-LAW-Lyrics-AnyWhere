"""
PyInstaller build script for YouTube Lyrics Popup
Run with: uv run build_exe.py
"""

import os
from PyInstaller.__main__ import run as pyinstaller_run

# Get the project root directory
project_root = os.path.dirname(os.path.abspath(__file__))

# PyInstaller arguments
args = [
    os.path.join(project_root, "main.py"),
    "--name=MusicLAW",
    "--onefile",  # Single exe file
    "--windowed",  # No console window
    f"--icon={os.path.join(project_root, 'icon.ico')}",
    f"--add-data={os.path.join(project_root, 'musiclaw.kv')}:.",
    f"--add-data={os.path.join(project_root, 'fonts')}:fonts",
    f"--add-data={os.path.join(project_root, 'images')}:images",
    "--collect-data=ytmusicapi",
    "--collect-submodules=ytmusicapi",
    f"--distpath={os.path.join(project_root, 'dist')}",
    f"--workpath={os.path.join(project_root, 'build')}",
    f"--specpath={os.path.join(project_root, 'spec')}",
    "-y",  # Overwrite without asking
]

if __name__ == "__main__":
    pyinstaller_run(args)
    print("\n[SUCCESS] Build completed! Check the 'dist' folder for MusicLAW.exe")
