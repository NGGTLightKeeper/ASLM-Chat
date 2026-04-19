@echo off
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 > nul
cd /d "%~dp0"

echo.
echo  Deep Research  ^|  mcp-web-search
echo  ================================
echo  1. low    (4 queries,   ~5 min)
echo  2. medium (7 queries,  ~10 min)
echo  3. high   (10 queries, ~15 min)
echo  4. extra  (14 queries, ~20 min)
echo.
set /p DEPTH_CHOICE=Depth (1-4, default 2):

if "!DEPTH_CHOICE!"=="" set "DEPTH_CHOICE=2"
if "!DEPTH_CHOICE!"=="1" set "DEPTH=low"
if "!DEPTH_CHOICE!"=="2" set "DEPTH=medium"
if "!DEPTH_CHOICE!"=="3" set "DEPTH=high"
if "!DEPTH_CHOICE!"=="4" set "DEPTH=extra"

if not defined DEPTH (
    echo Invalid choice, using medium.
    set "DEPTH=medium"
)

echo.
set /p QUERY=Research question:

if "!QUERY!"=="" (
    echo Question cannot be empty.
    pause
    exit /b 1
)

for /f "tokens=1-6 delims=/:. " %%a in ("%DATE% %TIME%") do set "TASK_ID=research_%%c-%%b-%%a_%%d-%%e-%%f"
set "REPORT_DIR=task\deep-research\!TASK_ID!"
set "REPORT_FILE=!REPORT_DIR!\report.md"

mkdir "!REPORT_DIR!" 2>nul

set "PYTHONIOENCODING=utf-8"
set "PYTHONUNBUFFERED=1"

echo.
echo  Launch: depth=!DEPTH!
echo  Question: !QUERY!
echo  ID: !TASK_ID!
echo  Report: !REPORT_FILE!
echo.

cd /d "%~dp0Tools\mcp-web-search"
python -u -m services.deep_research "!QUERY!" --depth !DEPTH! --out "..\..\!REPORT_FILE!"
set "EXIT_CODE=!ERRORLEVEL!"
cd /d "%~dp0"

if not "!EXIT_CODE!"=="0" (
    echo.
    echo  === ERROR ===
    echo  Exit code: !EXIT_CODE!
    echo  Check logs: Tools\mcp-web-search\logs\deep_research.log
)

echo.
pause
