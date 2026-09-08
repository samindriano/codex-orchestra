@echo off
if exist "%~dp0codex_benchmark_launcher.py" (
  py -3 "%~dp0codex_benchmark_launcher.py" standard -- %*
) else (
  py -3 "%~dp0..\scripts\codex_benchmark_launcher.py" standard -- %*
)
exit /b %ERRORLEVEL%
