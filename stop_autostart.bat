@echo off
cd /d "%~dp0"
net session >nul 2>nul || (echo [X] Run as administrator. & pause & exit /b 1)
schtasks /end /tn "FORMS Website" >nul 2>nul
schtasks /delete /f /tn "FORMS Website" >nul 2>nul
schtasks /delete /f /tn "FORMS Hourly Backup" >nul 2>nul
schtasks /delete /f /tn "FORMS Failover Watchdog" >nul 2>nul
echo Stopped and removed the FORMS tasks.
pause
