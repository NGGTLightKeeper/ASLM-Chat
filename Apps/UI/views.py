import sys, os
sys.path.insert(0, os.path.join(os.getcwd()))

from django.shortcuts import render
from django.views.generic import TemplateView, DetailView, ListView
from django.http import JsonResponse, StreamingHttpResponse
from django.views.decorators.csrf import csrf_exempt
import json
from ..Data.models import *
from API import llm_api
from Settings import settings

# Main Page
class main(TemplateView):
    template_name = 'main/main.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Fetch available models if ollama-service is active
        models = []
        if settings.get('ollama-service'):
            try:
                models_data = llm_api.get_models('ollama-service')
                # extract model names (Ollama python client returns 'model' key for the name)
                models = [m.get('model') for m in models_data]
            except Exception as e:
                print(f"[ASLM-Chat UI] Error getting models: {e}")
        context['models'] = models
        
        # Fetch existing chats for sidebar
        context['chats'] = Chat.objects.all()
        return context

def chat_api(request):
    """
    Receives JSON payload via POST, interacts with llm_api, 
    saves messages to DB, and returns the AI reply.
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'Invalid request method'}, status=405)

    try:
        data = json.loads(request.body)
        user_message = data.get('message', '')
        model_name = data.get('model', '')
        system_prompt = data.get('system_prompt', '')
        options = data.get('options', {})
        chat_id = data.get('chat_id', '')

        if not user_message or not model_name:
            return JsonResponse({'error': 'Missing message or model parameter'}, status=400)
            
        # Get or create chat
        if chat_id:
            try:
                chat = Chat.objects.get(id=chat_id)
            except Chat.DoesNotExist:
                return JsonResponse({'error': 'Chat not found'}, status=404)
        else:
            # Create a new chat, generate a title automatically from the first few words
            title = user_message[:30] + ('...' if len(user_message) > 30 else '')
            chat = Chat.objects.create(title=title)
            
        # Save user message to DB
        Message.objects.create(chat=chat, role='user', content=user_message)

        # Build prompt considering system prompt if available
        # Currently the llm_api wrapper expects a simple string or standard ollama params.
        # We'll pass the options up as kwargs to the generator.
        
        # Prepare kwargs for generate
        generate_kwargs = {
            'engine': 'ollama-service',
            'model_name': model_name,
            'prompt': user_message,
            'system': system_prompt,
            'stream': True
        }
        
        # Merge options
        if options:
            generate_kwargs['options'] = options

        # Call the LLM Wrapper with stream=True
        # We will yield plain text chunks back to the client
        def stream_response():
            full_response = ""
            try:
                # generate() with stream=True returns an iterator from ollama
                response_iterator = llm_api.generate(**generate_kwargs)
                for chunk in response_iterator:
                    if 'response' in chunk:
                        text_part = chunk['response']
                        full_response += text_part
                        yield text_part
            except Exception as e:
                print(f"Error during streaming: {e}")
                yield f"\n[Error during generation: {str(e)}]"
            finally:
                # Once streaming is done (or fails), save the full response to DB
                if full_response:
                    Message.objects.create(chat=chat, role='assistant', content=full_response)

        response = StreamingHttpResponse(stream_response(), content_type='text/plain; charset=utf-8')
        # Inject custom header so frontend knows the chat ID
        response['X-Chat-ID'] = str(chat.id)
        return response

    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON format'}, status=400)
    except Exception as e:
        print(f"Exception in chat_api: {e}")
        return JsonResponse({'error': str(e)}, status=500)


def load_chat_api(request, chat_id):
    """
    Loads historical messages for a specific chat ID.
    """
    if request.method != 'GET':
        return JsonResponse({'error': 'Invalid request method'}, status=405)
        
    try:
        chat = Chat.objects.get(id=chat_id)
        messages = chat.messages.all()
        msg_list = [{'role': m.role, 'content': m.content} for m in messages]
        
        return JsonResponse({'chat_id': str(chat.id), 'title': chat.title, 'messages': msg_list})
    except Chat.DoesNotExist:
        return JsonResponse({'error': 'Chat not found'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

def get_model_info_api(request):
    """
    Returns settings for a specific model, parsing the metadata 
    to extract actual maximum context lengths and other dynamic bounds.
    """
    if request.method != 'GET':
        return JsonResponse({'error': 'Invalid request method'}, status=405)
        
    model_name = request.GET.get('model', '')
    if not model_name:
        return JsonResponse({'error': 'Model parameter is required'}, status=400)
        
    try:
        settings_data = llm_api.get_model_settings('ollama-service', model_name)
        # Ollama's show method returns a dictionary directly with python-ollama API
        # but the structure can be nested depending on the dict fields parsing
        # we are looking specifically for modelinfo attributes
        
        # Safe default fallbacks
        context_length = 8192
        defaults = {}
        
        # In `ollama` python client, `show` returns a mapping directly with 'modelinfo' and 'parameters'
        modelinfo = {}
        parameters_str = ""
        
        if isinstance(settings_data, dict):
            modelinfo = settings_data.get('modelinfo', {})
            parameters_str = settings_data.get('parameters', "")
        else:
            modelinfo = getattr(settings_data, 'modelinfo', {})
            parameters_str = getattr(settings_data, 'parameters', "")
            
        # Parse looking for context length
        for key, value in modelinfo.items():
            if key.endswith('.context_length'):
                try:
                    context_length = int(value)
                except ValueError:
                    pass
                break # Found the typical context_length key
                
        # Parse the parameters string into a dictionary
        if parameters_str:
            lines = parameters_str.strip().split('\n')
            for line in lines:
                parts = line.strip().split()
                if len(parts) >= 2:
                    k = parts[0].strip().lower()
                    # Values might have spaces if they are strings, join them back, but usually they are numbers
                    v = " ".join(parts[1:]).strip()
                    try:
                        # Try int
                        defaults[k] = int(v)
                    except ValueError:
                        try:
                            # Try float
                            defaults[k] = float(v)
                        except ValueError:
                            # Keep as string
                            defaults[k] = v
                
        return JsonResponse({
            'model': model_name,
            'context_length': context_length,
            'defaults': defaults
        })
    except Exception as e:
        print(f"[ASLM-Chat UI] Error getting model info for {model_name}: {e}")
        return JsonResponse({'error': str(e)}, status=500)

# Profile Page
class profile(TemplateView):
    template_name = 'main/profile.html'
