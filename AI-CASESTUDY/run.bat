@echo off
cd /d "%~dp0"
rem rebuild the venv if it is missing or was copied from another PC
venv\Scripts\python.exe -c "pass" 2>nul || (if exist venv rmdir /s /q venv)
if not exist venv py -3 -m venv venv
call venv\Scripts\activate.bat
python -m pip install -q -r requirements.txt
echo.
echo Open http://localhost:8765 in your browser (press Ctrl+C here to stop)
python -m solara run app.py
pause
