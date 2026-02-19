@echo off
:: build.bat — Local build script for Baby Tank Switcher
:: Run this to produce dist\BabyTankSwitcher.exe on your own machine.

echo ============================================
echo  Baby Tank Switcher — Local Build
echo ============================================
echo.

:: Check Python is available
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found on PATH.
    echo Install Python 3.11+ from https://python.org
    pause
    exit /b 1
)

:: Install / update dependencies
echo [1/3] Installing dependencies...
python -m pip install --upgrade pip --quiet
pip install -r requirements.txt --quiet
pip install pyinstaller --quiet
echo       Done.
echo.

:: Generate a dummy version_info.txt for local builds
echo [2/3] Generating version info...
python -c ^
"content=open('version_info.txt','w') if False else None; ^
v='0.0.0'; ^
parts=v.split('.')+['0']; ^
vt=', '.join(parts[:4]); ^
txt=f'''# UTF-8\nVSVersionInfo(\n  ffi=FixedFileInfo(\n    filevers=({vt}),\n    prodvers=({vt}),\n    mask=0x3f,flags=0x0,OS=0x40004,fileType=0x1,subtype=0x0,date=(0,0)\n  ),\n  kids=[\n    StringFileInfo([StringTable(u\"040904B0\",[StringStruct(u\"FileDescription\",u\"Baby Tank Switcher\"),StringStruct(u\"FileVersion\",u\"0.0.0\"),StringStruct(u\"ProductName\",u\"Baby Tank Switcher\"),StringStruct(u\"ProductVersion\",u\"0.0.0\")])]),\n    VarFileInfo([VarStruct(u\"Translation\",[1033,1200])])\n  ]\n)\n'''; ^
open('version_info.txt','w').write(txt)"
echo       Done.
echo.

:: Run PyInstaller
echo [3/3] Building exe...
pyinstaller BabyTankSwitcher.spec --noconfirm
if errorlevel 1 (
    echo.
    echo ERROR: Build failed. Check output above.
    pause
    exit /b 1
)

echo.
echo ============================================
echo  Build complete!
echo  Output: dist\BabyTankSwitcher.exe
echo ============================================
pause
