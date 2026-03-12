import os
import subprocess
import logging
import threading
from Settings import settings

logger = logging.getLogger(__name__)

# Keep track of the process to avoid garbage collection and allow future termination if needed
_ollama_process = None

def start_ollama() -> None:
    """
    Reads ASLM configurations and starts the Ollama executable in a background process
    if the 'ollama-service' setting is enabled.
    """
    global _ollama_process

    if not settings.get('ollama-service', False):
        return
        
    ollama_path = settings.get('ollama-service_path')
    if not ollama_path or not os.path.exists(ollama_path):
        print(f"[ASLM-Chat] Ollama service is enabled but not found at: {ollama_path}")
        return
        
    ollama_data = settings.get('ollama-service_data')
    ollama_models = settings.get('ollama-service_models')
    ollama_port = settings.get('ollama-service_port', 30002)
    
    # Prepare environment variables for Ollama
    env = os.environ.copy()
    env['OLLAMA_HOST'] = f"127.0.0.1:{ollama_port}"
    if ollama_data:
        # According to Ollama docs, OLLAMA_MODELS configures the location for models
        # and there isn't a direct "data" folder variable unless it's just the root for models.
        # ASLM separates data and models. The primary environment variable is OLLAMA_MODELS.
        pass # Not natively used by ollama unless combined with models
        
    if ollama_models:
        env['OLLAMA_MODELS'] = str(ollama_models)
        
    print(f"[ASLM-Chat] Starting local Ollama service on port {ollama_port}...")
    
    try:
        # Start Ollama serve in the background
        # Use CREATE_NO_WINDOW on windows so it doesn't pop up an extra console
        creationflags = 0
        if os.name == 'nt':
            creationflags = subprocess.CREATE_NO_WINDOW
            
        args = [ollama_path, "serve"]
        
        _ollama_process = subprocess.Popen(
            args,
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=creationflags
        )
        print(f"[ASLM-Chat] Ollama service started successfully (PID: {_ollama_process.pid})")
    except Exception as e:
        print(f"[ASLM-Chat] Failed to start Ollama service: {e}")
