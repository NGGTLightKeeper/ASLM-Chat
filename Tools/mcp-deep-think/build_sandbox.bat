@echo off
setlocal

set IMAGE_NAME=dima1312313/deep-think-sandbox:latest
set CONTAINER_NAME=deep-think-sandbox

echo [deep-think-sandbox] Building image: %IMAGE_NAME%
docker build -t %IMAGE_NAME% "%~dp0."

if %ERRORLEVEL% neq 0 (
    echo [ERROR] Build failed.
    pause
    exit /b 1
)

echo.
echo [deep-think-sandbox] Build successful.
echo.

echo [deep-think-sandbox] Image size:
docker image inspect %IMAGE_NAME% --format "  {{.Size}} bytes  (~{{div .Size 1048576}} MB)"

echo.
set /p PUSH="Push to Docker Hub? (y/n): "
if /i "%PUSH%"=="y" (
    echo Pushing %IMAGE_NAME% ...
    docker push %IMAGE_NAME%
    if not %ERRORLEVEL% == 0 (
        echo [ERROR] Push failed. Make sure you are logged in: docker login
    ) else (
        echo [OK] Pushed successfully.
    )
)

echo.
echo Done.
pause
