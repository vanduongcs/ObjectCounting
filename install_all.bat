@echo off
setlocal

echo [1/3] Checking Python...
where python >nul 2>nul || (
  echo Python not found. Please install Python 3.10+ and retry.
  exit /b 1
)

echo [2/3] Installing Python dependencies...
python -m pip install -r requirements.txt
if errorlevel 1 (
  echo pip install failed.
  exit /b 1
)

echo [3/3] Checking Tesseract OCR...
where tesseract >nul 2>nul
if %errorlevel%==0 (
  echo Tesseract found in PATH.
  goto :done
)

if exist "C:\\Program Files\\Tesseract-OCR\\tesseract.exe" (
  echo Tesseract found at default path.
  goto :done
)

where winget >nul 2>nul
if %errorlevel%==0 (
  echo Installing Tesseract via winget...
  winget install --id UB-Mannheim.TesseractOCR -e
) else (
  echo winget not found. Please install Tesseract manually and ensure it is in PATH.
)

:done
echo Done.
endlocal
