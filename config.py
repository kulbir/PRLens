"""Shared configuration and utilities for PRLens."""

import functools
import json
import logging
import os
import re
import time

from dotenv import load_dotenv
from google import genai
from google.api_core.exceptions import (
    DeadlineExceeded,
    InternalServerError,
    ServiceUnavailable,
    TooManyRequests,
)
from pydantic import ValidationError

from models import ReviewResult

# ---------------------------------------------------------------------------
# Environment & logging (initialised once on first import)
# ---------------------------------------------------------------------------
load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
USE_MOCK: bool = os.getenv("USE_MOCK", "false").lower() == "true"
DEFAULT_MODEL: str = "gemini-2.5-flash-lite"

# Repo format: "owner/repo"
_REPO_PATTERN = re.compile(r"^[\w.-]+/[\w.-]+$")

# Gemini errors worth retrying (transient / rate-limit)
_RETRYABLE_GEMINI_ERRORS: tuple[type[Exception], ...] = (
    ServiceUnavailable,
    TooManyRequests,
    DeadlineExceeded,
    InternalServerError,
)


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------
def validate_repo(repo: str) -> str:
    """Validate repository string matches 'owner/repo' format.

    Returns *repo* unchanged on success; raises ``ValueError`` otherwise.
    """
    if not _REPO_PATTERN.match(repo):
        raise ValueError(
            f"Invalid repo format: {repo!r}. Expected 'owner/repo' "
            f"(e.g. 'kulbir/PRLens')."
        )
    return repo


# ---------------------------------------------------------------------------
# Retry decorator
# ---------------------------------------------------------------------------
def with_retry(
    max_retries: int = 3,
    base_delay: float = 1.0,
    retryable: tuple[type[Exception], ...] = (Exception,),
):
    """Decorator: retry a function with exponential back-off."""

    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            last_exc: Exception | None = None
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except retryable as exc:
                    last_exc = exc
                    if attempt < max_retries - 1:
                        delay = base_delay * (2**attempt)
                        logger.warning(
                            "Attempt %d/%d for %s failed: %s. Retrying in %.1fs…",
                            attempt + 1,
                            max_retries,
                            func.__name__,
                            exc,
                            delay,
                        )
                        time.sleep(delay)
            raise last_exc  # type: ignore[misc]

        return wrapper

    return decorator


# ---------------------------------------------------------------------------
# Cached API clients
# ---------------------------------------------------------------------------
@functools.lru_cache(maxsize=1)
def get_gemini_client() -> genai.Client:
    """Return a cached Gemini client (created once per process)."""
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY not found. Set it in .env file.")
    return genai.Client(api_key=api_key)


# ---------------------------------------------------------------------------
# Gemini API call (with retry)
# ---------------------------------------------------------------------------
@with_retry(max_retries=3, base_delay=2.0, retryable=_RETRYABLE_GEMINI_ERRORS)
def call_gemini(prompt: str, model: str = DEFAULT_MODEL) -> str:
    """Call Gemini and return the raw response text.

    Retries automatically on transient API errors.
    """
    client = get_gemini_client()
    response = client.models.generate_content(
        model=model,
        contents=prompt,
        config={"response_mime_type": "application/json"},
    )
    return response.text


# ---------------------------------------------------------------------------
# LLM response parsing
# ---------------------------------------------------------------------------
def parse_llm_json(text: str) -> ReviewResult | None:
    """Extract the first JSON object from *text* and validate as ReviewResult."""
    start = text.find("{")
    if start == -1:
        logger.warning("No JSON object found in LLM response")
        return None

    try:
        decoder = json.JSONDecoder()
        obj, _ = decoder.raw_decode(text[start:])
        return ReviewResult.model_validate(obj)
    except json.JSONDecodeError as e:
        logger.warning("JSON decode error: %s", e)
        return None
    except ValidationError as e:
        logger.warning("Pydantic validation error: %s", e)
        return None
