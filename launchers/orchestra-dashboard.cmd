@echo off
setlocal
if exist "%~dp0..\scripts\orchestra_dashboard.py" (
  py -3 "%~dp0..\scripts\orchestra_dashboard.py" %*
) else if exist "%~dp0orchestra_dashboard.py" (
  py -3 "%~dp0orchestra_dashboard.py" %*
) else (
  echo orchestra-dashboard: dashboard script is not installed 1>&2
  endlocal & exit /b 2
)
set "EXIT_CODE=%ERRORLEVEL%"
endlocal & exit /b %EXIT_CODE%
