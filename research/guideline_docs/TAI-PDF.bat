@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo Dang tai PDF guideline mun trung ca...
echo.
python download_acne_pdfs.py
if errorlevel 1 (
  echo.
  echo Khong chay duoc. Thu lenh: py download_acne_pdfs.py
  py download_acne_pdfs.py
)
echo.
pause
