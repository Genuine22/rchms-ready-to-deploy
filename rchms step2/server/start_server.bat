@echo off
REM ============================================================
REM RCHMS Server Auto-Start Script
REM This file is called by Windows Task Scheduler when the Admin
REM PC starts up. It activates the virtual environment and runs
REM the server, keeping a log of anything that happens.
REM
REM You do NOT need to double-click this file yourself once Task
REM Scheduler is set up - it runs automatically. You can still
REM double-click it any time to start the server manually.
REM ============================================================

cd /d "%~dp0"
call venv\Scripts\activate.bat
python run.py >> server_log.txt 2>&1
