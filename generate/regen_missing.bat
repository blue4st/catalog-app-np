@echo off
setlocal

REM === Set Python executable path if needed ===
REM set PYTHON_PATH=C:\Path\To\Python\python.exe

REM === Run the generator script in incremental mode ===
REM If using a virtual environment, activate it here

echo Running regeneration for missing variants...
python generate_variants.py

pause
