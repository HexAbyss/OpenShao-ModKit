@echo off
rem Builds the ModKit as one Windows executable (dist\modkit.exe) that needs no Python to run.
rem Run it from an x64 Native Tools Command Prompt for Visual Studio, with the Python that has the build packages:
rem     packaging\windows\build.bat [path\to\python.exe]
rem The packages are pyinstaller, unicorn, numpy, pillow and imgui-bundle; a virtual environment keeps them out of the system's Python.
setlocal
set "PY=%~1"
if "%PY%"=="" set "PY=python"
cd /d "%~dp0..\.."
call native\bc\build.bat || exit /b 1
set "BC_LIB=%CD%\src\modkit\_native\bcenc.dll"
rem The Unicorn library is loaded by path, so PyInstaller does not see it: it is added by hand.
set "UNICORN_LIB="
for /f "usebackq delims=" %%i in (`""%PY%" "%~dp0unicorn_path.py""`) do set "UNICORN_LIB=%%i"
if not exist "%UNICORN_LIB%" (echo unicorn.dll was not found: install the unicorn package in that Python 1>&2 & exit /b 1)
set "WORK=%TEMP%\openshao-modkit-build"
if exist "%WORK%" rmdir /s /q "%WORK%"
set PYTHONDONTWRITEBYTECODE=1
"%PY%" -m PyInstaller --noconfirm --distpath dist --workpath "%WORK%" packaging\modkit.spec > "%WORK%.log" 2>&1 || (powershell -NoProfile -Command "Get-Content -Tail 30 '%WORK%.log'" & exit /b 1)
rem Control Flow Guard in the bootloader aborts the process when Unicorn runs: see disable_cfg.py.
for %%f in (dist\modkit.exe dist\OpenShao-ModKit.exe) do "%PY%" "%~dp0disable_cfg.py" %%f || exit /b 1
echo built %CD%\dist\modkit.exe and %CD%\dist\OpenShao-ModKit.exe
