import os
import sys
import logging

from google import genai
from google.api_core.exceptions import GoogleAPIError
from dotenv import load_dotenv

from mock_data import MOCK_RESPONSE
from prompts import REVIEW_PROMPT

load_dotenv()

# Configuration
USE_MOCK = os.getenv("USE_MOCK", "false").lower() == "true"
DEFAULT_MODEL = "gemini-2.5-flash-lite"

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def get_api_key():
    """Get API key from environment, fail fast if missing."""
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError(
            "GEMINI_API_KEY not found. Set it in .env file."
        )
    return api_key


def analyze_code(code: str, model: str = DEFAULT_MODEL) -> str:
    """Send code to Gemini for analysis and return the response."""
    client = genai.Client(api_key=get_api_key())
    
    prompt = REVIEW_PROMPT.format(code=code)
    
    response = client.models.generate_content(
        model=model,
        contents=prompt
    )
    return response.text


def main() -> int:
    """Main entry point."""
    code_to_analyze = """
def calculate_average(numbers):
    total = sum(numbers)
    return total / len(numbers)
    """

    logger.info("Starting code analysis...")

    if USE_MOCK:
        logger.info("[MOCK MODE - No API call made]")
        print("\nGemini's Response:")
        print(MOCK_RESPONSE)
        return 0

    try:
        result = analyze_code(code_to_analyze)
        print("\nGemini's Response:")
        print(result)
        return 0

    except ValueError as e:
        logger.error(f"Configuration error: {e}")
        return 1
    except GoogleAPIError as e:
        logger.error(f"API error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())