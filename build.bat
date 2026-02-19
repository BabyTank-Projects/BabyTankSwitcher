@echo off
cd /d "%~dp0"
:: build.bat — Local build script for Baby Tank Switcher
:: Targets Python 3.14 at C:\Python314

echo ============================================
echo  Baby Tank Switcher — Local Build
echo ============================================
echo.

:: ── Point explicitly at C:\Python314 ─────────────────────────────────────────
set PYTHON=C:\Python314\python.exe

:: Verify Python exists
if not exist "%PYTHON%" (
    echo ERROR: Python not found at C:\Python314\python.exe
    echo Edit the PYTHON variable at the top of this script if installed elsewhere.
    pause
    exit /b 1
)

echo Using: %PYTHON%
%PYTHON% --version
echo.

:: ── Step 1: Install / update dependencies ────────────────────────────────────
echo [1/3] Installing dependencies...
%PYTHON% -m pip install --upgrade pip --quiet
if errorlevel 1 echo WARNING: pip upgrade failed, continuing...

%PYTHON% -m pip install -r requirements.txt --quiet
if errorlevel 1 (
    echo ERROR: Failed to install requirements.txt
    pause
    exit /b 1
)

:: Install latest PyInstaller pre-release for Python 3.14 support
%PYTHON% -m pip install --upgrade --pre pyinstaller --quiet
if errorlevel 1 (
    echo ERROR: Could not install PyInstaller.
    pause
    exit /b 1
)
echo       Done.
echo.

:: ── Step 2: Generate version_info.txt ────────────────────────────────────────
echo [2/3] Generating version info...
%PYTHON% generate_version_info.py 0.0.0
if errorlevel 1 (
    echo ERROR: Failed to generate version_info.txt
    pause
    exit /b 1
)
echo       Done.
echo.

:: ── Step 3: Build with PyInstaller ───────────────────────────────────────────
echo [3/3] Building exe...

:: Create dist\ in advance to avoid permission issues
if not exist dist mkdir dist

:: Run PyInstaller as a Python module (avoids Scripts\ launcher issues on 3.14)
%PYTHON% -m PyInstaller BabyTankSwitcher.spec --noconfirm
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
