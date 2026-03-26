@echo off
setlocal
set "BASE=%~dp0"
"%BASE%.venv\Scripts\python.exe" "%BASE%app.py"
