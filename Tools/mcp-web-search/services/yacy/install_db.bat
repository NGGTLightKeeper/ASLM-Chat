@echo off
echo Installing required dependencies...
pip install huggingface_hub

echo.
echo Starting YaCy database download from Hugging Face...
python download_hf.py

echo.
echo Press any key to exit...
pause >nul
