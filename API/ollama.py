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

def generate(model_name: str, prompt: str, **kwargs):
    """
    Generates a response using the specified model.
    Optional kwargs:
        stream (bool)
        options (dict) - generation parameters (temperature, num_ctx, etc.)
        system (str) - custom system prompt
        context (list) - context from previous interaction
        format (str) - return format (e.g. 'json')
    """
    client = get_client()
    try:
        return client.generate(model=model_name, prompt=prompt, **kwargs)
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
