@echo off
rem Run once. Creates two Windows scheduled tasks that run auto_pull.bat
rem daily at 9:00 AM, with a backup at 12:00 PM.
setlocal
set "SCRIPT=%~dp0auto_pull.bat"
schtasks /Delete /F /TN "Grocery Dashboard Auto Pull" >nul 2>nul
schtasks /Create /F /TN "Grocery Dashboard Auto Pull 9AM"  /SC DAILY /ST 09:00 /TR "\"%SCRIPT%\"" >nul
set E1=%errorlevel%
schtasks /Create /F /TN "Grocery Dashboard Auto Pull 12PM" /SC DAILY /ST 12:00 /TR "\"%SCRIPT%\"" >nul
set E2=%errorlevel%
if not "%E1%%E2%"=="00" (
  echo Could not create the tasks. Right-click this file and choose "Run as administrator".
) else (
  echo Done. Auto pull runs daily at 9:00 AM, backup at 12:00 PM.
  echo Running it once now...
  call "%SCRIPT%"
  echo Check auto_pull.log in this folder for the result.
)
pause
