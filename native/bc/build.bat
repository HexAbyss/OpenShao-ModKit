@echo off
rem Builds bcenc.dll, the BC encoders (rgbcx and stb_dxt), into src\modkit\_native. Run it from an x64 Native Tools Command Prompt for
rem Visual Studio. The objects and the import library go to a temporary folder; only the DLL is kept.
setlocal
where cl >nul 2>nul || (echo cl was not found: open an "x64 Native Tools Command Prompt for VS" and run this again 1>&2 & exit /b 1)
set "HERE=%~dp0"
set "WORK=%TEMP%\openshao-bcenc-%RANDOM%"
mkdir "%WORK%" || exit /b 1
pushd "%HERE%"
cl /nologo /std:c++17 /O2 /LD /EHsc /I. bcenc.cpp rgbcx.cpp /Fo:"%WORK%\\" /Fe:"%WORK%\bcenc.dll" || (popd & rmdir /s /q "%WORK%" & exit /b 1)
popd
copy /y "%WORK%\bcenc.dll" "%HERE%..\..\src\modkit\_native\bcenc.dll" >nul || (rmdir /s /q "%WORK%" & exit /b 1)
rmdir /s /q "%WORK%"
echo built %HERE%..\..\src\modkit\_native\bcenc.dll
