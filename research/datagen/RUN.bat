@echo off
setlocal
set "RESEARCH_ROOT=%~dp0.."
set "REPO_ROOT=%~dp0..\.."
set "PYTHONPATH=%RESEARCH_ROOT%;%PYTHONPATH%"
set "PYTHON_EXE=%REPO_ROOT%\.venv\Scripts\python.exe"
if not exist "%PYTHON_EXE%" (
  echo LOI: Khong tim thay .venv tai "%PYTHON_EXE%".
  echo Hay tao/cai dat .venv cua repo truoc khi chay datagen.
  exit /b 2
)
cd /d "%REPO_ROOT%"
"%PYTHON_EXE%" -m datagen.main %*
exit /b %ERRORLEVEL%
