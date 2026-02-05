import os
import sys
import json
import re
import logging

from google import genai
from google.api_core.exceptions import GoogleAPIError
from dotenv import load_dotenv

from mock_data import MOCK_RESPONSE
from prompts import REVIEW_PROMPT
from models import ReviewResult

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


def parse_response(text: str) -> ReviewResult | None:
    """Parse Gemini response, stripping markdown and handling errors."""
    # Remove markdown code block wrapper if present
    cleaned = re.sub(r'^```(?:json)?\s*|\s*```$', '', text.strip())
    
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as e:
        logger.warning(f"Failed to parse JSON: {e}")
        logger.debug(f"Raw response: {text}")
        return None


def analyze_code(code: str, model: str = DEFAULT_MODEL) -> ReviewResult | None:
    """Send code to Gemini for analysis and return parsed result."""
    client = genai.Client(api_key=get_api_key())
    
    prompt = REVIEW_PROMPT.format(code=code)
    
    response = client.models.generate_content(
        model=model,
        contents=prompt
    )
    return parse_response(response.text)


def print_findings(result: ReviewResult) -> None:
    """Pretty print the review findings."""
    print(f"\n📋 Summary: {result.get('summary', 'N/A')}\n")
    
    for finding in result.get("findings", []):
        severity = finding.get("severity", "?")
        category = finding.get("category", "?")
        line = finding.get("line", "?")
        desc = finding.get("description", "No description")
        fix = finding.get("fix", "No fix provided")
        
        icon = {"bug": "🐛", "security": "🔒", "performance": "⚡", "pep8": "📐"}.get(category, "❓")
        
        print(f"{icon} [{severity}] Line {line}: {desc}")
        print(f"   💡 Fix: {fix}\n")


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
        result = parse_response(MOCK_RESPONSE)
        if result:
            print_findings(result)
        else:
            print("Failed to parse mock response")
        return 0

    try:
        result = analyze_code(code_to_analyze)
        if result:
            print_findings(result)
        else:
            logger.error("Failed to parse Gemini response")
            return 1
        return 0

    except ValueError as e:
        logger.error(f"Configuration error: {e}")
        return 1
    except GoogleAPIError as e:
        logger.error(f"API error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())