@echo off
cd /d "%~dp0"
rem rebuild the venv if it is missing or was copied from another PC
venv\Scripts\python.exe -c "pass" 2>nul || (if exist venv rmdir /s /q venv)
if not exist venv py -3 -m venv venv
call venv\Scripts\activate.bat
python -m pip install -q -r requirements.txt
if not exist data\A_Z_medicines_dataset_of_India.csv python -m mediguard.dataset --download
echo.
echo  1  Phone app + full database   (http://localhost:8000)
echo  2  Town simulation dashboard   (http://localhost:8765)
echo  3  Run all experiments         (results\ folder, about 5 minutes)
echo  4  Run the tests
set /p choice=Choose 1-4: 
if "%choice%"=="1" python server.py
if "%choice%"=="2" solara run sim_app.py
if "%choice%"=="3" python experiments.py
if "%choice%"=="4" python -m pytest -q tests
pause
