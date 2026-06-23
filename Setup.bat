@echo off
setlocal
cd /d "%~dp0"

py -m pip install --upgrade pip
if errorlevel 1 goto error
py -m pip install -r requirements.txt
if errorlevel 1 goto error

echo.
echo Python packages are installed.
where tesseract >nul 2>nul
if errorlevel 1 (
    echo.
    echo Tesseract OCR was not found.
    echo Install it from: https://github.com/UB-Mannheim/tesseract/wiki
    echo Include the Danish language if Danish OCR is needed.
)
echo.
pause
exit /b 0

:error
echo.
echo Setup failed.
pause
exit /b 1
