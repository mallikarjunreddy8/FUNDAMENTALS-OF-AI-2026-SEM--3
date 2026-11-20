@echo off
cd /d "%~dp0"
echo Open http://localhost:8000 in your browser (press Ctrl+C here to stop)
start "" http://localhost:8000
py -3 -m http.server 8000 || python -m http.server 8000
pause
