"""GitHub API client for PR operations."""

import os
from dataclasses import dataclass

import requests
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


@dataclass
class ChangedFile:
    """A file changed in a Pull Request."""
    filename: str
    status: str          # added, removed, modified, renamed
    additions: int       # lines added
    deletions: int       # lines deleted
    changes: int         # total lines changed
    patch: str | None    # the diff/patch for this file


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


def fetch_changed_files(repo: str, pr_number: int) -> list[ChangedFile]:
    """
    Fetch list of files changed in a PR.
    
    Args:
        repo: Repository in "owner/repo" format
        pr_number: Pull request number
        
    Returns:
        List of ChangedFile objects with file details and patches
    """
    client = get_github_client()
    
    try:
        repository = client.get_repo(repo)
        pr = repository.get_pull(pr_number)
        
        files = []
        for file in pr.get_files():
            files.append(ChangedFile(
                filename=file.filename,
                status=file.status,
                additions=file.additions,
                deletions=file.deletions,
                changes=file.changes,
                patch=file.patch,  # This is the diff for this file
            ))
        return files
        
    except GithubException as e:
        if e.status == 404:
            raise ValueError(f"PR #{pr_number} not found in {repo}") from e
        raise ValueError(f"GitHub API error: {e.data.get('message', str(e))}") from e


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
    token = os.getenv("GITHUB_TOKEN")
    if not token:
        raise ValueError("GITHUB_TOKEN not found")
    
    url = f"https://api.github.com/repos/{repo}/pulls/{pr_number}"
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3.diff",  # Request diff format
    }
    
    response = requests.get(url, headers=headers)
    
    if response.status_code == 404:
        raise ValueError(f"PR #{pr_number} not found in {repo}")
    response.raise_for_status()
    
    return response.text


# Quick test when run directly
if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    
    # Test with a public repo PR
    TEST_REPO = "kulbir/PRLens"
    TEST_PR = 1
    
    try:
        # Test metadata
        print("=" * 50)
        print("PR METADATA")
        print("=" * 50)
        metadata = fetch_pr_metadata(TEST_REPO, TEST_PR)
        print(f"PR #{metadata.number}: {metadata.title}")
        print(f"Author: {metadata.author}")
        print(f"Draft: {metadata.draft}")
        print(f"State: {metadata.state}")
        print(f"Branches: {metadata.head_branch} → {metadata.base_branch}")
        
        # Test changed files
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
                # Show first 200 chars of patch
                preview = file.patch[:200] + "..." if len(file.patch) > 200 else file.patch
                print(f"   Patch preview:\n{preview}")
            print()
        
        # Test raw diff
        print("=" * 50)
        print("RAW DIFF")
        print("=" * 50)
        raw_diff = fetch_raw_diff(TEST_REPO, TEST_PR)
        print(f"Total diff size: {len(raw_diff)} characters\n")
        # Show first 500 chars
        preview = raw_diff[:500] + "..." if len(raw_diff) > 500 else raw_diff
        print(preview)
            
    except ValueError as e:
        print(f"Error: {e}")

