@echo off
setlocal EnableDelayedExpansion

set IMAGE=dima1312313/mcp-sandbox:latest
set CONTAINER=mcp-sandbox
set WORKSPACE=%~dp0..\..\..
set CONTAINER_WORKSPACE=/workspace
set CPU_LIMIT=1
set MEMORY_LIMIT=3g
set MEMORY_SWAP_LIMIT=4g
set PIDS_LIMIT=256

echo ===================================================
echo  MCP Sandbox Setup
echo ===================================================
echo.

:: Check Docker CLI
docker --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Docker CLI not found. Install Docker Desktop first.
    goto end
)
echo [OK] Docker CLI found.

:: Check Docker daemon
docker info >nul 2>&1
if not errorlevel 1 goto daemon_ready

echo [INFO] Docker daemon not running. Starting Docker Desktop...
set DOCKER_EXE=
if exist "%ProgramFiles%\Docker\Docker\Docker Desktop.exe" set DOCKER_EXE=%ProgramFiles%\Docker\Docker\Docker Desktop.exe
if exist "%LocalAppData%\Docker\Docker Desktop.exe" set DOCKER_EXE=%LocalAppData%\Docker\Docker Desktop.exe

if "!DOCKER_EXE!"=="" (
    echo [ERROR] Docker Desktop not found. Install or start it manually.
    goto end
)

start "" "!DOCKER_EXE!"
echo [INFO] Waiting for Docker daemon (up to 60 seconds)...
set /a WAIT=0

:wait_loop
timeout /t 2 /nobreak >nul
set /a WAIT+=2
docker info >nul 2>&1
if not errorlevel 1 goto daemon_ready
if !WAIT! geq 60 (
    echo [ERROR] Docker daemon did not respond in 60 seconds. Try again later.
    goto end
)
goto wait_loop

:daemon_ready
echo [OK] Docker daemon is running.

:: Check / pull image
echo.
docker image inspect %IMAGE% >nul 2>&1
if not errorlevel 1 (
    echo [OK] Image "%IMAGE%" already exists locally.
    goto check_container
)

echo [INFO] Pulling image "%IMAGE%" from Docker Hub...
docker pull %IMAGE%
if not errorlevel 1 (
    echo [OK] Image pulled successfully.
    goto check_container
)

echo [WARN] Pull failed. Trying to build from Dockerfile...
if not exist "%~dp0Dockerfile" (
    echo [ERROR] Dockerfile not found at %~dp0Dockerfile
    goto end
)
docker build -t %IMAGE% "%~dp0"
if errorlevel 1 (
    echo [ERROR] Image build failed.
    goto end
)
echo [OK] Image built locally.

:check_container
:: Normalize workspace path (remove trailing backslash)
set WS=%WORKSPACE%
if "!WS:~-1!"=="\" set WS=!WS:~0,-1!

echo.
set RUNNING=
set EXISTS=
for /f %%i in ('docker ps -q -f "name=^%CONTAINER%$" 2^>nul') do set RUNNING=%%i
if defined RUNNING (
    echo [OK] Container "%CONTAINER%" is already running.
    goto done
)

for /f %%i in ('docker ps -aq -f "name=^%CONTAINER%$" 2^>nul') do set EXISTS=%%i
if defined EXISTS (
    echo [INFO] Starting existing container "%CONTAINER%"...
    docker start %CONTAINER%
    if errorlevel 1 (
        echo [ERROR] Failed to start container.
        goto end
    )
    echo [OK] Container started.
    goto done
)

echo [INFO] Creating and starting container "%CONTAINER%"...
docker run -d ^
    --name %CONTAINER% ^
    --restart unless-stopped ^
    --cpus %CPU_LIMIT% ^
    --memory %MEMORY_LIMIT% ^
    --memory-swap %MEMORY_SWAP_LIMIT% ^
    --pids-limit %PIDS_LIMIT% ^
    --no-healthcheck ^
    --gpus all ^
    -v "%WS%:%CONTAINER_WORKSPACE%" ^
    -w %CONTAINER_WORKSPACE% ^
    %IMAGE% tail -f /dev/null

if not errorlevel 1 goto done

echo [WARN] Failed with --gpus all, retrying without GPU...
docker run -d ^
    --name %CONTAINER% ^
    --restart unless-stopped ^
    --cpus %CPU_LIMIT% ^
    --memory %MEMORY_LIMIT% ^
    --memory-swap %MEMORY_SWAP_LIMIT% ^
    --pids-limit %PIDS_LIMIT% ^
    --no-healthcheck ^
    -v "%WS%:%CONTAINER_WORKSPACE%" ^
    -w %CONTAINER_WORKSPACE% ^
    %IMAGE% tail -f /dev/null

if errorlevel 1 (
    echo [ERROR] Failed to create container.
    goto end
)

:done
echo.
echo ===================================================
echo  Sandbox ready!
echo  Container : %CONTAINER%
echo  Image     : %IMAGE%
echo  Workspace : %WS% -^> %CONTAINER_WORKSPACE%
echo ===================================================
goto end

:end
echo.
pause
