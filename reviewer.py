"""PR Review orchestration - connects GitHub + Gemini."""

import logging

from config import (
    DEFAULT_MODEL,
    USE_MOCK,
    call_gemini,
    parse_llm_json,
)
from models import Finding, ReviewResult
from prompts import QUALITY_PROMPT, REVIEW_PROMPT, SECURITY_PROMPT

logger = logging.getLogger(__name__)

# Token limits (conservative estimates)
# Gemini 2.5 Flash has ~1M context, but we keep chunks small for better results
MAX_LINES_PER_CHUNK = 200  # Max lines to send in one request
MAX_CHARS_PER_CHUNK = 15000  # Max characters (~3750 tokens)


# ---------------------------------------------------------------------------
# Chunking helpers
# ---------------------------------------------------------------------------
def chunk_code(
    code: str,
    max_lines: int = MAX_LINES_PER_CHUNK,
    max_chars: int = MAX_CHARS_PER_CHUNK,
) -> list[str]:
    """
    Split large code into reviewable chunks.

    Tries to split at logical boundaries (empty lines, function definitions).
    Each chunk preserves line numbers from the original.

    Args:
        code: Code string with line numbers (e.g., "   1| def foo():")
        max_lines: Maximum lines per chunk
        max_chars: Maximum characters per chunk

    Returns:
        List of code chunks, each small enough for one API call
    """
    lines = code.split("\n")

    # If code is small enough, return as-is
    if len(lines) <= max_lines and len(code) <= max_chars:
        return [code]

    chunks: list[str] = []
    current_chunk: list[str] = []
    current_chars = 0

    for line in lines:
        line_with_newline = line + "\n"

        # Check if adding this line would exceed limits
        would_exceed_lines = len(current_chunk) >= max_lines
        would_exceed_chars = current_chars + len(line_with_newline) > max_chars

        if current_chunk and (would_exceed_lines or would_exceed_chars):
            # Save current chunk and start new one
            chunks.append("\n".join(current_chunk))
            current_chunk = []
            current_chars = 0

        current_chunk.append(line)
        current_chars += len(line_with_newline)

    # Don't forget the last chunk
    if current_chunk:
        chunks.append("\n".join(current_chunk))

    return chunks


def is_large_file(code: str) -> bool:
    """Check if code exceeds chunk limits."""
    lines = code.split("\n")
    return len(lines) > MAX_LINES_PER_CHUNK or len(code) > MAX_CHARS_PER_CHUNK


# ---------------------------------------------------------------------------
# Core review functions
# ---------------------------------------------------------------------------
def analyze_code_chunk(
    code: str,
    filename: str,
    chunk_info: str = "",
    model: str = DEFAULT_MODEL,
) -> ReviewResult | None:
    """Send a single code chunk to Gemini for review."""
    if USE_MOCK:
        return ReviewResult(
            findings=[
                Finding(
                    severity="MEDIUM",
                    category="bug",
                    line=1,
                    description="Mock finding for testing",
                    fix="This is a mock fix",
                )
            ],
            summary="Mock review",
        )

    chunk_note = f" ({chunk_info})" if chunk_info else ""
    prompt = (
        f"Review this code from file '{filename}'{chunk_note}.\n\n"
        f"{REVIEW_PROMPT.format(code=code)}"
    )

    try:
        text = call_gemini(prompt, model)
        return parse_llm_json(text)
    except Exception as e:
        logger.error("Error reviewing %s: %s", filename, e)
        return None


def analyze_code(
    code: str,
    filename: str,
    model: str = DEFAULT_MODEL,
) -> ReviewResult | None:
    """
    Send code to Gemini for review, handling large files with chunking.

    If code exceeds limits, splits into chunks and combines findings.
    """
    # Check if chunking is needed
    if not is_large_file(code):
        return analyze_code_chunk(code, filename, model=model)

    # Split into chunks and review each
    chunks = chunk_code(code)
    logger.info("  Large file detected - splitting into %d chunks", len(chunks))

    all_findings: list[Finding] = []
    summaries: list[str] = []

    for i, chunk in enumerate(chunks, 1):
        chunk_info = f"chunk {i}/{len(chunks)}"
        logger.info("  Reviewing %s...", chunk_info)

        result = analyze_code_chunk(chunk, filename, chunk_info=chunk_info, model=model)

        if result:
            all_findings.extend(result.findings)
            if result.summary:
                summaries.append(result.summary)

    if not all_findings:
        return None

    # Combine results
    return ReviewResult(
        findings=all_findings,
        summary=(
            f"Combined review of {len(chunks)} chunks: " + "; ".join(summaries[:3])
        ),
    )


# ---------------------------------------------------------------------------
# Specialised reviewers
# ---------------------------------------------------------------------------
def _review_with_prompt(
    code: str,
    filename: str,
    prompt_template: str,
    reviewer_name: str,
    model: str = DEFAULT_MODEL,
) -> ReviewResult | None:
    """
    Generic function to review code with a specific prompt.

    Args:
        code: The code to review
        filename: Name of the file being reviewed
        prompt_template: The prompt template to use (must have {code} placeholder)
        reviewer_name: Name for logging (e.g., "security", "quality")
        model: Gemini model to use

    Returns:
        ReviewResult with findings, or None if failed
    """
    if USE_MOCK:
        return ReviewResult(
            findings=[],
            summary=f"Mock {reviewer_name} review - no issues",
        )

    prompt = prompt_template.format(code=code)

    try:
        text = call_gemini(prompt, model)
        return parse_llm_json(text)
    except Exception as e:
        logger.error("%s error reviewing %s: %s", reviewer_name, filename, e)
        return None


def security_review(
    code: str,
    filename: str,
    model: str = DEFAULT_MODEL,
) -> ReviewResult | None:
    """
    Review code for SECURITY issues only.

    Uses a specialised prompt focused on:
    - SQL Injection, Command Injection
    - XSS, SSRF
    - Hardcoded secrets
    - Insecure deserialization
    - Path traversal
    - Weak cryptography

    Args:
        code: The code to review
        filename: Name of the file being reviewed
        model: Gemini model to use

    Returns:
        ReviewResult with security findings only
    """
    logger.info("  🔒 Security review: %s", filename)
    return _review_with_prompt(code, filename, SECURITY_PROMPT, "security", model)


def quality_review(
    code: str,
    filename: str,
    model: str = DEFAULT_MODEL,
) -> ReviewResult | None:
    """
    Review code for QUALITY issues only.

    Uses a specialised prompt focused on:
    - Code complexity
    - Poor naming
    - Code duplication
    - Missing error handling
    - Magic numbers/strings

    Args:
        code: The code to review
        filename: Name of the file being reviewed
        model: Gemini model to use

    Returns:
        ReviewResult with quality findings only
    """
    logger.info("  📐 Quality review: %s", filename)
    return _review_with_prompt(code, filename, QUALITY_PROMPT, "quality", model)
