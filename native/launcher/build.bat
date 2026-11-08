@echo off
rem Builds dist\OpenShao-ModKit.exe, the launcher that shows the splash screen. Run it from an x64 Native Tools Command Prompt for Visual Studio:
rem     native\launcher\build.bat [path\to\python.exe]
rem The Python needs numpy: it draws the circle's picture (packaging\windows\make_splash_assets.py).
setlocal
set "PY=%~1"
if "%PY%"=="" set "PY=python"
cd /d "%~dp0..\.."
set "WORK=%TEMP%\openshao-launcher-%RANDOM%"
mkdir "%WORK%" || exit /b 1
"%PY%" packaging\windows\make_splash_assets.py "%WORK%" || exit /b 1
copy /y src\modkit\gui\app.ico "%WORK%\app.ico" >nul
rc /nologo /fo "%WORK%\launcher.res" /i "%WORK%" native\launcher\launcher.rc || exit /b 1
if not exist dist mkdir dist
cl /nologo /O2 /EHsc /MT /DNDEBUG /Fo"%WORK%\\" /Fe"dist\OpenShao-ModKit.exe" native\launcher\modkit_launcher.cpp "%WORK%\launcher.res" /link /SUBSYSTEM:WINDOWS gdiplus.lib user32.lib gdi32.lib kernel32.lib || exit /b 1
rmdir /s /q "%WORK%"
echo built %CD%\dist\OpenShao-ModKit.exe
