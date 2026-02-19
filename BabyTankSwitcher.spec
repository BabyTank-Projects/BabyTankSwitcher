# BabyTankSwitcher.spec
# PyInstaller spec — run with:  pyinstaller BabyTankSwitcher.spec
# Compatible with Python 3.14

import sys
from pathlib import Path
import customtkinter

block_cipher = None

# ── Locate the customtkinter data files (themes, fonts, images) ───────────────
ctk_path = Path(customtkinter.__file__).parent

a = Analysis(
    ['app.py'],
    pathex=['.'],
    binaries=[],
    datas=[
        (str(ctk_path), 'customtkinter'),
    ],
    hiddenimports=[
        'tkinter',
        'tkinter.ttk',
        'tkinter.messagebox',
        'tkinter.filedialog',
        'tkinter.colorchooser',
        'PIL',
        'PIL.Image',
        'PIL.ImageTk',
        'PIL.ImageGrab',
        'PIL.ImageDraw',
        'win32gui',
        'win32con',
        'win32ui',
        'win32process',
        'win32api',
        'pywintypes',
        'winerror',
        'psutil',
        'psutil._pswindows',
        'customtkinter.windows',
        'customtkinter.windows.widgets',
        'customtkinter.windows.widgets.core_rendering',
        'customtkinter.windows.widgets.theme',
        'customtkinter.windows.widgets.font',
        'urllib',
        'urllib.request',
        'urllib.parse',
        'urllib.error',
        'email',
        'html',
        'http',
        'http.client',
        'xml',
        'xml.etree.ElementTree',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'matplotlib',
        'numpy',
        'pandas',
        'scipy',
        'PyQt5',
        'PyQt6',
        'PySide2',
        'PySide6',
        'wx',
        'gi',
        'IPython',
        'jupyter',
        'notebook',
        'pydoc',
        'doctest',
        'unittest',
        'difflib',
        'sqlite3',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='BabyTankSwitcher',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    version='version_info.txt',
)
