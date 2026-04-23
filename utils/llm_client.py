"""
LLM client — Google Gemini API via the google-genai SDK.

All pipeline modules call `query_llm()` so this is the single integration
point.  Swap the backend here and the rest of the pipeline is unaffected.

Requires the GOOGLE_API_KEY environment variable to be set.
"""

import logging
import os
import time
from pathlib import Path

from dotenv import load_dotenv
from google import genai
from google.genai import types

# Load .env from the project root (one level up from utils/)
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

import config

# ── Lazy singleton client ─────────────────────────────────────────────────────
_client = None


def _get_client():
    """Initialise the Gemini client once (reads GOOGLE_API_KEY from env)."""
    global _client
    if _client is None:
        api_key = os.environ.get("GOOGLE_API_KEY", "")
        if not api_key:
            raise RuntimeError(
                "GOOGLE_API_KEY environment variable is not set. "
                "Get one at https://aistudio.google.com/apikey"
            )
        _client = genai.Client(api_key=api_key)
    return _client


def query_llm(
    prompt: str,
    *,
    system_prompt: str | None = None,
    max_tokens: int = 8192,
) -> str:
    """
    Send a prompt to the Google Gemini API and return the model output.

    Args:
        prompt:        User-facing text to send to the model.
        system_prompt: Optional system instruction (sets context / persona).
        max_tokens:    Maximum number of tokens in the response.
    """
    model = getattr(config, "GEMINI_MODEL", "gemini-2.5-flash")
    logging.info("Querying Gemini model: %s", model)

    gen_config = types.GenerateContentConfig(
        temperature=0.2,
        max_output_tokens=max_tokens,
        top_p=0.95,
        top_k=40,
    )

    if system_prompt:
        gen_config.system_instruction = system_prompt

    MAX_RETRIES = 3
    client = _get_client()

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = client.models.generate_content(
                model=model,
                contents=prompt,
                config=gen_config,
            )
            return response.text.strip() if response.text else ""
        except Exception as e:
            error_str = str(e)
            # Retry on rate-limit (429) errors
            if "429" in error_str or "RESOURCE_EXHAUSTED" in error_str:
                # Try to parse the retry delay from the error message
                wait_time = 15  # default wait
                if "retryDelay" in error_str:
                    import re
                    match = re.search(r'"retryDelay":\s*"(\d+)', error_str)
                    if match:
                        wait_time = int(match.group(1)) + 2  # add buffer
                logging.warning(
                    "Rate limited (attempt %d/%d). Waiting %ds before retry...",
                    attempt, MAX_RETRIES, wait_time,
                )
                time.sleep(wait_time)
                continue
            # Non-retryable error
            logging.error("Error querying Gemini: %s", e)
            return ""

    logging.error("All %d retry attempts exhausted due to rate limiting.", MAX_RETRIES)
    return ""
