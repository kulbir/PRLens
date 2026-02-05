"""GitHub API client for PR operations."""

import os
from dataclasses import dataclass

from github import Auth, Github
from github.GithubException import GithubException


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


def get_github_client() -> Github:
    """Create GitHub client from environment token."""
    token = os.getenv("GITHUB_TOKEN")
    if not token:
        raise ValueError(
            "GITHUB_TOKEN not found. Set it in .env file.\n"
            "Get your token at: https://github.com/settings/tokens"
        )
    return Github(auth=Auth.Token(token))


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


# Quick test when run directly
if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    
    # Test with a public repo PR
    # Change these to test with your own repo
    TEST_REPO = "octocat/Hello-World"
    TEST_PR = 2988
    
    try:
        metadata = fetch_pr_metadata(TEST_REPO, TEST_PR)
        print(f"PR #{metadata.number}: {metadata.title}")
        print(f"Author: {metadata.author}")
        print(f"Draft: {metadata.draft}")
        print(f"State: {metadata.state}")
        print(f"Branches: {metadata.head_branch} → {metadata.base_branch}")
    except ValueError as e:
        print(f"Error: {e}")

