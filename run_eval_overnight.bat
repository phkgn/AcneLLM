@echo off
REM Chạy overnight eval — đảm bảo backend đang chạy trước khi double-click file này
REM Log output: data\eval\eval_all.log

cd /d "%~dp0"

REM Tạo thư mục log nếu chưa có
if not exist "data\eval" mkdir "data\eval"

echo [%time%] Starting overnight eval...
echo Backend phải đang chạy tại http://localhost:8000
echo.

REM Kiểm tra uv có sẵn không, nếu không fallback sang python
where uv >nul 2>&1
if %errorlevel% == 0 (
    echo [%time%] Dùng: uv run python
    uv run python scripts/eval_all.py --host http://localhost:8000 --judge-model llama3.2
) else (
    echo [%time%] uv không tìm thấy, thử dùng python trực tiếp...
    where python >nul 2>&1
    if %errorlevel% == 0 (
        echo [%time%] Dùng: python
        python scripts/eval_all.py --host http://localhost:8000 --judge-model llama3.2
    ) else (
        echo [%time%] LỖI: Không tìm thấy uv lẫn python. Hãy cài uv hoặc Python.
        pause
        exit /b 1
    )
)

echo.
if %errorlevel% == 0 (
    echo [%time%] Eval XONG OK.
) else (
    echo [%time%] Eval KẾT THÚC VỚI LỖI (exit code %errorlevel%).
)
echo [%time%] Xem log:       data\eval\eval_all.log
echo [%time%] HTML report:   data\eval\report.html
pause
