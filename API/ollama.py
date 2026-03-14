import logging
import ollama
from Settings import settings

logger = logging.getLogger(__name__)

def get_client() -> ollama.Client:
    """
    Creates and returns an Ollama client configured with the host and port 
    from the ASLM settings for the ollama-service engine.
    """
    # The default port is 30002 as per ASLM_Module.json
    port = settings.get('ollama-service_port', 30002)
    host = f"http://127.0.0.1:{port}"
    return ollama.Client(host=host)

def get_models():
    """
    Returns a list of downloaded models via ollama.list().
    """
    client = get_client()
    try:
        response = client.list()
        # response['models'] contains a list of dictionary model descriptions
        return response.get('models', [])
    except Exception as e:
        logger.error(f"[Ollama API] Error listing models: {e}")
        return []

def download_model(model_name: str, **kwargs):
    """
    Downloads (pulls) a model from the Ollama registry.
    Optional kwargs: 
        stream (bool) - if True, yields progress objects.
    """
    client = get_client()
    stream = kwargs.get('stream', False)
    try:
        # If stream=True, this returns an Iterator
        return client.pull(model_name, stream=stream)
    except Exception as e:
        logger.error(f"[Ollama API] Error downloading model {model_name}: {e}")
        raise

def generate(model_name: str, messages: list, **kwargs):
    """
    Generates a response using the specified model via the chat endpoint.
    Accepts a list of message dicts: [{'role': 'user'/'assistant'/'system', 'content': '...'}, ...]
    Optional kwargs:
        stream (bool)
        options (dict) - generation parameters (temperature, num_ctx, etc.)
        think (bool) - enable/disable thinking (top-level Ollama param)
        think_level (str) - thinking effort level: low / medium / high
        format (str) - return format (e.g. 'json')
        images (list) - list of base64 image strings (for the last user message)
    """
    client = get_client()
    try:
        # 'think' is a top-level param for client.chat()
        # 'think_level' (and similar) must go into 'options' dict
        think = kwargs.pop('think', None)
        think_level = kwargs.pop('think_level', None)

        # Build call kwargs (drop legacy single-turn params if any)
        call_kwargs = {k: v for k, v in kwargs.items() if k not in ('system', 'prompt')}

        # Pass 'think' at top level — supported by ollama-python client
        if think is not None:
            call_kwargs['think'] = think

        # Pass 'think_level' inside options — it's a generation option, not a client kwarg
        if think_level is not None:
            opts = call_kwargs.setdefault('options', {})
            if isinstance(opts, dict):
                opts['think_level'] = think_level

        return client.chat(model=model_name, messages=messages, **call_kwargs)
    except Exception as e:
        logger.error(f"[Ollama API] Error generating response from {model_name}: {e}")
        raise

def get_model_settings(model_name: str):
    """
    Retrieves information about a specific model (Modelfile, parameters, template).
    """
    client = get_client()
    try:
        return client.show(model_name)
    except Exception as e:
        logger.error(f"[Ollama API] Error fetching settings for model {model_name}: {e}")
        raise
