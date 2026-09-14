@echo off
chcp 65001 >nul
cd /d "%~dp0"

REM 若没装依赖自动装
python -c "import requests" 2>nul || pip install requests
python -c "import openpyxl" 2>nul || pip install openpyxl

python main.py

echo.
echo ============================================
echo   程序已退出，按任意键关闭窗口
echo ============================================
pause >nul
