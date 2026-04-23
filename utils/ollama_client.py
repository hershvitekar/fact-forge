import logging
import requests

# Default llama.cpp port is 8080
LLAMA_CPP_URL = "http://192.168.1.18:8080"

def query_llama_cpp(prompt: str) -> str:
    """Send a prompt to the llama.cpp API and return the model output."""
    logging.info("Querying llama.cpp server at %s", LLAMA_CPP_URL)
    
    # llama.cpp uses 'prompt'. 
    # 'stream': False ensures we get a single JSON object back.
    payload = {
        "prompt": prompt,
        "stream": False,
        "n_predict": 400, # Optional: adjust max tokens to generate
    }
    
    # The native llama.cpp endpoint is /completion
    response = requests.post(f"{LLAMA_CPP_URL}/completion", json=payload)
    response.raise_for_status()
    
    data = response.json()
    
    # llama.cpp returns the text in the "content" field
    return data.get("content", "")

# Example usage:
# print(query_llama_cpp("Why is the sky blue?"))