"""GitHub API client for PR operations."""

import functools
import logging
import os
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
        raise ValueError(f"GitHub API error: {e.data.get('message', str(e))}") from e


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
        error_msg = e.data.get("message", str(e)) if hasattr(e, "data") else str(e)
        logger.error("Failed to post review: %s", error_msg)

        if hasattr(e, "data") and "errors" in e.data:
            for error in e.data["errors"]:
                logger.error("  - %s", error)

        raise ValueError(f"Failed to post review: {error_msg}") from e
