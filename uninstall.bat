@echo off
setlocal EnableDelayedExpansion

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

echo %CYAN%Uninstalling Stern-Volmer controller app...%NC%
echo.

:: 1. Remove the virtual environment
echo %YELLOW%Step 1/2:%GREEN% Removing Python virtual environment (.venv)...%NC%
if exist .venv (
    rmdir /s /q .venv
    if !errorlevel! equ 0 (
        echo %GREEN% Virtual environment deleted successfully.%NC%
    ) else (
        echo %RED% ERROR: %YELLOW%Could not remove .venv folder. Check if the app or an IDE is still using it.%NC%
    )
) else (
    echo %GREEN% Virtual environment not found. Skipping...%NC%
)

:: 2. Clear the Pip Cache
echo %YELLOW%Step 2/2:%GREEN% Clearing Python package cache...%NC%
:: Use the py launcher to call pip module directly
py -m pip cache purge >nul 2>&1

if %errorlevel% equ 0 (
    echo %GREEN% Package cache cleared.%NC%
) else (
    echo %GREEN% Pip cache already empty or no system Python found to perform cleanup.%NC%
)

echo.
echo  %CYAN%***********************************************************
echo  * Uninstallation complete^^!                                *
echo  * The updated Python, if installed, was left untouched.   *
echo  ***********************************************************%NC%

pause
