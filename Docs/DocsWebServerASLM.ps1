# =================================================================
# PowerShell Script: DocsWebServerASLM.ps1
#
# Checks for Chocolatey and Hugo Extended, then starts the Hugo
# development server for ASLM documentation.
#
# Re-launches as Administrator when elevation is required.
# =================================================================
param([switch]$Elevated)

function Test-Admin {
    $identity = [System.Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object System.Security.Principal.WindowsPrincipal($identity)
    return $principal.IsInRole([System.Security.Principal.WindowsBuiltInRole]::Administrator)
}

if (-not (Test-Admin)) {
    if ($Elevated) {
        Write-Warning "Failed to elevate to administrator privileges. Please run as Administrator."
        Read-Host "Press Enter to exit"
    } else {
        Start-Process powershell.exe -Verb RunAs -ArgumentList ('-ExecutionPolicy Bypass -NoProfile -File "{0}" -Elevated' -f ($myinvocation.MyCommand.Definition))
    }
    exit
}

$Host.UI.RawUI.WindowTitle = "ASLM Docs Web Server Launcher"
Clear-Host

$hugoProjectPath = Join-Path $PSScriptRoot "ASLM"

Write-Host "Checking for Chocolatey package manager..." -ForegroundColor Yellow
$chocoPath = Get-Command choco -ErrorAction SilentlyContinue
if (-not $chocoPath) {
    Write-Host "Chocolatey not found. Proceeding with installation." -ForegroundColor Cyan
    Write-Host "Installing Chocolatey... Please wait, this may take a few minutes." -ForegroundColor Cyan
    Set-ExecutionPolicy Bypass -Scope Process -Force
    [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor 3072
    iex ((New-Object System.Net.WebClient).DownloadString('https://community.chocolatey.org/install.ps1'))
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Chocolatey installation failed. Please try installing it manually from chocolatey.org"
        Read-Host "Press Enter to exit"
        exit 1
    }
    Write-Host "Chocolatey installed successfully." -ForegroundColor Green
    $env:Path = [Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [Environment]::GetEnvironmentVariable("Path","User")
} else {
    Write-Host "Chocolatey is already installed." -ForegroundColor Green
}

Write-Host ""
Write-Host "Checking for Hugo..." -ForegroundColor Yellow
$hugoPath = Get-Command hugo -ErrorAction SilentlyContinue
if (-not $hugoPath) {
    Write-Host "Hugo not found. Proceeding with installation." -ForegroundColor Cyan
    Write-Host "Installing Hugo (extended version)... This may take a moment." -ForegroundColor Cyan
    choco install hugo-extended -y
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Hugo installation failed. Please check your Chocolatey setup."
        Read-Host "Press Enter to exit"
        exit 1
    }
    Write-Host "Hugo installed successfully." -ForegroundColor Green
} else {
    Write-Host "Hugo is already installed." -ForegroundColor Green
}

Write-Host ""
Write-Host "Changing directory to Hugo project path: $hugoProjectPath" -ForegroundColor Yellow
Set-Location -Path $hugoProjectPath

Write-Host "All dependencies are met. Starting Hugo development server..." -ForegroundColor Yellow
Write-Host "Your site will be available at http://localhost:1313/" -ForegroundColor Cyan
Write-Host "Press Ctrl+C in this window to stop the server." -ForegroundColor Cyan
Write-Host ""

hugo server -D

Read-Host "Server stopped. Press Enter to exit."
