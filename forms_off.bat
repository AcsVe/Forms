@echo off
chcp 65001 >nul
title FORMS - Turn the forms system OFF
net session >nul 2>nul || (echo [X] Right-click this file and choose "Run as administrator". & pause & exit /b 1)
REM Stops 9.iajaward.org only - the other systems on this PC keep running.
REM Public forms stop accepting answers until it is turned on again.
schtasks /end /tn "FORMS Website" >nul 2>nul
schtasks /change /tn "FORMS Website" /disable >nul 2>nul
echo.
echo   9.iajaward.org (forms) is OFF (also after restarting the PC).
echo   Public forms do not open until it is turned on again.
echo   To turn it back on: forms_on.bat (as administrator)
echo.
pause
