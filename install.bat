@echo off
setlocal EnableDelayedExpansion

:: set the required Python version
set TARGET_PYTHON_VER=3.12

call :configANSI

echo %CYAN%--- Stern-Volmer app installation (Windows) ---%NC%
echo.

:: 1. Check if the target version of Python is installed
echo %YELLOW%Step 1/4:%GREEN% Checking if Python version %TARGET_PYTHON_VER% is installed...%NC%
py -%TARGET_PYTHON_VER% --version >nul 2>&1
if %errorlevel% neq 0 (
    echo %YELLOW% Python %TARGET_PYTHON_VER% is not found%NC%
    
    :: Check if winget exists
    where winget >nul 2>&1
    if !errorlevel! neq 0 (
        :: CORRECTED TO ! !
        echo !RED!ERROR: !YELLOW!The required Python version is missing and WinGet is not available.!NC!
        echo !CYAN!Please install Python %TARGET_PYTHON_VER% manually from python.org and run install.bat again.!NC!
        pause
        exit /b
    )

    echo %GREEN% Attempting to install Python %TARGET_PYTHON_VER% using WinGet...%NC%
    winget install --id Python.Python.%TARGET_PYTHON_VER% --exact --silent --accept-package-agreements --accept-source-agreements
    
    set WINGET_RESULT=!errorlevel!
    call :configANSI
    
    if !WINGET_RESULT! equ 0 (
        echo !GREEN! Python %TARGET_PYTHON_VER% has been installed. !NC!
        echo.
        echo !CYAN! ***********************************************************
        echo  * !RED!ACTION REQUIRED!CYAN! to continue:                            *
        echo  * Please CLOSE this window and run install.bat again      *
        echo  * to complete the setup with the new Python version.      *
        echo  ***********************************************************!NC!
    ) else (
        echo !RED! ERROR: !YELLOW!WinGet installation failed.
        echo !CYAN! Please install Python %TARGET_PYTHON_VER% manually from python.org and run install.bat again.!NC!
    )
    pause
    exit /b
)

:: The following part only runs if py -version succeeded
for /f "delims=" %%i in ('py -%TARGET_PYTHON_VER% -c "import sys; print(sys.executable)"') do (
    set "TARGET_PYTHON_LOCATION=%%i"
)
echo %GREEN% Python %TARGET_PYTHON_VER% is found in: %CYAN%!TARGET_PYTHON_LOCATION!%NC%

:: 2. (Re)create Python virtual environment in .venv
echo %YELLOW%Step 2/4:%GREEN% Creating/upgrading Python %TARGET_PYTHON_VER% virtual environment...%NC%
py -%TARGET_PYTHON_VER% -m venv .venv --clear
if %errorlevel% neq 0 (
    echo !RED! ERROR: !YELLOW!Failed to create Python %TARGET_PYTHON_VER% virtual environment in \.venv !NC! 
    pause
    exit /b
)

:: 3. Upgrading core tools in .venv
echo %YELLOW%Step 3/4:%GREEN% Upgrading core tools in the virtual environment... %NC%
.venv\Scripts\python.exe -m pip install --upgrade pip setuptools wheel

:: 4. Install Python packages
echo %YELLOW%Step 4/4:%GREEN% Installing Python requirements... %NC%
.venv\Scripts\python.exe -m pip install -r requirements\windows.txt

:: Capture the errorlevel
set PIP_RESULT=%errorlevel%

:: End of installation message
if %PIP_RESULT% equ 0 (
	echo.
    echo !CYAN! ***********************************************************
    echo  * Installation complete^^!                                   *
    echo  * Please run Stern-Volmer application with SV-windows.bat *
    echo  ***********************************************************!NC!
) else (
    echo !RED! ERROR: !YELLOW!Installation failed during package setup.!NC!
)

pause
exit /b

:configANSI
:: Empty color table for ANSI escape codes 
set "ESC="
set "GREEN="
set "YELLOW="
set "RED="
set "CYAN="
set "NC="

:: Populate it with correct escape codes if Win version is 10 or 11
ver | findstr /i /C:"Version 10." /C:"Version 11." >nul
if %errorlevel% equ 0 (
    for /F %%a in ('echo prompt $E ^| cmd') do set "ESC=%%a"
    set "GREEN=!ESC![92m"
    set "YELLOW=!ESC![93m"
    set "RED=!ESC![91m"
    set "CYAN=!ESC![96m"
    set "NC=!ESC![0m"
)
exit /b
