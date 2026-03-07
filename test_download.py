import os
import sys

# Ensure the ASLM-Chat base directory is in sys.path so we can import API and Settings properly
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from API import llm_api

def run():
    print("Testing Model Download via llm_api...")
    
    engine = 'ollama-service'
    model_name = 'gpt-oss:20b'
    
    print(f"\n[1] Checking currently downloaded models in {engine}...")
    try:
        models = llm_api.get_models(engine)
        print(f"  Found {len(models)} models:")
        for m in models:
            print(f"  - {m.get('model')}")
    except Exception as e:
        print(f"Error getting models: {e}")
        return

    print(f"\n[2] Attempting to pull '{model_name}'...")
    try:
        # stream=True returns an iterator. 
        # For a quick test script, we will iterate and print progress.
        progress_iterator = llm_api.download_model(engine, model_name, stream=True)
        for chunk in progress_iterator:
            status = chunk.get('status', '')
            completed = chunk.get('completed') or 0
            total = chunk.get('total') or 0
            
            if total > 0 and 'downloading' in status.lower():
                percent = (completed / total) * 100
                print(f"\r  Progress: {percent:.1f}% ({status})", end="", flush=True)
            else:
                print(f"\r  Status: {status}".ljust(50), end="", flush=True)
                
        print("\n\n  [OK] Download complete!")
    except Exception as e:
        print(f"\n  [ERROR] Error downloading model: {e}")
        return

    print(f"\n[3] Testing simple generation with '{model_name}'...")
    try:
        response = llm_api.generate(
            engine=engine,
            model_name=model_name,
            prompt="Reply with exactly 'Download Test OK'.",
            stream=False
        )
        print(f"  Response: {response.get('response')}")
    except Exception as e:
        print(f"  [ERROR] Error generating response: {e}")


if __name__ == "__main__":
    run()
