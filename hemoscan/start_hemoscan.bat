@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title HemoScan launcher

rem ============================================================
rem  HemoScan - one-click setup + launcher for a fresh Windows PC
rem    start_hemoscan.bat           install anything missing, then start
rem    start_hemoscan.bat nosim     same, without the fake ESP32 (use real hardware)
rem    start_hemoscan.bat train     also train the models if the dataset is present
rem    start_hemoscan.bat check     only report what is installed / missing, change nothing
rem
rem  Installs automatically (via winget, built into Windows 10/11):
rem    Python 3.11  - if no Python 3.8 - 3.11 is found (TensorFlow 2.13 needs one of those)
rem    Node.js LTS  - if Node is missing or older than 18
rem  Then: Python packages in .venv, dashboard packages, dashboard build, API start.
rem ============================================================

if "%HEMOSCAN_PORT%"=="" set HEMOSCAN_PORT=8000
set "SIM=ask"
set "TRAIN=0"
set "CHECKONLY=0"
for %%A in (%*) do (
  if /i "%%A"=="nosim" set "SIM=no"
  if /i "%%A"=="train" set "TRAIN=1"
  if /i "%%A"=="check" set "CHECKONLY=1"
)

echo.
echo  === HemoScan ===
echo.
set "MISSING=0"

rem ---------- 1. Python 3.8 - 3.11 ----------
set "BASEPY="
call :findpy
if defined BASEPY goto :pyok
echo [!] No Python 3.8 - 3.11 found.
call :wingetinstall Python.Python.3.11 "Python 3.11"
call :findpy
if defined BASEPY goto :pyok
if "%CHECKONLY%"=="1" ( set "MISSING=1" & goto :node )
echo [X] Python 3.11 could not be installed automatically.
echo     Install it from https://www.python.org/downloads/ - tick "Add python.exe to PATH" - then run this again.
goto :fail
:pyok
rem the extra outer quotes survive cmd /c stripping one pair when the path has spaces
for /f "tokens=2" %%v in ('""%BASEPY%" --version"') do set PYVER=%%v
echo [OK] Python %PYVER%  -  %BASEPY%

rem ---------- 2. Node.js 18+ ----------
:node
call :findnode
if defined NODEOK goto :nodeok
echo [!] Node.js 18 or newer not found.
call :wingetinstall OpenJS.NodeJS.LTS "Node.js LTS"
set "PATH=%PATH%;%ProgramFiles%\nodejs"
call :findnode
if defined NODEOK goto :nodeok
if "%CHECKONLY%"=="1" ( set "MISSING=1" & goto :checkdone )
echo [X] Node.js could not be installed automatically. Install the LTS version from https://nodejs.org and run this again.
goto :fail
:nodeok
for /f "delims=" %%v in ('node -v') do echo [OK] Node %%v

rem ---------- other things worth knowing ----------
where curl >nul 2>nul || echo [!] curl not found - the launcher cannot detect when the API is ready; open http://localhost:%HEMOSCAN_PORT% yourself.
if exist "ml\data\dataset_blood_group" (echo [OK] Dataset found in ml\data\dataset_blood_group) else (echo [!] No dataset - training disabled until the Kaggle folders are placed in ml\data\dataset_blood_group)
if exist "backend\models\fingerprint_model.h5" (echo [OK] Trained model found) else (echo [!] No trained model yet - the API will run in DEMO mode)

:checkdone
if not "%CHECKONLY%"=="1" goto :setup
echo.
if "%MISSING%"=="1" (echo Check finished - something is missing, run without "check" to install it.) else (echo Check finished - all requirements are installed.)
goto :end

:setup
rem ---------- 3. Python environment (rebuilt if broken, e.g. its base Python was uninstalled) ----------
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" -c "import sys; assert (3,8) <= sys.version_info[:2] <= (3,11)" >nul 2>nul
  if errorlevel 1 (
    echo [!] The existing .venv is broken or uses an unsupported Python - recreating it
    rmdir /s /q ".venv"
  )
)
if not exist ".venv\Scripts\python.exe" (
  echo [..] Creating Python environment in .venv
  "%BASEPY%" -m venv .venv
  if errorlevel 1 goto :fail
)
set "PY=%~dp0.venv\Scripts\python.exe"

if exist ".venv\.deps_installed" (
  "%PY%" -c "import tensorflow, fastapi, uvicorn, cv2, sklearn" >nul 2>nul
  if errorlevel 1 (
    echo [!] Some Python packages are missing - reinstalling
    del ".venv\.deps_installed"
  )
)
if exist ".venv\.deps_installed" (
  echo [OK] Python packages already installed
  goto :dash
)
echo.
echo [..] Installing Python packages - first run only, this can take several minutes
"%PY%" -m pip install --upgrade pip
echo      step 1/2: TensorFlow and ML libraries
"%PY%" -m pip install -r backend\requirements-ml.txt
if errorlevel 1 (
  echo [X] ML package install failed - see the messages above.
  goto :fail
)
echo      step 2/2: API and sensor tools - a typing-extensions warning below is expected and harmless
"%PY%" -m pip install -r backend\requirements.txt
if errorlevel 1 (
  echo [X] API package install failed - see the messages above.
  goto :fail
)
echo ok> ".venv\.deps_installed"

:dash
rem ---------- 4. Dashboard (React) ----------
if not exist "frontend\node_modules" (
  echo.
  echo [..] Installing dashboard packages - first run only
  pushd frontend
  call npm install
  if errorlevel 1 ( popd & echo [X] npm install failed. & goto :fail )
  popd
) else (
  echo [OK] Dashboard packages already installed
)
rem rebuild when the dashboard source is newer than the last build
set "NEEDBUILD=1"
if exist "frontend\dist\index.html" (
  powershell -NoProfile -Command "$b=(Get-Item 'frontend\dist\index.html').LastWriteTime; if (Get-ChildItem 'frontend\src','frontend\index.html','frontend\package.json' -Recurse -File | Where-Object { $_.LastWriteTime -gt $b }) { exit 1 } else { exit 0 }"
  if not errorlevel 1 set "NEEDBUILD=0"
)
if "%NEEDBUILD%"=="1" (
  echo [..] Building the dashboard
  pushd frontend
  call npm run build
  if errorlevel 1 ( popd & echo [X] Dashboard build failed. & goto :fail )
  popd
) else (
  echo [OK] Dashboard build is up to date
)

rem ---------- 5. Model ----------
if "%TRAIN%"=="1" (
  if exist "ml\data\dataset_blood_group" (
    echo [..] Training the models - this takes a long time on a CPU. Progress is also shown on the Models page.
    "%PY%" ml\train_model.py
  ) else (
    echo [!] No dataset in ml\data\dataset_blood_group - skipping training.
  )
)
if exist "backend\models\fingerprint_model.h5" (
  set "HEMOSCAN_DEMO="
) else (
  echo [!] Starting in DEMO mode - predictions are RANDOM until a model is trained.
  echo     Train from the dashboard: Models and Training - Train all models
  set "HEMOSCAN_DEMO=1"
)

rem ---------- 6. Start the API ----------
echo.
echo [..] Starting the API on port %HEMOSCAN_PORT%
start "HemoScan API" /D "%~dp0backend" cmd /k ""%PY%" -m uvicorn app.main:app --host 0.0.0.0 --port %HEMOSCAN_PORT%"

rem ---------- 7. ESP32 simulator ----------
if "%SIM%"=="ask" (
  echo.
  choice /c YN /t 10 /d Y /m "Start the fake ESP32 simulator (choose N if the real ESP32 is connected)"
  if errorlevel 2 (set "SIM=no") else (set "SIM=yes")
)
if "%SIM%"=="yes" (
  start "HemoScan ESP32 simulator" /D "%~dp0backend" cmd /k ""%PY%" tools\esp32_simulator.py --server http://localhost:%HEMOSCAN_PORT%"
)

rem ---------- 8. Wait until the API answers, then open the browser ----------
echo [..] Waiting for the API to be ready - the first start can take about 30 seconds
set /a TRIES=0
:wait
set /a TRIES+=1
curl -s -f -o nul http://localhost:%HEMOSCAN_PORT%/api/health && goto :ready
if %TRIES% GEQ 60 (
  echo [X] The API did not start - read the "HemoScan API" window for the error.
  goto :fail
)
timeout /t 2 /nobreak >nul
goto :wait

:ready
echo.
echo [OK] HemoScan is running:  http://localhost:%HEMOSCAN_PORT%
echo      First visit:          create the admin account, then add users under "Users"
echo      API docs:             http://localhost:%HEMOSCAN_PORT%/docs
echo      Stop everything with: stop_hemoscan.bat
start "" http://localhost:%HEMOSCAN_PORT%
goto :end

rem ============================================================ helpers
:findpy
rem sets BASEPY to the full path of a Python 3.8 - 3.11 (newest first), or leaves it empty
set "BASEPY="
for %%V in (3.11 3.10 3.9 3.8) do (
  if not defined BASEPY for /f "delims=" %%E in ('py -%%V -c "import sys;print(sys.executable)" 2^>nul') do set "BASEPY=%%E"
)
if defined BASEPY exit /b 0
for %%P in ("%LOCALAPPDATA%\Programs\Python\Python311\python.exe" "%LOCALAPPDATA%\Programs\Python\Python310\python.exe" "%ProgramFiles%\Python311\python.exe" "%ProgramFiles%\Python310\python.exe") do (
  if not defined BASEPY if exist %%P set "BASEPY=%%~P"
)
if defined BASEPY exit /b 0
for /f "delims=" %%E in ('python -c "import sys;print(sys.executable if (3,8)<=sys.version_info[:2]<=(3,11) else 0)" 2^>nul') do set "BASEPY=%%E"
if "%BASEPY%"=="0" set "BASEPY="
exit /b 0

:findnode
set "NODEOK="
set "NODEMAJ="
where node >nul 2>nul || exit /b 0
for /f "tokens=1 delims=v." %%v in ('node -v') do set "NODEMAJ=%%v"
if not defined NODEMAJ exit /b 0
if %NODEMAJ% GEQ 18 set "NODEOK=1"
exit /b 0

:wingetinstall
rem %1 = winget package id, %2 = display name
if "%CHECKONLY%"=="1" (
  echo     would install %~2 - run without "check" to do it
  exit /b 1
)
where winget >nul 2>nul
if errorlevel 1 (
  echo [X] winget is not available on this PC, so %~2 cannot be installed automatically.
  exit /b 1
)
echo [..] Installing %~2 with winget - accept the Windows prompt if one appears
winget install -e --id %~1 --silent --accept-package-agreements --accept-source-agreements
exit /b 0

:fail
echo.
echo Setup stopped. Fix the problem above and run this file again.
pause
exit /b 1

:end
echo.
pause
endlocal
