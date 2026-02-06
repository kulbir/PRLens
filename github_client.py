"""GitHub API client for PR operations."""

import os
import logging
import functools
from dataclasses import dataclass, field

import requests
import requests.exceptions
from github import Auth, Github
from github.GithubException import GithubException

from config import validate_repo, with_retry

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------
@dataclass
class PRMetadata:
    """Pull Request metadata."""

    number: int
    title: str
    author: str
    draft: bool
    state: str
    base_branch: str
    head_branch: str
    description: str | None


@dataclass
class ChangedFile:
    """A file changed in a Pull Request."""

    filename: str
    status: str  # added, removed, modified, renamed
    additions: int  # lines added
    deletions: int  # lines deleted
    changes: int  # total lines changed
    patch: str | None  # the diff/patch for this file


@dataclass
class ReviewComment:
    """A comment to post on a specific line in a PR."""

    path: str  # file path (e.g., "src/main.py")
    line: int  # line number in the file (new version)
    body: str  # comment text
    side: str = "RIGHT"  # RIGHT = new code, LEFT = old code


@dataclass
class ReviewSubmission:
    """A complete review to submit to a PR."""

    body: str = ""  # overall summary
    event: str = "COMMENT"  # APPROVE, REQUEST_CHANGES, COMMENT
    comments: list[ReviewComment] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Cached GitHub client
# ---------------------------------------------------------------------------
@functools.lru_cache(maxsize=1)
def get_github_client() -> Github:
    """Create or return a cached GitHub client."""
    token = os.getenv("GITHUB_TOKEN")
    if not token:
        raise ValueError(
            "GITHUB_TOKEN not found. Set it in .env file.\n"
            "Get your token at: https://github.com/settings/tokens"
        )
    return Github(auth=Auth.Token(token))


# ---------------------------------------------------------------------------
# Read operations
# ---------------------------------------------------------------------------
def fetch_pr_metadata(repo: str, pr_number: int) -> PRMetadata:
    """
    Fetch PR metadata from GitHub.

    Args:
        repo: Repository in "owner/repo" format (e.g., "kulbir/PRLens")
        pr_number: Pull request number

    Returns:
        PRMetadata object with PR details

    Raises:
        ValueError: If PR not found or access denied
    """
    repo = validate_repo(repo)
    client = get_github_client()

    try:
        repository = client.get_repo(repo)
        pr = repository.get_pull(pr_number)

        return PRMetadata(
            number=pr.number,
            title=pr.title,
            author=pr.user.login,
            draft=pr.draft,
            state=pr.state,
            base_branch=pr.base.ref,
            head_branch=pr.head.ref,
            description=pr.body,
        )
    except GithubException as e:
        if e.status == 404:
            raise ValueError(f"PR #{pr_number} not found in {repo}") from e
        raise ValueError(
            f"GitHub API error: {e.data.get('message', str(e))}"
        ) from e


def fetch_changed_files(repo: str, pr_number: int) -> list[ChangedFile]:
    """
    Fetch list of files changed in a PR.

    Args:
        repo: Repository in "owner/repo" format
        pr_number: Pull request number

    Returns:
        List of ChangedFile objects with file details and patches
    """
    repo = validate_repo(repo)
    client = get_github_client()

    try:
        repository = client.get_repo(repo)
        pr = repository.get_pull(pr_number)

        files = []
        for file in pr.get_files():
            files.append(
                ChangedFile(
                    filename=file.filename,
                    status=file.status,
                    additions=file.additions,
                    deletions=file.deletions,
                    changes=file.changes,
                    patch=file.patch,
                )
            )
        return files

    except GithubException as e:
        if e.status == 404:
            raise ValueError(f"PR #{pr_number} not found in {repo}") from e
        raise ValueError(
            f"GitHub API error: {e.data.get('message', str(e))}"
        ) from e


@with_retry(
    max_retries=3,
    base_delay=1.0,
    retryable=(
        requests.exceptions.ConnectionError,
        requests.exceptions.Timeout,
    ),
)
def fetch_raw_diff(repo: str, pr_number: int) -> str:
    """
    Fetch the raw unified diff for the entire PR.

    This uses the REST API directly because PyGithub doesn't expose
    the raw diff format. The diff includes all files in one string.

    Args:
        repo: Repository in "owner/repo" format
        pr_number: Pull request number

    Returns:
        Raw unified diff as a string

    Raises:
        ValueError: If PR not found or access denied
    """
    repo = validate_repo(repo)

    token = os.getenv("GITHUB_TOKEN")
    if not token:
        raise ValueError("GITHUB_TOKEN not found")

    url = f"https://api.github.com/repos/{repo}/pulls/{pr_number}"
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3.diff",
    }

    response = requests.get(url, headers=headers, timeout=30)

    if response.status_code == 404:
        raise ValueError(f"PR #{pr_number} not found in {repo}")
    response.raise_for_status()

    return response.text


# ---------------------------------------------------------------------------
# Write operations
# ---------------------------------------------------------------------------
def post_pr_comment(repo: str, pr_number: int, body: str) -> int:
    """
    Post a general comment on a PR (not attached to a specific line).

    This appears in the PR conversation, not inline with code.
    Useful for summaries or when findings don't map to specific lines.

    Args:
        repo: Repository in "owner/repo" format
        pr_number: Pull request number
        body: Comment text (supports markdown)

    Returns:
        Comment ID

    Raises:
        ValueError: If posting fails
    """
    repo = validate_repo(repo)
    client = get_github_client()

    try:
        repository = client.get_repo(repo)
        pr = repository.get_pull(pr_number)
        comment = pr.create_issue_comment(body)
        logger.info("Posted comment %d on PR #%d", comment.id, pr_number)
        return comment.id

    except GithubException as e:
        raise ValueError(
            f"Failed to post comment: {e.data.get('message', str(e))}"
        ) from e


def post_review(repo: str, pr_number: int, review: ReviewSubmission) -> int:
    """
    Post a complete review with inline comments to a PR.

    This is the main function for posting AI findings. Each comment
    appears inline next to the relevant code.

    Args:
        repo: Repository in "owner/repo" format
        pr_number: Pull request number
        review: ReviewSubmission with body, event type, and comments

    Returns:
        Review ID

    Raises:
        ValueError: If posting fails
    """
    repo = validate_repo(repo)
    client = get_github_client()

    try:
        repository = client.get_repo(repo)
        pr = repository.get_pull(pr_number)

        # Get the latest commit SHA (required for review API)
        commit = pr.get_commits().reversed[0]

        # Build comments in the format GitHub expects
        comments_payload = []
        for comment in review.comments:
            comments_payload.append(
                {
                    "path": comment.path,
                    "line": comment.line,
                    "side": comment.side,
                    "body": comment.body,
                }
            )

        # Use PyGithub's create_review method
        github_review = pr.create_review(
            commit=commit,
            body=review.body,
            event=review.event,
            comments=comments_payload,
        )

        logger.info(
            "Posted review %d on PR #%d with %d comments",
            github_review.id,
            pr_number,
            len(comments_payload),
        )
        return github_review.id

    except GithubException as e:
        error_msg = (
            e.data.get("message", str(e)) if hasattr(e, "data") else str(e)
        )
        logger.error("Failed to post review: %s", error_msg)

        if hasattr(e, "data") and "errors" in e.data:
            for error in e.data["errors"]:
                logger.error("  - %s", error)

        raise ValueError(f"Failed to post review: {error_msg}") from e


def post_review_with_fallback(
    repo: str,
    pr_number: int,
    review: ReviewSubmission,
) -> dict:
    """
    Post a review, falling back to general comment if line comments fail.

    Some findings may not map to valid diff lines. This function tries
    to post inline comments first, and falls back to a general comment
    if that fails.

    Args:
        repo: Repository in "owner/repo" format
        pr_number: Pull request number
        review: ReviewSubmission with body, event type, and comments

    Returns:
        Dict with 'review_id' and/or 'comment_id', plus 'fallback' boolean
    """
    repo = validate_repo(repo)
    result: dict = {"fallback": False}

    # If no inline comments, just post the summary as a general comment
    if not review.comments:
        if review.body:
            result["comment_id"] = post_pr_comment(repo, pr_number, review.body)
        return result

    # Try posting as a proper review with inline comments
    try:
        result["review_id"] = post_review(repo, pr_number, review)
        return result

    except ValueError as e:
        logger.warning("Review failed, falling back to general comment: %s", e)
        result["fallback"] = True

        # Format findings as a markdown comment
        fallback_body = review.body + "\n\n" if review.body else ""
        fallback_body += "## Inline Comments\n\n"
        fallback_body += (
            "_Could not post as inline comments. Listing here instead:_\n\n"
        )

        for comment in review.comments:
            fallback_body += f"**{comment.path}** (line {comment.line}):\n"
            fallback_body += f"> {comment.body}\n\n"

        result["comment_id"] = post_pr_comment(repo, pr_number, fallback_body)
        return result


# ---------------------------------------------------------------------------
# Quick test when run directly
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import sys

    import config as _config  # noqa: F401 — ensures env & logging are initialised

    TEST_REPO = "kulbir/PRLens"
    TEST_PR = 1

    def test_read_operations():
        """Test fetching PR data (safe, no changes made)."""
        print("=" * 50)
        print("PR METADATA")
        print("=" * 50)
        metadata = fetch_pr_metadata(TEST_REPO, TEST_PR)
        print(f"PR #{metadata.number}: {metadata.title}")
        print(f"Author: {metadata.author}")
        print(f"Draft: {metadata.draft}")
        print(f"State: {metadata.state}")
        print(f"Branches: {metadata.head_branch} → {metadata.base_branch}")

        print("\n" + "=" * 50)
        print("CHANGED FILES")
        print("=" * 50)
        files = fetch_changed_files(TEST_REPO, TEST_PR)
        print(f"Total files changed: {len(files)}\n")

        for file in files:
            print(f"📄 {file.filename}")
            print(f"   Status: {file.status}")
            print(f"   Changes: +{file.additions} -{file.deletions}")
            if file.patch:
                preview = (
                    file.patch[:200] + "..."
                    if len(file.patch) > 200
                    else file.patch
                )
                print(f"   Patch preview:\n{preview}")
            print()

        print("=" * 50)
        print("RAW DIFF")
        print("=" * 50)
        raw_diff = fetch_raw_diff(TEST_REPO, TEST_PR)
        print(f"Total diff size: {len(raw_diff)} characters\n")
        preview = raw_diff[:500] + "..." if len(raw_diff) > 500 else raw_diff
        print(preview)

    def test_post_general_comment():
        """Test posting a general comment on PR."""
        print("=" * 50)
        print("POSTING GENERAL COMMENT")
        print("=" * 50)

        comment_body = """## 🤖 Hello from PRLens!

This is a test comment posted by the PRLens agent.

**What just happened:**
- PRLens connected to the GitHub API
- Used your `GITHUB_TOKEN` to authenticate
- Posted this comment programmatically

If you see this, the write-back is working! 🎉
"""
        comment_id = post_pr_comment(TEST_REPO, TEST_PR, comment_body)
        print(f"✅ Posted comment with ID: {comment_id}")
        print(f"   View at: https://github.com/{TEST_REPO}/pull/{TEST_PR}")

    def test_post_review_with_comments():
        """Test posting a review with inline comments."""
        print("=" * 50)
        print("POSTING REVIEW WITH INLINE COMMENTS")
        print("=" * 50)

        from diff_parser import parse_diff, build_line_mapping

        raw_diff = fetch_raw_diff(TEST_REPO, TEST_PR)
        files = parse_diff(raw_diff)
        mappings = build_line_mapping(raw_diff)

        review_comments = []
        for file in files:
            if file.filename in mappings:
                mapping = mappings[file.filename]
                if mapping.valid_lines:
                    line = min(mapping.valid_lines)
                    review_comments.append(
                        ReviewComment(
                            path=file.filename,
                            line=line,
                            body=(
                                "🤖 **PRLens Test Comment**\n\n"
                                "This inline comment was posted by PRLens "
                                "to test the review API."
                            ),
                        )
                    )
                    break

        if not review_comments:
            print("❌ No valid lines found in diff to comment on")
            return

        review = ReviewSubmission(
            body=(
                "## 🤖 PRLens Test Review\n\n"
                "This is a test review with inline comments."
            ),
            event="COMMENT",
            comments=review_comments,
        )

        review_id = post_review(TEST_REPO, TEST_PR, review)
        print(f"✅ Posted review with ID: {review_id}")
        print(f"   Comments posted: {len(review_comments)}")
        print(f"   View at: https://github.com/{TEST_REPO}/pull/{TEST_PR}")

    # Run tests based on command line args
    try:
        if len(sys.argv) > 1:
            test_type = sys.argv[1]
            if test_type == "read":
                test_read_operations()
            elif test_type == "comment":
                test_post_general_comment()
            elif test_type == "review":
                test_post_review_with_comments()
            else:
                print(f"Unknown test: {test_type}")
                print("Usage: python github_client.py [read|comment|review]")
        else:
            print("Usage: python github_client.py [read|comment|review]")
            print("  read    - Test fetching PR data (safe)")
            print("  comment - Post a general comment on PR")
            print("  review  - Post a review with inline comment")

    except ValueError as e:
        print(f"Error: {e}")
