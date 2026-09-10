@echo off
setlocal
chcp 65001 >nul

set "SCRIPT_DIR=%~dp0src"
set "APP_NAME=VillagerTradePredictor"
set "BUILD_ENV=%~dp0.build-venv"

echo ========================================
echo  %APP_NAME% - Build EXE
echo ========================================
echo.

rem Prefer the Python Launcher, then fall back to python on PATH.
where py >nul 2>&1
if not errorlevel 1 (
    set "PYTHON_CMD=py"
) else (
    where python >nul 2>&1
    if errorlevel 1 (
        echo [ERROR] Python was not found. Install Python 3.10 or newer first.
        pause
        exit /b 1
    )
    set "PYTHON_CMD=python"
)

echo [1/4] Checking Python...
%PYTHON_CMD% --version
if errorlevel 1 (
    echo [ERROR] Python could not be started.
    pause
    exit /b 1
)

echo [2/4] Preparing an isolated build environment...
if not exist "%BUILD_ENV%\Scripts\python.exe" (
    %PYTHON_CMD% -m venv "%BUILD_ENV%"
    if errorlevel 1 (
        echo [ERROR] Could not create the build environment.
        pause
        exit /b 1
    )
)
set "BUILD_PYTHON=%BUILD_ENV%\Scripts\python.exe"

"%BUILD_PYTHON%" -m PyInstaller --version >nul 2>&1
if errorlevel 1 (
    echo Installing PyInstaller in the isolated build environment...
    "%BUILD_PYTHON%" -m pip install pyinstaller
    if errorlevel 1 (
        echo [ERROR] Could not install PyInstaller. Check the network connection.
        pause
        exit /b 1
    )
)

cd /d "%SCRIPT_DIR%"
if errorlevel 1 (
    echo [ERROR] Cannot enter the source directory: %SCRIPT_DIR%
    pause
    exit /b 1
)

echo [3/4] Removing old build files...
if exist "build" rmdir /s /q "build"
if exist "dist" rmdir /s /q "dist"

echo [4/4] Building EXE...
"%BUILD_PYTHON%" -m PyInstaller --noconfirm --clean --onefile --windowed --name "%APP_NAME%" "trade_export_gui.py"
if errorlevel 1 (
    echo.
    echo [ERROR] Build failed. See the error messages above.
    pause
    exit /b 1
)

if not exist "dist\%APP_NAME%.exe" (
    echo [ERROR] PyInstaller finished, but the EXE was not found.
    pause
    exit /b 1
)

echo.
echo ========================================
echo  Build completed.
echo  Output: %CD%\dist\%APP_NAME%.exe
echo ========================================
pause
endlocal
