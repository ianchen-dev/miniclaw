@echo off
echo Batch Launcher for Claude Code
echo ================================
echo.
echo Usage: run-batch.bat [batch_size] [interval_seconds]
echo   Default: batch_size=5, interval=60s
echo.

cd /d %~dp0
python run-batch.py %1 %2
pause
