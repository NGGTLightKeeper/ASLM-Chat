@echo off
TITLE Start ASLM Docs Web Server

:: =================================================================
:: Batch Script: StartDocsWebServerASLM.bat
::
:: Launches DocsWebServerASLM.ps1 to start the Hugo documentation
:: development server for ASLM.
:: =================================================================

ECHO Launching the ASLM documentation web server...
ECHO.

powershell.exe -ExecutionPolicy Bypass -File "%~dp0DocsWebServerASLM.ps1"
