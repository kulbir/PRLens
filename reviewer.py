"""PR Review orchestration - connects GitHub + Gemini."""

import logging
from dataclasses import dataclass, field

from config import (
    DEFAULT_MODEL,
    USE_MOCK,
    call_gemini,
    parse_llm_json,
)
from diff_parser import extract_added_code, filter_files, parse_diff
from github_client import fetch_pr_metadata, fetch_raw_diff
from models import Finding, ReviewResult
from prompts import QUALITY_PROMPT, REVIEW_PROMPT, SECURITY_PROMPT

logger = logging.getLogger(__name__)

# Token limits (conservative estimates)
# Gemini 2.5 Flash has ~1M context, but we keep chunks small for better results
MAX_LINES_PER_CHUNK = 200  # Max lines to send in one request
MAX_CHARS_PER_CHUNK = 15000  # Max characters (~3750 tokens)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------
@dataclass
class FileReview:
    """Review results for a single file."""

    filename: str
    status: str
    additions: int
    findings: list[Finding] = field(default_factory=list)
    error: str | None = None


@dataclass
class PRReview:
    """Complete review results for a PR."""

    repo: str
    pr_number: int
    pr_title: str
    pr_author: str
    files_reviewed: int
    total_findings: int
    file_reviews: list[FileReview] = field(default_factory=list)


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


def general_review(
    code: str,
    filename: str,
    model: str = DEFAULT_MODEL,
) -> ReviewResult | None:
    """
    Review code for general issues (bugs, performance, style).

    This is the original comprehensive review.

    Args:
        code: The code to review
        filename: Name of the file being reviewed
        model: Gemini model to use

    Returns:
        ReviewResult with all types of findings
    """
    logger.info("  🔍 General review: %s", filename)
    return analyze_code(code, filename, model)


# ---------------------------------------------------------------------------
# High-level PR review
# ---------------------------------------------------------------------------
def review_pr(repo: str, pr_number: int) -> PRReview:
    """
    Review a Pull Request using Gemini.

    Args:
        repo: Repository in "owner/repo" format
        pr_number: Pull request number

    Returns:
        PRReview object with all findings
    """
    logger.info("Starting review of %s PR #%d", repo, pr_number)

    # 1. Fetch PR metadata
    logger.info("Fetching PR metadata...")
    metadata = fetch_pr_metadata(repo, pr_number)
    logger.info("PR: %s by %s", metadata.title, metadata.author)

    # 2. Fetch the diff
    logger.info("Fetching PR diff...")
    raw_diff = fetch_raw_diff(repo, pr_number)

    # 3. Parse and filter files
    logger.info("Parsing diff...")
    all_files = parse_diff(raw_diff)
    files_to_review = filter_files(all_files)
    logger.info(
        "Files to review: %d (filtered from %d)",
        len(files_to_review),
        len(all_files),
    )

    # 4. Review each file
    file_reviews: list[FileReview] = []
    total_findings = 0

    for file in files_to_review:
        logger.info("Reviewing %s...", file.filename)

        # Extract code to review
        code = extract_added_code(file, include_line_numbers=True)

        if not code.strip():
            logger.info("  Skipping %s - no code to review", file.filename)
            continue

        # Send to Gemini
        result = analyze_code(code, file.filename)

        if result:
            findings = result.findings
            total_findings += len(findings)

            file_reviews.append(
                FileReview(
                    filename=file.filename,
                    status=file.status,
                    additions=file.additions,
                    findings=findings,
                )
            )

            logger.info("  Found %d issue(s) in %s", len(findings), file.filename)
        else:
            file_reviews.append(
                FileReview(
                    filename=file.filename,
                    status=file.status,
                    additions=file.additions,
                    error="Failed to analyze file",
                )
            )

    # 5. Return complete review
    return PRReview(
        repo=repo,
        pr_number=pr_number,
        pr_title=metadata.title,
        pr_author=metadata.author,
        files_reviewed=len(file_reviews),
        total_findings=total_findings,
        file_reviews=file_reviews,
    )


def print_review(review: PRReview) -> None:
    """Pretty print a PR review."""
    print(f"\n{'=' * 60}")
    print(f"📋 PR REVIEW: {review.repo} #{review.pr_number}")
    print(f"{'=' * 60}")
    print(f"Title: {review.pr_title}")
    print(f"Author: {review.pr_author}")
    print(f"Files reviewed: {review.files_reviewed}")
    print(f"Total findings: {review.total_findings}")

    for file_review in review.file_reviews:
        print(f"\n{'─' * 60}")
        print(
            f"📄 {file_review.filename} "
            f"({file_review.status}, +{file_review.additions})"
        )
        print(f"{'─' * 60}")

        if file_review.error:
            print(f"  ⚠️  Error: {file_review.error}")
            continue

        if not file_review.findings:
            print("  ✅ No issues found")
            continue

        for finding in file_review.findings:
            icon = {
                "bug": "🐛",
                "security": "🔒",
                "performance": "⚡",
                "pep8": "📐",
                "style": "📐",
                "quality": "📐",
            }.get(finding.category, "❓")

            line_str = f"Line {finding.line}" if finding.line else "General"
            print(f"\n  {icon} [{finding.severity}] {line_str}")
            print(f"     {finding.description}")
            if finding.fix:
                print(f"     💡 Fix: {finding.fix}")

    print(f"\n{'=' * 60}")
    print(f"Review complete: {review.total_findings} finding(s)")
    print(f"{'=' * 60}\n")


# Quick test
if __name__ == "__main__":
    TEST_REPO = "kulbir/PRLens"
    TEST_PR = 1

    review = review_pr(TEST_REPO, TEST_PR)
    print_review(review)
