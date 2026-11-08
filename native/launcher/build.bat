@echo off
rem Builds dist\OpenShao-ModKit.exe, the one file that opens the ModKit: the launcher with a splash screen and dist\modkit.exe inside it. Run it from an x64 Native Tools Command Prompt for Visual Studio:
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
cl /nologo /O2 /EHsc /MT /DNDEBUG /Fo"%WORK%\\" /Fe"dist\OpenShao-ModKit.exe" native\launcher\modkit_launcher.cpp "%WORK%\launcher.res" /link /SUBSYSTEM:WINDOWS gdiplus.lib user32.lib gdi32.lib kernel32.lib bcrypt.lib || exit /b 1
if exist dist\modkit.exe (move /y dist\OpenShao-ModKit.exe "%WORK%\launcher.exe" >nul && "%PY%" packaging\windows\embed_payload.py "%WORK%\launcher.exe" dist\modkit.exe dist\OpenShao-ModKit.exe || exit /b 1)
rmdir /s /q "%WORK%"
echo built %CD%\dist\OpenShao-ModKit.exe
