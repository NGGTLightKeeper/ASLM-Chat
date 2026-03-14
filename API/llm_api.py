import importlib
import logging

logger = logging.getLogger(__name__)

# Map engine identifiers to python modules inside the API folder
ENGINE_MODULES = {
    'ollama': 'API.ollama',
    'ollama-service': 'API.ollama', # Standard ASLM ID
    'lms': 'API.lms',               # For future use
}

def _get_engine_module(engine: str):
    """
    Dynamically loads and returns the python module for the given engine ID.
    Raises ValueError if unsupported, or ImportError if loading fails.
    """
    engine_lower = engine.lower()
    module_name = ENGINE_MODULES.get(engine_lower)
    
    if not module_name:
        raise ValueError(f"Unsupported LLM engine: {engine}")
    
    try:
        return importlib.import_module(module_name)
    except ImportError as e:
        logger.error(f"Failed to load engine module {module_name}: {e}")
        raise ImportError(f"Failed to load engine module {module_name}: {e}")

def get_models(engine: str):
    """
    Returns a list of available (downloaded) models for the specified engine.
    """
    module = _get_engine_module(engine)
    if hasattr(module, 'get_models'):
        return module.get_models()
    raise NotImplementedError(f"Engine {engine} does not implement get_models")

def download_model(engine: str, model_name: str, **kwargs):
    """
    Downloads (or pulls) the specified model. Returns engine-specific response or stream.
    """
    module = _get_engine_module(engine)
    if hasattr(module, 'download_model'):
        return module.download_model(model_name, **kwargs)
    raise NotImplementedError(f"Engine {engine} does not implement download_model")

def generate(engine: str, model_name: str, messages: list, **kwargs):
    """
    Generates a response from the specified model using the conversation history.
    messages - list of dicts: [{'role': 'user'/'assistant'/'system', 'content': '...'}, ...]
    kwargs can contain parameters like 'stream', 'options', 'think', 'think_level', etc.
    """
    module = _get_engine_module(engine)
    if hasattr(module, 'generate'):
        return module.generate(model_name, messages, **kwargs)
    raise NotImplementedError(f"Engine {engine} does not implement generate")

def get_model_settings(engine: str, model_name: str):
    """
    Retrieves the settings, parameters, or Modelfile for the specified model.
    """
    module = _get_engine_module(engine)
    if hasattr(module, 'get_model_settings'):
        return module.get_model_settings(model_name)
    raise NotImplementedError(f"Engine {engine} does not implement get_model_settings")
