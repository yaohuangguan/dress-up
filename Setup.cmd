@echo off
cd /d "%~dp0"
py -3.11 scripts\bootstrap.py %*
if errorlevel 1 pause
