import logging
import requests
import config

def query_llm(prompt: str, n_predict: int = 512) -> str:
    """
    Send a prompt to the llama.cpp API and return the model output.
    
    Args:
        prompt: The text to send to the model.
        n_predict: The maximum number of tokens the model should generate.
    """
    url = getattr(config, "LLM_URL", "http://192.168.1.18:8080")
    logging.info("Querying LLM at %s", url)
    
    payload = {
        "prompt": prompt,
        "stream": False,
        "n_predict": n_predict,
        "temperature": 0.0,      # Forces deterministic output for higher accuracy
        "cache_prompt": True,    # Significant speed-up by caching prompt context
        "top_p": 0.95,
        "top_k": 40,
        "repeat_penalty": 1.1,   # Prevents the model from getting stuck in loops
    }
    
    try:
        response = requests.post(f"{url}/completion", json=payload, timeout=None)
        response.raise_for_status()
        data = response.json()
        return data.get("content", "").strip()
    except Exception as e:
        logging.error("Error querying LLM: %s", e)
        return ""
