@echo off
rem Pulls the latest daily FnV files from GitHub into this folder.
rem Uses Git for Windows if installed, otherwise the git bundled with GitHub Desktop.
setlocal
cd /d "%~dp0"

set "GIT=git"
where git >nul 2>nul
if errorlevel 1 (
  set "GIT="
  for /d %%D in ("%LOCALAPPDATA%\GitHubDesktop\app-*") do (
    if exist "%%D\resources\app\git\cmd\git.exe" set "GIT=%%D\resources\app\git\cmd\git.exe"
  )
)
if not defined GIT (
  echo %date% %time%  ERROR: git not found >> auto_pull.log
  exit /b 1
)

echo %date% %time%  pulling >> auto_pull.log
"%GIT%" pull --ff-only origin main >> auto_pull.log 2>&1
endlocal
