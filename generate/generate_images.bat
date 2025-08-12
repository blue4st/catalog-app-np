@echo off
set MODE=%1
if "%MODE%"=="" (
    set MODE=incremental
)

echo Running in %MODE% mode...
python generate/generate_images.py --mode %MODE%
pause
