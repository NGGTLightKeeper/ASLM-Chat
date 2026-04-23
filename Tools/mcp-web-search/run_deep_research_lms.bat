@echo off
setlocal EnableExtensions
chcp 65001 >nul

cd /d "%~dp0"

if "%~1"=="" (
  echo Agentic Deep Research via LMS
  echo.
  set /p "QUESTION=Research question: "
) else (
  set "QUESTION=%*"
)

if "%QUESTION%"=="" (
  echo No question provided.
  pause
  exit /b 2
)
set "STAMP=%DATE%_%TIME%"
set "STAMP=%STAMP:/=-%"
set "STAMP=%STAMP::=-%"
set "STAMP=%STAMP:.=-%"
set "STAMP=%STAMP:,=-%"
set "STAMP=%STAMP: =_%"
set "TASK_ID=lms_%STAMP%"

set "ASLM_LLM_ENGINE=lms"
set "ASLM_JSON_REASONING_EFFORT=off"
set "MCP_WEB_SEARCH_DEEP_RESEARCH_LOGS=1"
set "PYTHONIOENCODING=utf-8"
set "PYTHONUTF8=1"
set "PYTHONDONTWRITEBYTECODE=1"

echo [deep_research:lms] Question: %QUESTION%
echo [deep_research:lms] Task id : %TASK_ID%
echo [deep_research:lms] Engine  : %ASLM_LLM_ENGINE%
echo.

set "TIMEOUT_ARG="
if not "%DEEP_RESEARCH_TIMEOUT_SEC%"=="" set "TIMEOUT_ARG=--timeout %DEEP_RESEARCH_TIMEOUT_SEC%"

python -B scripts\deep_research.py "%QUESTION%" --depth standard --id "%TASK_ID%" %TIMEOUT_ARG%
set "EXIT_CODE=%ERRORLEVEL%"

echo.
if "%EXIT_CODE%"=="0" (
  echo [deep_research:lms] Done.
  echo [deep_research:lms] Report: %CD%\_out\%TASK_ID%\report.md
  echo [deep_research:lms] Realtime logs: %CD%\logs\deep_research\logs
  echo [deep_research:lms] Agentic artifacts: %CD%\logs\deep_research\agentic
) else (
  echo [deep_research:lms] Failed with exit code %EXIT_CODE%.
  echo [deep_research:lms] Realtime logs: %CD%\logs\deep_research\logs
)

if "%~1"=="" pause
exit /b %EXIT_CODE%
