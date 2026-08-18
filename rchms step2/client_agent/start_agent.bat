@echo off
REM ============================================================
REM RCHMS Client Agent Auto-Start Script
REM Run on the CLIENT (customer-facing) PC. Starts the countdown
REM agent automatically when this PC boots, via Task Scheduler.
REM
REM You can also double-click this file any time to start the
REM agent manually.
REM ============================================================

cd /d "%~dp0"
python agent.py
