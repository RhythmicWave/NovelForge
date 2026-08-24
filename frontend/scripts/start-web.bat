@echo off
setlocal
cd /d "%~dp0"
python start-web.py
if errorlevel 1 pause
