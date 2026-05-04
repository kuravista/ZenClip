"""
Unified LLM Provider for ZenClip

Supported providers:
- deepseek: DeepSeek API (default)
- openai: OpenAI GPT models
- gemini: Google Gemini API
- local: Local LLM via Ollama
- anthropic: Claude API
"""
import os
import requests
from openai import OpenAI


# Global variable to cache loaded model
_local_llm_model = None

# Provider configurations
PROVIDER_CONFIGS = {
    'deepseek': {
        'base_url': 'https://api.deepseek.com',
        'model': 'deepseek-chat',
        'api_key_env': 'DEEPSEEK_API_KEY'
    },
    'openai': {
        'base_url': 'https://api.openai.com',
        'model': 'gpt-4o-mini',  # Cost-effective
        'api_key_env': 'OPENAI_API_KEY'
    },
    'gemini': {
        'base_url': 'https://generativelanguage.googleapis.com/v1',
        'model': 'gemini-2.5-flash',
        'api_key_env': 'GEMINI_API_KEY'
    },
    'anthropic': {
        'base_url': 'https://api.anthropic.com',
        'model': 'claude-3-haiku-20240307',
        'api_key_env': 'ANTHROPIC_API_KEY'
    },
    'local': {
        'base_url': 'http://localhost:11434/v1',
        'model': 'mistral',
        'api_key_env': 'LOCAL_LLM_API_KEY'
    },
    'openrouter': {
        'base_url': 'https://openrouter.ai/api/v1',
        'model': 'meta-llama/llama-4-maverick',
        'api_key_env': 'OPENROUTER_API_KEY'
    }
}


def generate_llm_response(prompt, system_instruction, api_key, provider='deepseek', temperature=0.7, model=None):
    """
    Unified function to call LLM APIs with automatic fallback to OpenRouter.

    Fallback chain: primary provider -> openrouter (if primary fails with 429/5xx)

    Args:
        prompt (str): The user prompt.
        system_instruction (str): The system prompt/instruction.
        api_key (str): API Key for the provider.
        provider (str): 'deepseek', 'openai', 'gemini', 'anthropic', or 'local'.
        temperature (float): Sampling temperature.
        model (str): Optional model override.

    Returns:
        str: The text response from the LLM.
    """

    provider_lower = provider.lower()

    # Validate provider
    if provider_lower not in PROVIDER_CONFIGS:
        raise ValueError(
            f"Unknown provider: {provider}. "
            f"Supported: {list(PROVIDER_CONFIGS.keys())}"
        )

    config = PROVIDER_CONFIGS[provider_lower]

    # API key required for cloud providers
    if not api_key and provider_lower != 'local':
        # Try environment variable
        api_key = os.environ.get(config['api_key_env'])
        if not api_key:
            raise ValueError(
                f"API Key is required for {provider}. "
                f"Set via parameter or {config['api_key_env']} env var."
            )

    # Use specified model or default
    use_model = model or config['model']

    print(f"[INFO] Using {provider.upper()} API (Model: {use_model})")

    try:
        # Handle different providers
        if provider_lower == 'gemini':
            result = _call_gemini(prompt, system_instruction, api_key, use_model, temperature)
        elif provider_lower == 'anthropic':
            result = _call_anthropic(prompt, system_instruction, api_key, use_model, temperature)
        else:
            result = _call_openai_compatible(
                prompt, system_instruction, api_key,
                config['base_url'], use_model, temperature
            )
        return result
    except Exception as e:
        error_str = str(e)
        is_transient = any(code in error_str for code in ['429', '503', '500', '502', '504', 'UNAVAILABLE', 'overloaded', 'high demand', 'rate limit'])

        # Only fallback to OpenRouter if error is transient and not already using OpenRouter
        if is_transient and provider_lower != 'openrouter':
            openrouter_key = _get_openrouter_key()
            if openrouter_key:
                or_config = PROVIDER_CONFIGS['openrouter']
                or_model = or_config['model']
                print(f"[FALLBACK] {provider.upper()} failed ({error_str[:80]}...), retrying with OpenRouter ({or_model})")
                try:
                    return _call_openai_compatible(
                        prompt, system_instruction, openrouter_key,
                        or_config['base_url'], or_model, temperature
                    )
                except Exception as fallback_err:
                    print(f"[FALLBACK] OpenRouter also failed: {fallback_err}")
                    raise  # Raise original error if fallback also fails
            else:
                print(f"[WARN] {provider.upper()} failed but no OpenRouter key available for fallback")

        raise


def _get_openrouter_key():
    """Get OpenRouter API key from settings file or environment."""
    # 1. Try environment variable
    key = os.environ.get('OPENROUTER_API_KEY')
    if key:
        return key

    # 2. Try settings file
    try:
        import json
        settings_paths = ['user_settings.json']
        # Also check common locations
        home = os.path.expanduser('~')
        settings_paths.append(os.path.join(home, 'Documents', 'SnipieAI', 'user_settings.json'))

        for path in settings_paths:
            if os.path.exists(path):
                with open(path, 'r') as f:
                    settings = json.load(f)
                key = settings.get('openrouterApiKey') or settings.get('openrouter_api_key')
                if key:
                    return key
    except Exception:
        pass

    return None


def _call_openai_compatible(prompt, system_instruction, api_key, base_url, model, temperature):
    """Call OpenAI-compatible APIs (DeepSeek, OpenAI, Ollama, OpenRouter)."""
    try:
        client_kwargs = {
            'api_key': api_key or 'ollama',  # Ollama doesn't need real key
            'base_url': base_url,
        }

        # OpenRouter needs extra headers
        if 'openrouter.ai' in base_url:
            client_kwargs['default_headers'] = {
                'HTTP-Referer': 'https://zenclip.local',
                'X-Title': 'ZenClip',
            }

        client = OpenAI(**client_kwargs)

        create_kwargs = {
            'model': model,
            'messages': [
                {"role": "system", "content": system_instruction},
                {"role": "user", "content": prompt}
            ],
            'temperature': temperature,
            'stream': False,
        }

        # OpenRouter benefits from explicit max_tokens
        if 'openrouter.ai' in base_url:
            create_kwargs['max_tokens'] = 16000

        resp = client.chat.completions.create(**create_kwargs)

        content = resp.choices[0].message.content.strip()
        print(f"[SUCCESS] {model} Response received")
        return content

    except Exception as e:
        print(f"[ERROR] API Failed: {e}")
        raise e


def _call_gemini(prompt, system_instruction, api_key, model, temperature):
    """Call Google Gemini API."""
    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"

        payload = {
            "contents": [
                {
                    "parts": [
                        {"text": f"{system_instruction}\n\n{prompt}"}
                    ]
                }
            ],
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": 16384
            }
        }

        resp = requests.post(url, json=payload, timeout=120)

        if resp.status_code != 200:
            raise ValueError(f"Gemini API Error {resp.status_code}: {resp.text}")

        data = resp.json()
        content = data['candidates'][0]['content']['parts'][0]['text'].strip()

        print(f"[SUCCESS] Gemini Response received")
        return content

    except Exception as e:
        print(f"[ERROR] Gemini API Failed: {e}")
        raise e


def _call_anthropic(prompt, system_instruction, api_key, model, temperature):
    """Call Anthropic Claude API."""
    try:
        url = "https://api.anthropic.com/v1/messages"

        headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json"
        }

        payload = {
            "model": model,
            "max_tokens": 4096,
            "system": system_instruction,
            "messages": [
                {"role": "user", "content": prompt}
            ],
            "temperature": temperature
        }

        resp = requests.post(url, headers=headers, json=payload, timeout=120)

        if resp.status_code != 200:
            raise ValueError(f"Anthropic API Error {resp.status_code}: {resp.text}")

        data = resp.json()
        content = data['content'][0]['text'].strip()

        print(f"[SUCCESS] Claude Response received")
        return content

    except Exception as e:
        print(f"[ERROR] Anthropic API Failed: {e}")
        raise e


# Convenience functions
def test_api_connection(provider, api_key):
    """Test if API connection works."""
    try:
        result = generate_llm_response(
            prompt="Say 'Hello' in one word.",
            system_instruction="You are a helpful assistant.",
            api_key=api_key,
            provider=provider
        )
        return True, result
    except Exception as e:
        return False, str(e)


def get_available_providers():
    """Get list of available providers."""
    return list(PROVIDER_CONFIGS.keys())
