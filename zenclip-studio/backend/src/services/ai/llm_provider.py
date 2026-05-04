import os
from openai import OpenAI



# Global variable to cache loaded model
_local_llm_model = None

def generate_llm_response(prompt, system_instruction, api_key, provider='deepseek', temperature=0.7):
    """
    Unified function to call LLM APIs.
    
    Args:
        prompt (str): The user prompt.
        system_instruction (str): The system prompt/instruction.
        api_key (str): API Key for the provider (not required for 'local').
        provider (str): 'deepseek' or 'local'.
        
    Returns:
        str: The text response from the LLM.
    """
    
    # API key required for cloud providers
    if not api_key:
        raise ValueError(f"API Key is required for {provider}")

    if provider.lower() == 'local':
        import openai
        # Default to Ollama standard port
        local_base_url = os.environ.get('LOCAL_LLM_URL', 'http://localhost:11434/v1')
        local_api_key = os.environ.get('LOCAL_LLM_API_KEY', 'ollama')
        # Default model for general tasks
        local_model = os.environ.get('LOCAL_LLM_MODEL', 'mistral')
        
        print(f"[INFO] Using Local LLM at {local_base_url} (Model: {local_model})")
        
        try:
            client = openai.OpenAI(api_key=local_api_key, base_url=local_base_url)
            resp = client.chat.completions.create(
                model=local_model,
                messages=[
                    {"role": "system", "content": system_instruction},
                    {"role": "user", "content": prompt}
                ],
                temperature=temperature,
                stream=False
            )
            return resp.choices[0].message.content
        except Exception as e:
            print(f"[ERROR] Local LLM Failed: {e}")
            raise e

    else: # Default to DeepSeek
        print(f"[INFO] Connecting to DeepSeek API (via requests)...")
        import requests
        
        try:
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            }
            
            payload = {
                "model": "deepseek-chat",
                "messages": [
                    {"role": "system", "content": system_instruction},
                    {"role": "user", "content": prompt}
                ],
                "temperature": temperature,
                "stream": False
            }
            
            # Use requests with explicit timeout
            resp = requests.post(
                "https://api.deepseek.com/chat/completions",
                headers=headers,
                json=payload,
                timeout=120
            )
            
            if resp.status_code != 200:
                raise ValueError(f"API Error {resp.status_code}: {resp.text}")
                
            data = resp.json()
            content = data['choices'][0]['message']['content'].strip()
            
            print(f"[SUCCESS] DeepSeek Response received")
            return content
            
        except Exception as e:
            print(f"[ERROR] DeepSeek API Failed: {e}")
            raise e


