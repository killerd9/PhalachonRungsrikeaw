@echo off
cd /d "%~dp0"
set LOG=build_log.txt
echo Build started %date% %time% > %LOG%

rem --- find python (prefer 3.12 / 3.11 / 3.13 via py launcher) ---
set PY=
for %%V in (3.12 3.11 3.13 3.10) do (
  if not defined PY (
    py -%%V --version >nul 2>nul && set PY=py -%%V
  )
)
if not defined PY (
  python --version >nul 2>nul && set PY=python
)
if not defined PY goto :nopython

echo Using: %PY%
%PY% --version
%PY% --version >> %LOG% 2>&1

rem --- check version range 3.9 - 3.13 ---
%PY% -c "import sys; sys.exit(0 if (3,9)<=sys.version_info[:2]<=(3,13) else 1)"
if errorlevel 1 goto :badversion

echo.
echo [1/3] Installing libraries (this can take a few minutes)...
%PY% -m pip install --upgrade pip >> %LOG% 2>&1
%PY% -m pip install kivy "qrcode[pil]" pyinstaller >> %LOG% 2>&1
if errorlevel 1 goto :fail

echo [2/3] Checking kivy...
%PY% -c "import kivy, qrcode; print('kivy', kivy.__version__)" >> %LOG% 2>&1
if errorlevel 1 goto :fail

echo [3/3] Building exe...
%PY% -m PyInstaller --noconfirm --clean MakeQR.spec >> %LOG% 2>&1
if errorlevel 1 goto :fail

if not exist "dist\MakeQR\MakeQR.exe" goto :fail
echo.
echo ===== DONE =====
echo Program: %~dp0dist\MakeQR\MakeQR.exe
pause
exit /b 0

:nopython
echo.
echo [ERROR] Python not found.
echo Install Python 3.12 from https://www.python.org/downloads/windows/
echo and TICK "Add python.exe to PATH" in the installer, then run this again.
pause
exit /b 1

:badversion
echo.
echo [ERROR] Your Python version is not supported (need 3.9 - 3.13).
echo Install Python 3.12 from https://www.python.org/downloads/windows/
echo (tick "Add python.exe to PATH"), then run this again.
pause
exit /b 1

:fail
echo.
echo [ERROR] Build failed. Last lines of the log (full log: %~dp0%LOG%):
echo ------------------------------------------------------------
powershell -NoProfile -Command "Get-Content -Tail 25 '%LOG%'"
echo ------------------------------------------------------------
pause
exit /b 1
