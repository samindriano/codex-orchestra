@echo off
setlocal
if exist "%~dp0..\scripts\orchestra_dashboard_product.py" (
  py -3 "%~dp0..\scripts\orchestra_dashboard_product.py" %*
) else (
  echo orchestra-dashboard-product: product dashboard script is not available in this checkout 1>&2
  endlocal & exit /b 2
)
set "EXIT_CODE=%ERRORLEVEL%"
endlocal & exit /b %EXIT_CODE%
