"""PRLens — simple CLI entry point for quick code analysis."""

import sys
import logging

from google.api_core.exceptions import GoogleAPIError

from config import USE_MOCK, DEFAULT_MODEL, call_gemini, parse_llm_json
from mock_data import MOCK_RESPONSE
from prompts import REVIEW_PROMPT
from models import ReviewResult

logger = logging.getLogger(__name__)


def analyze_code(code: str, model: str = DEFAULT_MODEL) -> ReviewResult | None:
    """Send code to Gemini for analysis and return parsed result."""
    prompt = REVIEW_PROMPT.format(code=code)
    text = call_gemini(prompt, model)
    return parse_llm_json(text)


def print_findings(result: ReviewResult) -> None:
    """Pretty print the review findings."""
    print(f"\n📋 Summary: {result.summary or 'N/A'}\n")

    for finding in result.findings:
        icon = {
            "bug": "🐛",
            "security": "🔒",
            "performance": "⚡",
            "pep8": "📐",
            "style": "📐",
            "quality": "📐",
        }.get(finding.category, "❓")

        line_str = finding.line if finding.line is not None else "?"
        print(f"{icon} [{finding.severity}] Line {line_str}: {finding.description}")
        print(f"   💡 Fix: {finding.fix or 'No fix provided'}\n")


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
        result = parse_llm_json(MOCK_RESPONSE)
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
        logger.error("Configuration error: %s", e)
        return 1
    except GoogleAPIError as e:
        logger.error("API error: %s", e)
        return 1


if __name__ == "__main__":
    sys.exit(main())
