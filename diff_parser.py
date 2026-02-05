"""Parser for unified diff format using unidiff library."""

from dataclasses import dataclass, field
from unidiff import PatchSet


@dataclass
class FileDiff:
    """Parsed diff for a single file."""
    filename: str
    status: str                           # added, deleted, modified, renamed
    additions: int                        # count of added lines
    deletions: int                        # count of deleted lines
    added_lines: list[tuple[int, str]] = field(default_factory=list)   # (line_num, content)
    deleted_lines: list[tuple[int, str]] = field(default_factory=list) # (line_num, content)
    patch: str = ""                       # raw patch text


def parse_diff(diff_text: str) -> list[FileDiff]:
    """
    Parse a unified diff into structured FileDiff objects.
    
    Args:
        diff_text: Raw unified diff string
        
    Returns:
        List of FileDiff objects, one per file
    """
    patch_set = PatchSet(diff_text)
    files = []
    
    for patched_file in patch_set:
        # Determine status
        if patched_file.is_added_file:
            status = "added"
        elif patched_file.is_removed_file:
            status = "deleted"
        elif patched_file.is_rename:
            status = "renamed"
        else:
            status = "modified"
        
        # Extract added and deleted lines with line numbers
        added_lines = []
        deleted_lines = []
        
        for hunk in patched_file:
            for line in hunk:
                if line.is_added:
                    added_lines.append((line.target_line_no, line.value.rstrip('\n')))
                elif line.is_removed:
                    deleted_lines.append((line.source_line_no, line.value.rstrip('\n')))
        
        files.append(FileDiff(
            filename=patched_file.path,
            status=status,
            additions=patched_file.added,
            deletions=patched_file.removed,
            added_lines=added_lines,
            deleted_lines=deleted_lines,
            patch=str(patched_file),
        ))
    
    return files


# File extensions to skip during review
SKIP_EXTENSIONS = {
    '.md', '.txt', '.rst', '.adoc',           # Docs
    '.lock',                                   # Lock files
    '.png', '.jpg', '.jpeg', '.gif', '.svg', '.ico', '.webp',  # Images
    '.woff', '.woff2', '.ttf', '.eot',        # Fonts
    '.csv', '.json', '.xml', '.yaml', '.yml', '.toml',  # Data
    '.min.js', '.min.css', '.map',            # Build artifacts
    '.exe', '.dll', '.so', '.dylib', '.pyc',  # Binary
    '.zip', '.tar', '.gz', '.pdf',            # Archives/docs
}

SKIP_FILENAMES = {
    'package-lock.json', 'yarn.lock', 'pnpm-lock.yaml',
    'Pipfile.lock', 'poetry.lock', 'composer.lock',
    'Gemfile.lock', 'Cargo.lock', 'uv.lock',
    '.gitignore', '.gitattributes', '.editorconfig',
    'LICENSE', 'LICENSE.md', 'LICENSE.txt',
}

SKIP_DIRECTORIES = {'node_modules/', 'vendor/', 'dist/', 'build/', '.git/', '__pycache__/', '.venv/'}


def should_review_file(filename: str) -> bool:
    """Check if file should be reviewed based on name/extension."""
    # Check directory
    for skip_dir in SKIP_DIRECTORIES:
        if filename.startswith(skip_dir) or f'/{skip_dir}' in filename:
            return False
    
    # Check exact filename
    basename = filename.split('/')[-1]
    if basename in SKIP_FILENAMES:
        return False
    
    # Check extension
    for ext in SKIP_EXTENSIONS:
        if filename.lower().endswith(ext):
            return False
    
    return True


def filter_files(files: list[FileDiff], include_deletions: bool = False) -> list[FileDiff]:
    """Filter out files that shouldn't be reviewed."""
    result = []
    
    for file in files:
        if not should_review_file(file.filename):
            continue
        if not include_deletions and file.status == 'deleted':
            continue
        if not include_deletions and len(file.added_lines) == 0:
            continue
        result.append(file)
    
    return result


def extract_added_code(file: FileDiff, include_line_numbers: bool = True) -> str:
    """
    Extract only the added lines as a code string.
    
    Args:
        file: FileDiff object
        include_line_numbers: If True, prefix each line with its line number
        
    Returns:
        String containing only the new code, ready for review
    """
    if not file.added_lines:
        return ""
    
    lines = []
    for line_num, content in file.added_lines:
        if include_line_numbers:
            lines.append(f"{line_num:4}| {content}")
        else:
            lines.append(content)
    
    return "\n".join(lines)


def get_review_content(file: FileDiff) -> dict:
    """
    Get file content formatted for LLM review.
    
    Returns:
        Dict with filename, status, and code to review
    """
    return {
        "filename": file.filename,
        "status": file.status,
        "total_additions": file.additions,
        "code": extract_added_code(file, include_line_numbers=True),
    }


# Quick test
if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    
    from github_client import fetch_raw_diff
    
    TEST_REPO = "kulbir/PRLens"
    TEST_PR = 1
    
    print("Fetching diff...")
    raw_diff = fetch_raw_diff(TEST_REPO, TEST_PR)
    
    print("\nParsing diff with unidiff...")
    all_files = parse_diff(raw_diff)
    filtered = filter_files(all_files)
    
    print(f"\nFiles to review: {len(filtered)}")
    
    for f in filtered:
        print(f"\n{'='*60}")
        print(f"📄 {f.filename} ({f.status}, +{f.additions} lines)")
        print('='*60)
        
        # Extract just the added code
        added_code = extract_added_code(f)
        
        # Show preview (first 20 lines)
        lines = added_code.split('\n')
        preview = '\n'.join(lines[:20])
        print(preview)
        
        if len(lines) > 20:
            print(f"\n... and {len(lines) - 20} more lines")
        
        # Show what would be sent to LLM
        print(f"\n{'='*60}")
        print("REVIEW CONTENT (for Gemini):")
        print('='*60)
        review = get_review_content(f)
        print(f"Filename: {review['filename']}")
        print(f"Status: {review['status']}")
        print(f"Lines to review: {review['total_additions']}")
