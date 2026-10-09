@echo off
chcp 65001 > nul
cls

echo ========================================
echo    Animal Recognition System - Client B
echo ========================================

REM Set the title of the command window
title Animal Recognition System B

REM Check if .venv exists
if exist ".venv\Scripts\python.exe" (
    echo [INFO] Using virtual environment: .venv
    set PYTHON_PATH=.venv\Scripts\python.exe
) else if exist "venv\Scripts\python.exe" (
    echo [INFO] Using virtual environment: venv
    set PYTHON_PATH=venv\Scripts\python.exe
) else (
    echo [WARNING] No virtual environment found, using system Python
    set PYTHON_PATH=python
)

REM Check if Python exists
%PYTHON_PATH% --version > nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found or not accessible
    echo Please install Python 3.8+ or check your virtual environment
    pause
    exit /b 1
)

echo [INFO] Python version:
%PYTHON_PATH% --version

REM Check critical dependencies
echo [INFO] Checking dependencies...
%PYTHON_PATH% -c "import sys; print('[OK] Python:', sys.version.split()[0])"
%PYTHON_PATH% -c "import numpy; print('[OK] NumPy:', numpy.__version__)" 2>nul || echo [WARNING] NumPy not found
%PYTHON_PATH% -c "import cv2; print('[OK] OpenCV:', cv2.__version__)" 2>nul || echo [WARNING] OpenCV not found
%PYTHON_PATH% -c "import torch; print('[OK] PyTorch:', torch.__version__)" 2>nul || echo [WARNING] PyTorch not found
%PYTHON_PATH% -c "from ultralytics import YOLO; print('[OK] Ultralytics imported')" 2>nul || echo [WARNING] Ultralytics not found
%PYTHON_PATH% -c "from PyQt5 import QtCore; print('[OK] PyQt5 imported')" 2>nul || echo [WARNING] PyQt5 not found

REM Create necessary directories
echo [INFO] Creating directories...
if not exist "models" mkdir models
if not exist "logs" mkdir logs
if not exist "screenshots" mkdir screenshots
if not exist "data" mkdir data

REM Check config file
if not exist "config.py" (
    echo [WARNING] config.py not found, creating default config...
    copy config_default.py config.py >nul 2>&1
    if errorlevel 1 (
        echo [INFO] Please edit config.py to set Raspberry Pi IP address
    )
)

REM Run the main program
echo ========================================
echo [INFO] Starting Animal Recognition System...
echo ========================================

%PYTHON_PATH% main.py

if errorlevel 1 (
    echo [ERROR] Program exited with error code %errorlevel%
    echo.
    echo Troubleshooting tips:
    echo 1. Check if dependencies are installed: python install_dependencies.py
    echo 2. Check config.py for correct IP address
    echo 3. Make sure Raspberry Pi A-side is running
    echo 4. Check network connection
)

pause